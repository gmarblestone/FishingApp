"""
Fetches live data from public sources: NOAA tides, NDBC buoys, NWS weather.
All sources are free, no API keys required (except NWS needs a User-Agent).
"""

import logging
from datetime import date, datetime, timedelta, timezone

import requests

# US Central Time
try:
    import zoneinfo
    CENTRAL = zoneinfo.ZoneInfo("America/Chicago")
except Exception:
    CENTRAL = timezone(timedelta(hours=-5))

try:
    from fishing_forecast.config import (
        AREAS,
        NDBC_OBSERVATION_URL,
        NOAA_TIDES_API,
        NWS_API_BASE,
    )
    from fishing_forecast.models import (
        BuoyData,
        DayConditions,
        SolunarData,
        TideData,
        TidePoint,
        WindData,
    )
except ImportError:
    from config import (
        AREAS,
        NDBC_OBSERVATION_URL,
        NOAA_TIDES_API,
        NWS_API_BASE,
    )
    from models import (
        BuoyData,
        DayConditions,
        SolunarData,
        TideData,
        TidePoint,
        WindData,
    )

logger = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "FishingForecastApp/1.0 (fishing-forecast)"})
REQUEST_TIMEOUT = 15


def fetch_tides(station_id: str, begin: date, end: date) -> dict[str, TideData]:
    """Fetch NOAA tide predictions (hi/lo) for a date range. Returns {date_str: TideData}."""
    results: dict[str, TideData] = {}
    try:
        resp = SESSION.get(
            NOAA_TIDES_API,
            params={
                "begin_date": begin.strftime("%Y%m%d"),
                "end_date": end.strftime("%Y%m%d"),
                "station": station_id,
                "product": "predictions",
                "datum": "MLLW",
                "time_zone": "lst_ldt",
                "units": "english",
                "interval": "hilo",
                "format": "json",
                "application": "FishingForecast",
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        logger.exception("Failed to fetch tides for station %s", station_id)
        return results

    for pred in data.get("predictions", []):
        dt = datetime.strptime(pred["t"], "%Y-%m-%d %H:%M")
        day_str = dt.date().isoformat()
        if day_str not in results:
            results[day_str] = TideData()
        tide = results[day_str]
        time_str = dt.strftime("%H:%M")
        v = float(pred.get("v", 0))
        if pred.get("type") == "H":
            tide.high_times.append(time_str)
            tide.range_ft = max(tide.range_ft, v)
        else:
            tide.low_times.append(time_str)
            tide.range_ft = max(tide.range_ft, tide.range_ft - v) if tide.range_ft else 0

    return results


def fetch_hourly_tides(station_id: str, begin: date, end: date) -> dict[str, list[TidePoint]]:
    """Fetch hourly tide predictions for chart rendering. Returns {date_str: [TidePoint]}."""
    results: dict[str, list[TidePoint]] = {}
    try:
        resp = SESSION.get(
            NOAA_TIDES_API,
            params={
                "begin_date": begin.strftime("%Y%m%d"),
                "end_date": end.strftime("%Y%m%d"),
                "station": station_id,
                "product": "predictions",
                "datum": "MLLW",
                "time_zone": "lst_ldt",
                "units": "english",
                "interval": "h",
                "format": "json",
                "application": "FishingForecast",
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        logger.exception("Failed to fetch hourly tides for station %s", station_id)
        return results

    for pred in data.get("predictions", []):
        dt = datetime.strptime(pred["t"], "%Y-%m-%d %H:%M")
        day_str = dt.date().isoformat()
        if day_str not in results:
            results[day_str] = []
        results[day_str].append(TidePoint(time=dt.strftime("%H:%M"), height_ft=float(pred.get("v", 0))))

    return results


def fetch_buoy(station_id: str) -> BuoyData:
    """Fetch latest NDBC buoy observation."""
    try:
        url = NDBC_OBSERVATION_URL.format(station=station_id)
        resp = SESSION.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        lines = resp.text.strip().split("\n")
        if len(lines) < 3:
            return BuoyData()
        # Header in line 0, units in line 1, data starts line 2
        headers = lines[0].split()
        values = lines[2].split()
        data_map = dict(zip(headers, values))

        def safe_float(key: str) -> float:
            val = data_map.get(key, "MM")
            return float(val) if val != "MM" else 0.0

        wave_m = safe_float("WVHT")
        water_c = safe_float("WTMP")
        return BuoyData(
            wave_height_ft=round(wave_m * 3.28084, 1),
            wave_period_sec=safe_float("DPD"),
            water_temp_f=round(water_c * 9 / 5 + 32, 1) if water_c else 0.0,
            pressure_mb=safe_float("PRES"),
        )
    except Exception:
        logger.exception("Failed to fetch buoy %s", station_id)
        return BuoyData()


def fetch_nws_forecast(gridpoint: str, days: int = 7) -> list[dict]:
    """Fetch NWS 7-day forecast from api.weather.gov. Returns list of period dicts."""
    try:
        url = f"{NWS_API_BASE}/gridpoints/{gridpoint}/forecast"
        resp = SESSION.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        periods = resp.json().get("properties", {}).get("periods", [])
        return periods[:days * 2]  # day + night periods
    except Exception:
        logger.exception("Failed to fetch NWS forecast for %s", gridpoint)
        return []


def fetch_nws_marine(zone_id: str) -> str:
    """Fetch NWS marine zone forecast text."""
    try:
        url = f"{NWS_API_BASE}/zones/forecast/{zone_id}/forecast"
        resp = SESSION.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        periods = resp.json().get("properties", {}).get("periods", [])
        return "\n".join(p.get("detailedForecast", "") for p in periods[:4])
    except Exception:
        logger.exception("Failed to fetch marine forecast for zone %s", zone_id)
        return ""


def _parse_wind_from_nws(period: dict) -> WindData:
    """Extract wind info from an NWS forecast period."""
    speed_str = period.get("windSpeed", "0 mph")
    direction = period.get("windDirection", "")
    # "10 to 15 mph" → take the higher number
    parts = speed_str.replace(" mph", "").split(" to ")
    try:
        speeds = [int(p.strip()) for p in parts]
        speed = max(speeds)
    except ValueError:
        speed = 0
    return WindData(speed_mph=speed, gust_mph=0, direction=direction)


def fetch_all_conditions(
    area_key: str, num_days: int = 7
) -> list[DayConditions]:
    """Fetch and assemble conditions for each day in the forecast window."""
    area = AREAS.get(area_key)
    if not area:
        logger.error("Unknown area: %s", area_key)
        return []

    today = datetime.now(tz=CENTRAL).date()
    end = today + timedelta(days=num_days - 1)

    # Tides — use first station
    tides_by_day = fetch_tides(area["tide_stations"][0], today, end)

    # Hourly tides for charts
    hourly_by_day = fetch_hourly_tides(area["tide_stations"][0], today, end)

    # Buoy — latest observation (applies to all days as baseline)
    buoy = fetch_buoy(area["buoy_ids"][0])

    # NWS 7-day forecast
    nws_periods = fetch_nws_forecast(area["nws_gridpoint"], num_days)

    # Build per-day conditions
    conditions_list: list[DayConditions] = []
    for i in range(num_days):
        d = today + timedelta(days=i)
        day_str = d.isoformat()

        tide = tides_by_day.get(day_str, TideData())
        tide.hourly = hourly_by_day.get(day_str, [])

        # Match NWS period to this day (daytime period)
        wind = WindData()
        cloud_cover = 0
        rain_chance = 0
        air_high = 0.0
        air_low = 0.0
        for p in nws_periods:
            p_start = p.get("startTime", "")
            if day_str in p_start:
                if p.get("isDaytime", True):
                    wind = _parse_wind_from_nws(p)
                    air_high = float(p.get("temperature", 0))
                    short = p.get("shortForecast", "").lower()
                    if "cloud" in short or "overcast" in short:
                        cloud_cover = 75
                    elif "partly" in short:
                        cloud_cover = 40
                    elif "sunny" in short or "clear" in short:
                        cloud_cover = 10
                    if "rain" in short or "shower" in short or "thunder" in short:
                        rain_chance = 60
                else:
                    air_low = float(p.get("temperature", 0))

        # Pressure trend from buoy (simplified — single snapshot)
        pressure_trend = "stable"
        if buoy.pressure_mb:
            if buoy.pressure_mb < 1010:
                pressure_trend = "falling"
            elif buoy.pressure_mb > 1016:
                pressure_trend = "rising"

        conditions_list.append(
            DayConditions(
                date=d,
                tide=tide,
                wind=wind,
                buoy=buoy,
                solunar=SolunarData(),  # filled by scorer if solunar API available
                pressure_trend=pressure_trend,
                cloud_cover_pct=cloud_cover,
                rain_chance_pct=rain_chance,
                air_temp_high_f=air_high,
                air_temp_low_f=air_low,
            )
        )

    return conditions_list
