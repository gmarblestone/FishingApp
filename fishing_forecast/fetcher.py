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
        NDBC_SPEC_URL,
        NOAA_TIDES_API,
        NWS_API_BASE,
    )
    from fishing_forecast.models import (
        BuoyData,
        DayConditions,
        SolunarData,
        TideData,
        TidePoint,
        WaterLevelData,
        WindData,
    )
except ImportError:
    from config import (
        AREAS,
        NDBC_OBSERVATION_URL,
        NDBC_SPEC_URL,
        NOAA_TIDES_API,
        NWS_API_BASE,
    )
    from models import (
        BuoyData,
        DayConditions,
        SolunarData,
        TideData,
        TidePoint,
        WaterLevelData,
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


def fetch_water_level_deviation(station_id: str) -> WaterLevelData:
    """Compare recent observed water levels to NOAA predictions to determine
    if the bay is running higher or lower than nominal.

    Fetches the last 24 hours of observed water levels and predictions at
    hourly intervals, computes the mean deviation, and classifies as
    high / low / normal.
    """
    result = WaterLevelData()
    end = datetime.now(tz=CENTRAL)
    begin = end - timedelta(hours=24)
    begin_str = begin.strftime("%Y%m%d %H:%M")
    end_str = end.strftime("%Y%m%d %H:%M")
    base_params = {
        "begin_date": begin_str,
        "end_date": end_str,
        "station": station_id,
        "datum": "MLLW",
        "time_zone": "lst_ldt",
        "units": "english",
        "interval": "h",
        "format": "json",
        "application": "FishingForecast",
    }

    try:
        # Fetch observed water levels
        obs_resp = SESSION.get(
            NOAA_TIDES_API,
            params={**base_params, "product": "water_level"},
            timeout=REQUEST_TIMEOUT,
        )
        obs_resp.raise_for_status()
        obs_data = obs_resp.json().get("data", [])

        # Fetch predicted levels for same window
        pred_resp = SESSION.get(
            NOAA_TIDES_API,
            params={**base_params, "product": "predictions"},
            timeout=REQUEST_TIMEOUT,
        )
        pred_resp.raise_for_status()
        pred_data = pred_resp.json().get("predictions", [])
    except Exception:
        logger.exception("Failed to fetch water level data for station %s", station_id)
        return result

    if not obs_data or not pred_data:
        return result

    # Index predictions by timestamp for quick lookup
    pred_by_time: dict[str, float] = {}
    for p in pred_data:
        pred_by_time[p["t"]] = float(p.get("v", 0))

    # Compute mean observed and mean predicted over matched timestamps
    obs_vals: list[float] = []
    pred_vals: list[float] = []
    for o in obs_data:
        v = o.get("v", "")
        if v == "" or v is None:
            continue
        t = o["t"]
        if t in pred_by_time:
            obs_vals.append(float(v))
            pred_vals.append(pred_by_time[t])

    if not obs_vals:
        return result

    obs_avg = sum(obs_vals) / len(obs_vals)
    pred_avg = sum(pred_vals) / len(pred_vals)
    deviation = round(obs_avg - pred_avg, 2)

    # Classify: > +0.2 ft = high, < -0.2 ft = low, else normal
    if deviation >= 0.2:
        status = "high"
    elif deviation <= -0.2:
        status = "low"
    else:
        status = "normal"

    return WaterLevelData(
        observed_avg_ft=round(obs_avg, 2),
        predicted_avg_ft=round(pred_avg, 2),
        deviation_ft=deviation,
        status=status,
        has_data=True,
    )


def fetch_buoy(station_id: str) -> BuoyData:
    """Fetch latest NDBC buoy observation. Scans recent rows for non-MM values.
    Also fetches spectral data for swell/wind-wave breakdown and wave spread."""
    try:
        url = NDBC_OBSERVATION_URL.format(station=station_id)
        resp = SESSION.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        lines = resp.text.strip().split("\n")
        if len(lines) < 3:
            return BuoyData()
        headers = lines[0].split()

        wave_m = 0.0
        wave_period = 0.0
        water_c = 0.0
        pressure = 0.0
        mwd = 0.0

        # Scan up to 24 recent observations to find non-MM values
        for line in lines[2:26]:
            values = line.split()
            data_map = dict(zip(headers, values))

            def safe_float(key: str) -> float:
                val = data_map.get(key, "MM")
                return float(val) if val != "MM" else 0.0

            if not wave_m:
                wave_m = safe_float("WVHT")
                if wave_m:
                    wave_period = safe_float("DPD")
                    if not mwd:
                        mwd = safe_float("MWD")
            if not mwd:
                mwd = safe_float("MWD")
            if not water_c:
                water_c = safe_float("WTMP")
            if not pressure:
                pressure = safe_float("PRES")
            if wave_m and water_c and pressure and mwd:
                break

        # Fetch spectral data for swell/wind-wave breakdown
        swell_m = 0.0
        swell_dir = 0.0
        ww_m = 0.0
        ww_dir = 0.0
        try:
            spec_url = NDBC_SPEC_URL.format(station=station_id)
            spec_resp = SESSION.get(spec_url, timeout=REQUEST_TIMEOUT)
            spec_resp.raise_for_status()
            spec_lines = spec_resp.text.strip().split("\n")
            if len(spec_lines) >= 3:
                spec_headers = spec_lines[0].split()
                for spec_line in spec_lines[2:10]:
                    spec_values = spec_line.split()
                    spec_map = dict(zip(spec_headers, spec_values))

                    def spec_float(key: str) -> float:
                        val = spec_map.get(key, "MM")
                        return float(val) if val != "MM" else 0.0

                    if not swell_m:
                        swell_m = spec_float("SwH")
                    if not swell_dir:
                        swell_dir = spec_float("SwD")
                    if not ww_m:
                        ww_m = spec_float("WWH")
                    if not ww_dir:
                        ww_dir = spec_float("WWD")
                    if swell_m and swell_dir and ww_m and ww_dir:
                        break
        except Exception:
            logger.debug("No spectral data for buoy %s", station_id)

        # Calculate wave spread (angular difference between swell and wind waves)
        wave_spread = 0.0
        if swell_dir and ww_dir:
            diff = abs(swell_dir - ww_dir)
            wave_spread = min(diff, 360.0 - diff)

        return BuoyData(
            wave_height_ft=round(wave_m * 3.28084, 1),
            wave_period_sec=wave_period,
            water_temp_f=round(water_c * 9 / 5 + 32, 1) if water_c else 0.0,
            pressure_mb=pressure,
            swell_height_ft=round(swell_m * 3.28084, 1),
            wind_wave_height_ft=round(ww_m * 3.28084, 1),
            wave_direction_deg=mwd,
            swell_direction_deg=swell_dir,
            wave_spread_deg=round(wave_spread, 0),
        )
    except Exception:
        logger.exception("Failed to fetch buoy %s", station_id)
        return BuoyData()


def fetch_inshore_met(station_id: str) -> dict:
    """Fetch latest NDBC inshore met station data (wind, pressure, water temp).

    Returns a dict with available readings; missing values are 0.0.
    Scans up to 24 recent observations to find non-MM values.
    """
    result = {"water_temp_f": 0.0, "pressure_mb": 0.0, "wind_speed_mph": 0.0,
              "wind_gust_mph": 0.0, "wind_dir": ""}
    try:
        url = NDBC_OBSERVATION_URL.format(station=station_id)
        resp = SESSION.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        lines = resp.text.strip().split("\n")
        if len(lines) < 3:
            return result
        headers = lines[0].split()

        # Scan recent observations to find non-MM values
        for line in lines[2:26]:
            values = line.split()
            data_map = dict(zip(headers, values))

            def safe_float(key: str) -> float:
                val = data_map.get(key, "MM")
                return float(val) if val != "MM" else 0.0

            if not result["water_temp_f"]:
                wtmp = safe_float("WTMP")
                if wtmp:
                    result["water_temp_f"] = round(wtmp * 9 / 5 + 32, 1)

            if not result["pressure_mb"]:
                pres = safe_float("PRES")
                if pres:
                    result["pressure_mb"] = pres

            if not result["wind_speed_mph"]:
                wspd = safe_float("WSPD")
                if wspd:
                    result["wind_speed_mph"] = round(wspd * 2.23694, 1)
                    gst = safe_float("GST")
                    result["wind_gust_mph"] = round(gst * 2.23694, 1) if gst else 0.0
                    wdir = data_map.get("WDIR", "MM")
                    result["wind_dir"] = wdir if wdir != "MM" else ""

            # Stop once all fields are populated
            if result["water_temp_f"] and result["pressure_mb"] and result["wind_speed_mph"]:
                break

        return result
    except Exception:
        logger.exception("Failed to fetch inshore met %s", station_id)
        return result


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


def fetch_nws_marine_waves(marine_gridpoint: str, num_days: int = 7) -> dict[str, float]:
    """Fetch wave height forecast from NWS marine gridpoint data.

    Returns {date_iso: max_wave_height_ft} for each day.
    This provides area-specific wave forecasts vs distant buoy observations.
    """
    results: dict[str, float] = {}
    if not marine_gridpoint:
        return results
    try:
        url = f"{NWS_API_BASE}/gridpoints/{marine_gridpoint}"
        resp = SESSION.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        wave_data = resp.json().get("properties", {}).get("waveHeight", {})
        for entry in wave_data.get("values", []):
            val_m = entry.get("value", 0)
            if not val_m:
                continue
            val_ft = round(val_m * 3.28084, 1)
            # Parse ISO time to get the date
            time_str = entry.get("validTime", "")
            day_str = time_str[:10]  # "2026-05-07"
            # Keep the max wave height per day
            if day_str not in results or val_ft > results[day_str]:
                results[day_str] = val_ft
        logger.info("NWS marine waves: %d days from %s", len(results), marine_gridpoint)
    except Exception:
        logger.debug("No NWS marine wave data from %s", marine_gridpoint)
    return results


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

    # Water level deviation (observed vs predicted) — single snapshot applies to all days
    water_level = fetch_water_level_deviation(area["tide_stations"][0])

    # Buoy — latest observation (applies to all days as baseline)
    # Try each configured buoy until one returns data
    buoy = BuoyData()
    for bid in area["buoy_ids"]:
        buoy = fetch_buoy(bid)
        if buoy.wave_height_ft or buoy.water_temp_f:
            break

    # Inshore met stations — supplement buoy with local water temp & pressure
    inshore_stations = area.get("inshore_stations", [])
    for sid in inshore_stations:
        met = fetch_inshore_met(sid)
        if not buoy.water_temp_f and met["water_temp_f"]:
            buoy.water_temp_f = met["water_temp_f"]
        if not buoy.pressure_mb and met["pressure_mb"]:
            buoy.pressure_mb = met["pressure_mb"]
        if buoy.water_temp_f and buoy.pressure_mb:
            break

    # NWS 7-day forecast
    nws_periods = fetch_nws_forecast(area["nws_gridpoint"], num_days)

    # NWS marine wave forecast — area-specific wave heights per day
    marine_gp = area.get("nws_marine_gridpoint", "")
    marine_waves = fetch_nws_marine_waves(marine_gp, num_days)

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
        has_weather = False
        night_period = None
        for p in nws_periods:
            p_start = p.get("startTime", "")
            if day_str in p_start:
                if p.get("isDaytime", True):
                    has_weather = True
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
                    if not night_period:
                        night_period = p

        # Fall back to night period if no daytime data (e.g., late in the day)
        if not has_weather and night_period:
            has_weather = True
            wind = _parse_wind_from_nws(night_period)
            air_high = air_low or float(night_period.get("temperature", 0))
            short = night_period.get("shortForecast", "").lower()
            if "cloud" in short or "overcast" in short:
                cloud_cover = 75
            elif "partly" in short:
                cloud_cover = 40
            elif "sunny" in short or "clear" in short:
                cloud_cover = 10
            if "rain" in short or "shower" in short or "thunder" in short:
                rain_chance = 60

        # Pressure trend from buoy (simplified — single snapshot)
        pressure_trend = "stable"
        if buoy.pressure_mb:
            if buoy.pressure_mb < 1010:
                pressure_trend = "falling"
            elif buoy.pressure_mb > 1016:
                pressure_trend = "rising"

        # Use NWS marine wave forecast if available (area-specific, per-day)
        # Falls back to buoy observation if no marine data for this day
        day_buoy = buoy
        nws_wave_ft = marine_waves.get(day_str)
        if nws_wave_ft is not None:
            from dataclasses import replace as dc_replace
            day_buoy = dc_replace(buoy, wave_height_ft=nws_wave_ft)

        conditions_list.append(
            DayConditions(
                date=d,
                tide=tide,
                wind=wind,
                buoy=day_buoy,
                solunar=SolunarData(),  # filled by scorer if solunar API available
                pressure_trend=pressure_trend,
                cloud_cover_pct=cloud_cover,
                rain_chance_pct=rain_chance,
                air_temp_high_f=air_high,
                air_temp_low_f=air_low,
                water_level=water_level,
                has_weather=has_weather,
            )
        )

    return conditions_list
