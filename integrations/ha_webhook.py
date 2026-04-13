"""
Push fishing forecast data to Home Assistant via its REST API.
Requires a long-lived access token set in config or HA_TOKEN env var.
"""

import logging
import os

import requests

from fishing_forecast.config import DEFAULT_AREA, HA_TOKEN, HA_URL
from fishing_forecast.scorer import generate_forecast

logger = logging.getLogger(__name__)


def get_ha_headers() -> dict:
    token = os.environ.get("HA_TOKEN", HA_TOKEN)
    if not token:
        raise ValueError(
            "HA_TOKEN not set. Create a long-lived access token in HA "
            "→ Profile → Long-Lived Access Tokens, then set the HA_TOKEN "
            "environment variable."
        )
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def push_sensor(entity_id: str, state: str, attributes: dict) -> bool:
    """Create or update a sensor entity in Home Assistant."""
    url = f"{HA_URL}/api/states/{entity_id}"
    payload = {"state": state, "attributes": attributes}
    try:
        resp = requests.post(url, json=payload, headers=get_ha_headers(), timeout=10)
        resp.raise_for_status()
        logger.info("Updated %s = %s", entity_id, state)
        return True
    except Exception:
        logger.exception("Failed to push %s to HA", entity_id)
        return False


def push_forecast_to_ha(area_key: str = DEFAULT_AREA):
    """Generate forecast and push all sensors to Home Assistant."""
    forecast = generate_forecast(area_key)

    if not forecast.days:
        logger.error("No forecast data to push")
        return

    today = forecast.days[0]

    # Main score sensor — state is the inshore score (most visible)
    push_sensor(
        "sensor.fishing_inshore_score",
        str(today.inshore_score),
        {
            "friendly_name": "Fishing - Inshore Score",
            "icon": "mdi:fish",
            "unit_of_measurement": "/10",
            "area": forecast.area,
            "best_species": today.best_species,
            "best_window": today.best_window,
            "key_factor": today.key_factor,
            "wind": f"{today.conditions.wind.speed_mph} mph {today.conditions.wind.direction}",
            "water_temp": f"{today.conditions.buoy.water_temp_f}°F",
            "wave_height": f"{today.conditions.buoy.wave_height_ft} ft",
            "pressure_trend": today.conditions.pressure_trend,
            "warnings": ", ".join(today.warnings) if today.warnings else "None",
            "generated_at": forecast.generated_at,
        },
    )

    push_sensor(
        "sensor.fishing_nearshore_score",
        str(today.nearshore_score),
        {
            "friendly_name": "Fishing - Nearshore Score",
            "icon": "mdi:waves",
            "unit_of_measurement": "/10",
        },
    )

    push_sensor(
        "sensor.fishing_offshore_score",
        str(today.offshore_score),
        {
            "friendly_name": "Fishing - Offshore Score",
            "icon": "mdi:ferry",
            "unit_of_measurement": "/10",
            "wave_height": f"{today.conditions.buoy.wave_height_ft} ft",
            "wave_period": f"{today.conditions.buoy.wave_period_sec}s",
        },
    )

    push_sensor(
        "sensor.fishing_best_species",
        today.best_species,
        {
            "friendly_name": "Fishing - Best Species Today",
            "icon": "mdi:fishbowl",
        },
    )

    # Week outlook — best days
    push_sensor(
        "sensor.fishing_best_inshore_day",
        forecast.best_inshore_day or "unknown",
        {
            "friendly_name": "Fishing - Best Inshore Day",
            "icon": "mdi:calendar-star",
        },
    )

    push_sensor(
        "sensor.fishing_best_offshore_day",
        forecast.best_offshore_day or "unknown",
        {
            "friendly_name": "Fishing - Best Offshore Day",
            "icon": "mdi:calendar-star",
        },
    )

    # Push each day as a separate sensor for the week view
    for day in forecast.days:
        day_str = day.date.isoformat()
        safe_date = day_str.replace("-", "_")
        push_sensor(
            f"sensor.fishing_day_{safe_date}",
            str(day.inshore_score),
            {
                "friendly_name": f"Fishing {day_str}",
                "icon": "mdi:fish",
                "date": day_str,
                "inshore": day.inshore_score,
                "nearshore": day.nearshore_score,
                "offshore": day.offshore_score,
                "species": day.best_species,
                "key_factor": day.key_factor,
                "warnings": ", ".join(day.warnings) if day.warnings else "None",
            },
        )

    logger.info("All sensors pushed to HA for %s", forecast.area)
