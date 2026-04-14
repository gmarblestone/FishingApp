"""
Scores each day 1-10 for inshore, nearshore, and offshore fishing.
Recommends best species based on conditions.
"""

import logging
from datetime import datetime, timezone, timedelta

# US Central Time (CDT = UTC-5, CST = UTC-6) — use CDT for spring/summer
try:
    import zoneinfo
    CENTRAL = zoneinfo.ZoneInfo("America/Chicago")
except Exception:
    CENTRAL = timezone(timedelta(hours=-5))


def _fmt12(time_24: str) -> str:
    """Convert 'HH:MM' 24h to '12:30 PM'."""
    try:
        h, m = int(time_24.split(":")[0]), time_24.split(":")[1]
        suffix = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12}:{m} {suffix}"
    except Exception:
        return time_24


def _fmt_generated_at(dt: datetime) -> str:
    """Format datetime as 'M/DD/YYYY h:MM AM/PM'."""
    h = dt.hour % 12 or 12
    suffix = "AM" if dt.hour < 12 else "PM"
    return f"{dt.month}/{dt.day:02d}/{dt.year} {h}:{dt.minute:02d} {suffix}"

try:
    from fishing_forecast.config import (
        AREAS,
        INSHORE_WEIGHTS,
        NEARSHORE_WEIGHTS,
        OFFSHORE_WEIGHTS,
        SPECIES_TEMP_RANGES,
        WAVE_OFFSHORE_IDEAL_FT,
        WAVE_OFFSHORE_MAX_FT,
        WIND_FISHABLE_MPH,
        WIND_IDEAL_MPH,
        WIND_OFFSHORE_MAX_MPH,
    )
    from fishing_forecast.fetcher import fetch_all_conditions
    from fishing_forecast.models import DayConditions, DayForecast, ForecastResult, TimeWindow
except ImportError:
    from config import (
        AREAS,
        INSHORE_WEIGHTS,
        NEARSHORE_WEIGHTS,
        OFFSHORE_WEIGHTS,
        SPECIES_TEMP_RANGES,
        WAVE_OFFSHORE_IDEAL_FT,
        WAVE_OFFSHORE_MAX_FT,
        WIND_FISHABLE_MPH,
        WIND_IDEAL_MPH,
        WIND_OFFSHORE_MAX_MPH,
    )
    from fetcher import fetch_all_conditions
    from models import DayConditions, DayForecast, ForecastResult, TimeWindow

logger = logging.getLogger(__name__)


def _score_wind(speed: float, max_ideal: float, max_fishable: float) -> float:
    """Score wind 0-10. Ideal or below = 10, above fishable = 0."""
    if speed <= max_ideal:
        return 10.0
    if speed >= max_fishable * 1.5:
        return 0.0
    if speed <= max_fishable:
        return 10.0 - ((speed - max_ideal) / (max_fishable - max_ideal)) * 5
    return max(0, 5.0 - ((speed - max_fishable) / max_fishable) * 5)


def _score_tide(conditions: DayConditions) -> float:
    """Score tide quality. More swings and bigger range = better."""
    total_events = len(conditions.tide.high_times) + len(conditions.tide.low_times)
    if total_events == 0:
        return 3.0  # no data, neutral
    range_score = min(conditions.tide.range_ft / 2.0, 1.0) * 5
    event_score = min(total_events / 4, 1.0) * 5
    return range_score + event_score


def _score_pressure(trend: str) -> float:
    """Stable or slowly falling = best. Rising post-front = worst."""
    return {"stable": 8.0, "falling": 9.0, "rising": 4.0}.get(trend, 5.0)


def _score_solunar(conditions: DayConditions) -> float:
    """Score solunar — use rating if available, else neutral."""
    if conditions.solunar.rating:
        return conditions.solunar.rating * 2  # 1-5 → 2-10
    return 5.0


def _score_swell(wave_ft: float, ideal: float, max_ft: float) -> float:
    """Score swell for offshore. Lower = better."""
    if wave_ft <= ideal:
        return 10.0
    if wave_ft >= max_ft:
        return 1.0
    return 10.0 - ((wave_ft - ideal) / (max_ft - ideal)) * 9


def _score_water_temp(temp_f: float) -> float:
    """General water temp score — moderate temps are best."""
    if temp_f == 0:
        return 5.0  # no data
    if 62 <= temp_f <= 78:
        return 9.0
    if 55 <= temp_f <= 85:
        return 6.0
    return 3.0


def _score_cloud_cover(pct: int) -> float:
    """Overcast can be good. Partly cloudy is ideal."""
    if 30 <= pct <= 70:
        return 8.0
    if pct < 30:
        return 6.0
    return 5.0


def _weighted_score(subscores: dict[str, float], weights: dict[str, float]) -> int:
    """Combine subscores with weights into a 1-10 score."""
    total = sum(subscores.get(k, 5.0) * w for k, w in weights.items())
    return max(1, min(10, round(total)))


def _pick_species(conditions: DayConditions) -> str:
    """Recommend species based on water temp and tide pattern."""
    temp = conditions.buoy.water_temp_f
    month = conditions.date.month

    # Fall flounder run
    if month in (10, 11) and 55 <= temp <= 68:
        if len(conditions.tide.low_times) >= 2:
            return "Flounder"

    # Trophy trout in winter
    if month in (12, 1, 2) and 48 <= temp <= 60:
        return "Trout (trophy)"

    # Check ideal ranges
    best = "Redfish"
    best_fit = 0
    for species, temps in SPECIES_TEMP_RANGES.items():
        if temps["ideal_min"] <= temp <= temps["ideal_max"]:
            fit = 1.0
        elif temps["min"] <= temp <= temps["max"]:
            fit = 0.5
        else:
            fit = 0.0
        if fit > best_fit:
            best_fit = fit
            best = species.capitalize()

    return best


def _pick_best_window(conditions: DayConditions) -> str:
    """Identify the best fishing window for the day."""
    wind = conditions.wind.speed_mph
    if wind <= WIND_IDEAL_MPH:
        return "All day — light wind"
    if conditions.air_temp_high_f > 85:
        return "Dawn to mid-morning (beat the heat)"
    if len(conditions.tide.high_times) > 0:
        return f"Around tide changes: highs {', '.join(_fmt12(t) for t in conditions.tide.high_times)}"
    return "Early morning best"


def _pick_worst_window(conditions: DayConditions) -> str:
    """Identify the worst fishing window for the day."""
    if conditions.air_temp_high_f > 85:
        return "Midday 11 AM - 3 PM (peak heat)"
    if conditions.wind.speed_mph > WIND_FISHABLE_MPH:
        return "All day — wind too strong"
    if conditions.rain_chance_pct >= 60:
        return "Afternoon (storms likely)"
    # Slack tide = slowest
    if conditions.tide.low_times:
        return f"Slack low tide around {_fmt12(conditions.tide.low_times[0])}"
    return "Midday (slack tide period)"


def _build_time_windows(conditions: DayConditions) -> list[TimeWindow]:
    """Break the day into fishing quality windows."""
    windows = []
    wind = conditions.wind.speed_mph
    temp_high = conditions.air_temp_high_f

    # Dawn (5-7 AM) — usually best
    dawn_quality = "prime" if wind <= WIND_IDEAL_MPH else "good" if wind <= WIND_FISHABLE_MPH else "fair"
    dawn_reason = "Calm water, low light, active fish"
    if wind > WIND_FISHABLE_MPH:
        dawn_reason = f"Wind already {wind:.0f} mph but low light helps"
    windows.append(TimeWindow("5:00 AM – 7:00 AM", dawn_quality, dawn_reason))

    # Morning (7-10 AM) — tide-dependent
    morning_quality = "good"
    morning_reason = "Good light, fish still feeding"
    tide_events = conditions.tide.high_times + conditions.tide.low_times
    morning_tides = [t for t in tide_events if "07" <= t[:2] <= "10"]
    if morning_tides:
        morning_quality = "prime"
        morning_reason = f"Tide change at {', '.join(_fmt12(t) for t in morning_tides)} — peak movement"
    if wind > WIND_FISHABLE_MPH:
        morning_quality = "fair"
        morning_reason += f" (wind {wind:.0f} mph)"
    windows.append(TimeWindow("7:00 AM – 10:00 AM", morning_quality, morning_reason))

    # Midday (10 AM - 2 PM)
    midday_quality = "fair"
    midday_reason = "Sun high, fish go deeper"
    if temp_high > 85:
        midday_quality = "poor"
        midday_reason = "Peak heat — fish shut down in shallows"
    elif temp_high < 65:
        midday_quality = "good"
        midday_reason = "Warmest part of day — winter fish move up"
    midday_tides = [t for t in tide_events if "10" <= t[:2] <= "14"]
    if midday_tides and midday_quality != "poor":
        midday_quality = "good"
        midday_reason = f"Tide change at {', '.join(_fmt12(t) for t in midday_tides)} keeps fish active"
    windows.append(TimeWindow("10:00 AM – 2:00 PM", midday_quality, midday_reason))

    # Afternoon (2-5 PM)
    afternoon_quality = "fair"
    afternoon_reason = "Afternoon sea breeze typical"
    if conditions.rain_chance_pct >= 50:
        afternoon_quality = "poor"
        afternoon_reason = "Storm risk — safety concern"
    afternoon_tides = [t for t in tide_events if "14" <= t[:2] <= "17"]
    if afternoon_tides and afternoon_quality != "poor":
        afternoon_quality = "good"
        afternoon_reason = f"Tide change at {', '.join(_fmt12(t) for t in afternoon_tides)}"
    windows.append(TimeWindow("2:00 PM – 5:00 PM", afternoon_quality, afternoon_reason))

    # Evening (5-8 PM)
    evening_quality = "good"
    evening_reason = "Wind dies, low light, evening feed"
    evening_tides = [t for t in tide_events if "17" <= t[:2] <= "20"]
    if evening_tides:
        evening_quality = "prime"
        evening_reason = f"Tide change at {', '.join(_fmt12(t) for t in evening_tides)} + low light = prime"
    if conditions.rain_chance_pct >= 60:
        evening_quality = "fair"
        evening_reason = "Possible lingering storms"
    windows.append(TimeWindow("5:00 PM – 8:00 PM", evening_quality, evening_reason))

    return windows


def _recommend_location(conditions: DayConditions) -> tuple[str, str]:
    """Recommend back lakes vs ICW vs bay based on conditions.
    Returns (location, reason)."""
    temp = conditions.buoy.water_temp_f
    wind = conditions.wind.speed_mph
    month = conditions.date.month
    pressure = conditions.pressure_trend

    # Cold water / winter — back lakes & deep holes
    if temp and temp < 60:
        return ("Back Lakes & Deep Holes",
                f"Water {temp:.0f}°F — fish concentrating in deep protected water. "
                "Look for mud-bottom potholes and residential canals that hold warmth.")

    # Cold front just passed (rising pressure) — sheltered water
    if pressure == "rising" and wind > 12:
        return ("Back Lakes & ICW (protected)",
                f"Post-front conditions with {wind:.0f} mph wind. Fish sheltered water — "
                "back lakes, ICW edges, and lee shorelines out of the wind.")

    # High wind — ICW and protected areas
    if wind > 18:
        return ("ICW & Protected Shorelines",
                f"Wind {wind:.0f} mph makes open bay dangerous. "
                "Fish the ICW, dredge spoil edges, and wind-protected shorelines.")
    if wind > 12:
        return ("ICW & Lee Shorelines",
                f"Wind {wind:.0f} mph — open bay is choppy. "
                "Focus on ICW structure and shorelines sheltered from {conditions.wind.direction} wind.")

    # Warm & calm — open bay flats (prime conditions)
    if temp and 68 <= temp <= 80 and wind <= WIND_IDEAL_MPH:
        return ("Open Bay Flats & Reefs",
                f"Ideal conditions — {temp:.0f}°F water, {wind:.0f} mph wind. "
                "Wade or drift the open bay flats, shell reefs, and grass edges.")

    # Spring / warming up — transition to flats
    if month in (3, 4, 5) and temp and temp >= 62:
        return ("Bay Flats & Grass Edges",
                f"Spring pattern — {temp:.0f}°F and warming. "
                "Fish are moving to shallow grass flats and shell pads. "
                "Wade the shorelines on incoming tide.")

    # Hot summer — deep structure
    if temp and temp > 82:
        return ("Deep Reefs, Channels & Night Spots",
                f"Water {temp:.0f}°F — too hot for shallow flats midday. "
                "Target deep shell reefs (4-8 ft), channel edges, and "
                "gas well channels. Consider dawn-only or night fishing.")

    # Fall — passes and drains (flounder migration)
    if month in (10, 11):
        return ("Passes, Drains & Jetties",
                "Fall pattern — flounder running to Gulf. "
                "Fish passes, ICW cuts, and drain mouths on outgoing tide. "
                "Also good for reds along marsh edges.")

    # Default moderate conditions
    if wind <= WIND_FISHABLE_MPH:
        return ("Bay Systems & Shorelines",
                f"Moderate conditions ({wind:.0f} mph wind, {temp:.0f}°F water). "
                "Work bay shorelines, scattered shell, and reef edges.")

    return ("Protected Water",
            f"Conditions variable — stick to protected water near access points.")


def _pick_key_factor(conditions: DayConditions) -> str:
    """One-line summary of what drives this day's score."""
    factors = []
    if conditions.wind.speed_mph <= WIND_IDEAL_MPH:
        factors.append("light wind")
    elif conditions.wind.speed_mph > WIND_FISHABLE_MPH:
        factors.append(f"wind {conditions.wind.speed_mph} mph")
    tide_events = len(conditions.tide.high_times) + len(conditions.tide.low_times)
    if tide_events >= 4:
        factors.append("strong tide movement")
    if conditions.pressure_trend == "falling":
        factors.append("falling pressure")
    if conditions.rain_chance_pct >= 50:
        factors.append("rain likely")
    return " + ".join(factors) if factors else "average conditions"


def score_day(conditions: DayConditions) -> DayForecast:
    """Score a single day across all fishing types."""
    subscores = {
        "tide": _score_tide(conditions),
        "wind": _score_wind(conditions.wind.speed_mph, WIND_IDEAL_MPH, WIND_FISHABLE_MPH),
        "pressure": _score_pressure(conditions.pressure_trend),
        "solunar": _score_solunar(conditions),
        "swell": _score_swell(
            conditions.buoy.wave_height_ft,
            WAVE_OFFSHORE_IDEAL_FT,
            WAVE_OFFSHORE_MAX_FT,
        ),
        "water_temp": _score_water_temp(conditions.buoy.water_temp_f),
        "cloud_cover": _score_cloud_cover(conditions.cloud_cover_pct),
        "weather_window": 8.0 if conditions.rain_chance_pct < 30 else 3.0,
    }

    # Offshore wind score uses stricter threshold
    offshore_subscores = {
        **subscores,
        "wind": _score_wind(
            conditions.wind.speed_mph, WIND_IDEAL_MPH, WIND_OFFSHORE_MAX_MPH
        ),
    }

    warnings = []
    if conditions.wind.speed_mph > 20:
        warnings.append(f"High wind: {conditions.wind.speed_mph} mph {conditions.wind.direction}")
    if conditions.rain_chance_pct >= 50:
        warnings.append("Rain/storms likely")
    if conditions.buoy.wave_height_ft > WAVE_OFFSHORE_MAX_FT:
        warnings.append(f"Rough seas: {conditions.buoy.wave_height_ft} ft")

    data_gaps = []
    if not conditions.has_weather:
        data_gaps.append("Extended forecast — wind/weather estimated from current conditions")
    if conditions.buoy.water_temp_f == 0:
        data_gaps.append("Water temperature unavailable")
    if not conditions.tide.high_times and not conditions.tide.low_times:
        data_gaps.append("Tide data missing")

    location_rec, location_reason = _recommend_location(conditions)
    time_windows = _build_time_windows(conditions)

    return DayForecast(
        date=conditions.date,
        inshore_score=_weighted_score(subscores, INSHORE_WEIGHTS),
        nearshore_score=_weighted_score(subscores, NEARSHORE_WEIGHTS),
        offshore_score=_weighted_score(offshore_subscores, OFFSHORE_WEIGHTS),
        best_species=_pick_species(conditions),
        best_window=_pick_best_window(conditions),
        worst_window=_pick_worst_window(conditions),
        key_factor=_pick_key_factor(conditions),
        location_rec=location_rec,
        location_reason=location_reason,
        time_windows=time_windows,
        conditions=conditions,
        warnings=warnings,
        data_gaps=data_gaps,
    )


def generate_forecast(area_key: str = "matagorda", num_days: int = 7) -> ForecastResult:
    """Generate a complete forecast for the given area.
    
    If no day in the initial window scores >= 6 inshore, extends up to 14 days
    to find a decent fishing day. Days beyond NWS coverage (7) have limited
    weather data and are marked accordingly.
    """
    GOOD_THRESHOLD = 6
    MAX_EXTEND = 14

    area = AREAS.get(area_key, {})
    conditions_list = fetch_all_conditions(area_key, num_days)
    days = [score_day(c) for c in conditions_list]

    # If no good day found, extend the search
    best_so_far = max((d.inshore_score for d in days), default=0)
    if best_so_far < GOOD_THRESHOLD and num_days < MAX_EXTEND:
        extra_days = MAX_EXTEND - num_days
        logger.info("No good day in %d-day window (best=%d), extending to %d days",
                     num_days, best_so_far, MAX_EXTEND)
        extended = fetch_all_conditions(area_key, MAX_EXTEND)
        # Only add the new days (skip ones we already have)
        for c in extended[num_days:]:
            days.append(score_day(c))

    best_inshore = max(days, key=lambda d: d.inshore_score) if days else None
    best_offshore = max(days, key=lambda d: d.offshore_score) if days else None

    return ForecastResult(
        area=area.get("name", area_key),
        generated_at=_fmt_generated_at(datetime.now(tz=CENTRAL)),
        days=days,
        best_inshore_day=best_inshore.date.isoformat() if best_inshore else None,
        best_offshore_day=best_offshore.date.isoformat() if best_offshore else None,
    )
