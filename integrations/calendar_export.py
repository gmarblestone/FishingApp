"""
Export fishing forecast to .ics calendar file for Google Calendar import.
Creates events on the best fishing days with scores and conditions.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

from icalendar import Calendar, Event

from fishing_forecast.config import DEFAULT_AREA
from fishing_forecast.scorer import generate_forecast

logger = logging.getLogger(__name__)

SCORE_THRESHOLD = 6  # Only create calendar events for days scoring this or above


def generate_ics(
    area_key: str = DEFAULT_AREA,
    output_path: str = "fishing_forecast.ics",
    min_score: int = SCORE_THRESHOLD,
) -> str:
    """Generate an .ics file with events for the best fishing days."""
    forecast = generate_forecast(area_key)
    cal = Calendar()
    cal.add("prodid", "-//Fishing Forecast//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", f"Fishing Forecast - {forecast.area}")

    events_created = 0

    for day in forecast.days:
        best_score = max(day.inshore_score, day.nearshore_score, day.offshore_score)
        if best_score < min_score:
            continue

        # Determine the best type for this day
        scores = {
            "Inshore": day.inshore_score,
            "Nearshore": day.nearshore_score,
            "Offshore": day.offshore_score,
        }
        best_type = max(scores, key=scores.get)

        event = Event()
        event.add(
            "summary",
            f"🎣 {best_type} {best_score}/10 — {day.best_species}",
        )

        description_lines = [
            f"Inshore: {day.inshore_score}/10 | Nearshore: {day.nearshore_score}/10 | Offshore: {day.offshore_score}/10",
            f"Best Species: {day.best_species}",
            f"Best Window: {day.best_window}",
            f"Key Factor: {day.key_factor}",
            f"Wind: {day.conditions.wind.speed_mph} mph {day.conditions.wind.direction}",
            f"Water Temp: {day.conditions.buoy.water_temp_f}°F",
            f"Waves: {day.conditions.buoy.wave_height_ft} ft",
        ]
        if day.warnings:
            description_lines.append(f"⚠️ {', '.join(day.warnings)}")
        description_lines.append(f"\nGenerated: {forecast.generated_at}")

        event.add("description", "\n".join(description_lines))
        event.add("dtstart", day.date)
        event.add("dtend", day.date + timedelta(days=1))
        event.add("dtstamp", datetime.now())

        # Color coding via categories
        if best_score >= 8:
            event.add("categories", ["Excellent Fishing"])
        elif best_score >= 6:
            event.add("categories", ["Good Fishing"])

        cal.add_component(event)
        events_created += 1

    output = Path(output_path)
    output.write_bytes(cal.to_ical())
    logger.info("Created %d events in %s", events_created, output_path)
    return str(output.resolve())
