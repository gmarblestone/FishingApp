"""
Lightweight REST server that Home Assistant polls for fishing forecast data.
Exposes /api/forecast as JSON — configure HA REST sensor to point here.
"""

import json
import logging

from flask import Flask, jsonify, request

from fishing_forecast.config import DEFAULT_AREA, SERVER_HOST, SERVER_PORT
from fishing_forecast.scorer import generate_forecast

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache the latest forecast to avoid hammering APIs on every HA poll
_cache: dict = {}


def _get_or_refresh(area: str, force: bool = False) -> dict:
    if area not in _cache or force:
        logger.info("Generating fresh forecast for %s", area)
        result = generate_forecast(area)
        _cache[area] = result.to_dict()
    return _cache[area]


@app.route("/api/forecast")
def forecast():
    area = request.args.get("area", DEFAULT_AREA)
    force = request.args.get("refresh", "").lower() == "true"
    data = _get_or_refresh(area, force)
    return jsonify(data)


@app.route("/api/forecast/today")
def today():
    """Simplified endpoint for HA sensor — returns today's scores only."""
    area = request.args.get("area", DEFAULT_AREA)
    data = _get_or_refresh(area)
    days = data.get("days", [])
    if not days:
        return jsonify({"error": "No forecast data"})
    today_data = days[0]
    return jsonify(
        {
            "date": today_data["date"],
            "inshore_score": today_data["inshore_score"],
            "nearshore_score": today_data["nearshore_score"],
            "offshore_score": today_data["offshore_score"],
            "best_species": today_data["best_species"],
            "best_window": today_data["best_window"],
            "key_factor": today_data["key_factor"],
            "wind_speed": today_data["conditions"]["wind"]["speed_mph"],
            "wind_dir": today_data["conditions"]["wind"]["direction"],
            "water_temp": today_data["conditions"]["buoy"]["water_temp_f"],
            "wave_height": today_data["conditions"]["buoy"]["wave_height_ft"],
            "pressure": today_data["conditions"]["buoy"]["pressure_mb"],
            "pressure_trend": today_data["conditions"]["pressure_trend"],
            "warnings": today_data["warnings"],
            "area": data["area"],
            "generated_at": data["generated_at"],
        }
    )


@app.route("/api/forecast/week")
def week_summary():
    """Returns 7-day summary for HA calendar or dashboard cards."""
    area = request.args.get("area", DEFAULT_AREA)
    data = _get_or_refresh(area)
    summary = []
    for d in data.get("days", []):
        summary.append(
            {
                "date": d["date"],
                "inshore": d["inshore_score"],
                "nearshore": d["nearshore_score"],
                "offshore": d["offshore_score"],
                "species": d["best_species"],
                "key_factor": d["key_factor"],
                "warnings": d["warnings"],
            }
        )
    return jsonify(
        {
            "area": data["area"],
            "generated_at": data["generated_at"],
            "best_inshore_day": data["best_inshore_day"],
            "best_offshore_day": data["best_offshore_day"],
            "days": summary,
        }
    )


@app.route("/api/refresh", methods=["POST"])
def refresh():
    """Force refresh the forecast cache."""
    area = request.args.get("area", DEFAULT_AREA)
    data = _get_or_refresh(area, force=True)
    return jsonify({"status": "refreshed", "generated_at": data["generated_at"]})


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


def main():
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False)


if __name__ == "__main__":
    main()
