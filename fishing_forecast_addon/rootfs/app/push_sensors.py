"""Push forecast data as HA sensor entities via the Supervisor REST API."""

import json
import urllib.request


def _post_state(ha_api: str, ha_token: str, entity_id: str, state, attributes: dict):
    url = f"{ha_api}/states/{entity_id}"
    data = json.dumps({"state": state, "attributes": attributes}).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {ha_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"  Failed to set {entity_id}: {e}")


def push_sensors(forecast: dict, ha_api: str, ha_token: str):
    days = forecast.get("days", [])
    if not days:
        print("No forecast days to push")
        return

    today = days[0]
    cond = today.get("conditions", {})
    buoy = cond.get("buoy", {})
    wind = cond.get("wind", {})

    # Find best days
    best_inshore = max(days, key=lambda d: d.get("inshore_score", 0))
    best_offshore = max(days, key=lambda d: d.get("offshore_score", 0))

    off_score = today.get("offshore_score", 0)
    off_status = "GO" if off_score >= 6 else "MARGINAL" if off_score >= 4 else "NO-GO"

    sensors = [
        ("sensor.fishing_inshore_score", today.get("inshore_score", 0), {
            "friendly_name": "Fishing — Inshore",
            "icon": "mdi:fish",
            "unit_of_measurement": "/10",
            "species": today.get("best_species", ""),
            "location": today.get("location_rec", ""),
            "location_reason": today.get("location_reason", ""),
            "best_window": today.get("best_window", ""),
            "worst_window": today.get("worst_window", ""),
            "key_factor": today.get("key_factor", ""),
            "area": forecast.get("area", ""),
            "generated_at": forecast.get("generated_at", ""),
        }),
        ("sensor.fishing_nearshore_score", today.get("nearshore_score", 0), {
            "friendly_name": "Fishing — Nearshore",
            "icon": "mdi:fish",
            "unit_of_measurement": "/10",
        }),
        ("sensor.fishing_offshore_score", off_score, {
            "friendly_name": "Fishing — Offshore",
            "icon": "mdi:ferry",
            "unit_of_measurement": "/10",
            "status": off_status,
            "wave_height": buoy.get("wave_height_ft", 0),
            "wave_period": buoy.get("wave_period_sec", 0),
        }),
        ("sensor.fishing_water_temp", round(buoy.get("water_temp_f", 0), 1), {
            "friendly_name": "Fishing — Water Temp",
            "icon": "mdi:thermometer-water",
            "unit_of_measurement": "°F",
        }),
        ("sensor.fishing_wind", round(wind.get("speed_mph", 0)), {
            "friendly_name": "Fishing — Wind",
            "icon": "mdi:weather-windy",
            "unit_of_measurement": "mph",
            "direction": wind.get("direction", ""),
            "gust_mph": wind.get("gust_mph", 0),
        }),
        ("sensor.fishing_waves", round(buoy.get("wave_height_ft", 0), 1), {
            "friendly_name": "Fishing — Waves",
            "icon": "mdi:waves",
            "unit_of_measurement": "ft",
            "period_sec": buoy.get("wave_period_sec", 0),
        }),
        ("sensor.fishing_pressure", round(buoy.get("pressure_mb", 0), 1), {
            "friendly_name": "Fishing — Pressure",
            "icon": "mdi:gauge",
            "unit_of_measurement": "mb",
            "trend": cond.get("pressure_trend", ""),
        }),
        ("sensor.fishing_species", today.get("best_species", "Unknown"), {
            "friendly_name": "Fishing — Target Species",
            "icon": "mdi:fish",
        }),
        ("sensor.fishing_location", today.get("location_rec", "Unknown"), {
            "friendly_name": "Fishing — Where to Fish",
            "icon": "mdi:map-marker",
            "reason": today.get("location_reason", ""),
        }),
        ("sensor.fishing_best_window", today.get("best_window", "Unknown"), {
            "friendly_name": "Fishing — Best Time",
            "icon": "mdi:clock-outline",
            "worst_window": today.get("worst_window", ""),
        }),
        ("sensor.fishing_best_inshore_day", best_inshore.get("date", ""), {
            "friendly_name": "Fishing — Best Inshore Day",
            "icon": "mdi:star",
            "score": best_inshore.get("inshore_score", 0),
            "species": best_inshore.get("best_species", ""),
            "location": best_inshore.get("location_rec", ""),
        }),
        ("sensor.fishing_best_offshore_day", best_offshore.get("date", ""), {
            "friendly_name": "Fishing — Best Offshore Day",
            "icon": "mdi:star",
            "score": best_offshore.get("offshore_score", 0),
            "wave_height": best_offshore.get("conditions", {}).get("buoy", {}).get("wave_height_ft", 0),
        }),
        ("sensor.fishing_forecast_week", f"{len(days)} days", {
            "friendly_name": "Fishing — Weekly Forecast",
            "icon": "mdi:calendar-week",
            "area": forecast.get("area", ""),
            "generated": forecast.get("generated_at", ""),
            "days": [{
                "date": d.get("date", ""),
                "inshore": d.get("inshore_score", 0),
                "nearshore": d.get("nearshore_score", 0),
                "offshore": d.get("offshore_score", 0),
                "species": d.get("best_species", ""),
                "location": d.get("location_rec", ""),
                "wind_mph": round(d.get("conditions", {}).get("wind", {}).get("speed_mph", 0)),
                "waves_ft": round(d.get("conditions", {}).get("buoy", {}).get("wave_height_ft", 0), 1),
                "best_window": d.get("best_window", ""),
            } for d in days],
        }),
        ("sensor.fishing_warnings", len(today.get("warnings", [])), {
            "friendly_name": "Fishing — Warnings",
            "icon": "mdi:alert" if today.get("warnings") else "mdi:check-circle",
            "warnings": today.get("warnings", []),
        }),
    ]

    for entity_id, state, attrs in sensors:
        _post_state(ha_api, ha_token, entity_id, state, attrs)

    print(f"Pushed {len(sensors)} sensors to Home Assistant")
