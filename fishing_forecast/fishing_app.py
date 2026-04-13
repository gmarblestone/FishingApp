"""
AppDaemon app — runs the fishing forecast engine entirely inside Home Assistant.

Sensors are set directly via self.set_state(). HTML report is written to
/config/www/fishing_forecast.html and accessible at /local/fishing_forecast.html.
No external server required.
"""

import json
import logging
import traceback

try:
    import appdaemon.plugins.hass.hassapi as hass

    _HAS_APPDAEMON = True
except ImportError:
    _HAS_APPDAEMON = False

try:
    from fishing_forecast.scorer import generate_forecast
    from fishing_forecast.models import ForecastResult
except ImportError:
    from scorer import generate_forecast
    from models import ForecastResult

logger = logging.getLogger(__name__)


class FishingForecastApp(hass.Hass if _HAS_APPDAEMON else object):
    """AppDaemon app that fetches live data, scores days, and publishes HA sensors."""

    def initialize(self):
        self.area = self.args.get("area", "matagorda")
        self.report_path = self.args.get("report_path", "/config/www/fishing_forecast.html")

        refresh_times = self.args.get("refresh_times", ["05:00:00", "12:00:00"])
        for t in refresh_times:
            self.run_daily(self._scheduled_refresh, t)
            self.log(f"Scheduled forecast refresh at {t}")

        self.listen_event(self._handle_refresh_event, "fishing_forecast_refresh")

        self.log(f"Fishing Forecast initializing — area: {self.area}")
        self._refresh()

    # ── Triggers ─────────────────────────────────────────────────────────────

    def _scheduled_refresh(self, kwargs):
        self._refresh()

    def _handle_refresh_event(self, event_name, data, kwargs):
        area = data.get("area", self.area) if data else self.area
        self._refresh(area)

    # ── Core ─────────────────────────────────────────────────────────────────

    def _refresh(self, area=None):
        area = area or self.area
        try:
            forecast = generate_forecast(area)
            self._update_sensors(forecast)
            self._write_report(forecast)
            self.log(f"Forecast updated: {len(forecast.days)} days for {forecast.area}")
        except Exception:
            self.log(f"Forecast refresh failed:\n{traceback.format_exc()}", level="ERROR")

    # ── Sensors ──────────────────────────────────────────────────────────────

    def _update_sensors(self, forecast: ForecastResult):
        if not forecast.days:
            return

        today = forecast.days[0]
        best_inshore = max(forecast.days, key=lambda d: d.inshore_score)
        best_offshore = max(forecast.days, key=lambda d: d.offshore_score)

        # ── Today's scores ───────────────────────────────────────────────────

        self.set_state(
            "sensor.fishing_inshore_score",
            state=today.inshore_score,
            attributes={
                "friendly_name": "Fishing — Inshore",
                "icon": "mdi:fish",
                "unit_of_measurement": "/10",
                "species": today.best_species,
                "location": today.location_rec,
                "location_reason": today.location_reason,
                "best_window": today.best_window,
                "worst_window": today.worst_window,
                "key_factor": today.key_factor,
                "area": forecast.area,
                "generated_at": forecast.generated_at,
            },
        )

        self.set_state(
            "sensor.fishing_nearshore_score",
            state=today.nearshore_score,
            attributes={
                "friendly_name": "Fishing — Nearshore",
                "icon": "mdi:fish",
                "unit_of_measurement": "/10",
            },
        )

        off_status = (
            "GO" if today.offshore_score >= 6
            else "MARGINAL" if today.offshore_score >= 4
            else "NO-GO"
        )
        self.set_state(
            "sensor.fishing_offshore_score",
            state=today.offshore_score,
            attributes={
                "friendly_name": "Fishing — Offshore",
                "icon": "mdi:ferry",
                "unit_of_measurement": "/10",
                "status": off_status,
                "wave_height": today.conditions.buoy.wave_height_ft,
                "wave_period": today.conditions.buoy.wave_period_sec,
            },
        )

        # ── Conditions ───────────────────────────────────────────────────────

        self.set_state(
            "sensor.fishing_water_temp",
            state=round(today.conditions.buoy.water_temp_f, 1),
            attributes={
                "friendly_name": "Fishing — Water Temp",
                "icon": "mdi:thermometer-water",
                "unit_of_measurement": "°F",
            },
        )

        self.set_state(
            "sensor.fishing_wind",
            state=round(today.conditions.wind.speed_mph),
            attributes={
                "friendly_name": "Fishing — Wind",
                "icon": "mdi:weather-windy",
                "unit_of_measurement": "mph",
                "direction": today.conditions.wind.direction,
                "gust_mph": today.conditions.wind.gust_mph,
            },
        )

        self.set_state(
            "sensor.fishing_waves",
            state=round(today.conditions.buoy.wave_height_ft, 1),
            attributes={
                "friendly_name": "Fishing — Waves",
                "icon": "mdi:waves",
                "unit_of_measurement": "ft",
                "period_sec": today.conditions.buoy.wave_period_sec,
            },
        )

        self.set_state(
            "sensor.fishing_species",
            state=today.best_species,
            attributes={
                "friendly_name": "Fishing — Target Species",
                "icon": "mdi:fish",
            },
        )

        self.set_state(
            "sensor.fishing_location",
            state=today.location_rec,
            attributes={
                "friendly_name": "Fishing — Where to Fish",
                "icon": "mdi:map-marker",
                "reason": today.location_reason,
            },
        )

        self.set_state(
            "sensor.fishing_best_window",
            state=today.best_window,
            attributes={
                "friendly_name": "Fishing — Best Time",
                "icon": "mdi:clock-outline",
                "worst_window": today.worst_window,
            },
        )

        self.set_state(
            "sensor.fishing_pressure",
            state=round(today.conditions.buoy.pressure_mb, 1),
            attributes={
                "friendly_name": "Fishing — Pressure",
                "icon": "mdi:gauge",
                "unit_of_measurement": "mb",
                "trend": today.conditions.pressure_trend,
            },
        )

        # ── Best days this week ──────────────────────────────────────────────

        self.set_state(
            "sensor.fishing_best_inshore_day",
            state=best_inshore.date.strftime("%A %b %d"),
            attributes={
                "friendly_name": "Fishing — Best Inshore Day",
                "icon": "mdi:star",
                "score": best_inshore.inshore_score,
                "species": best_inshore.best_species,
                "location": best_inshore.location_rec,
            },
        )

        self.set_state(
            "sensor.fishing_best_offshore_day",
            state=best_offshore.date.strftime("%A %b %d"),
            attributes={
                "friendly_name": "Fishing — Best Offshore Day",
                "icon": "mdi:star",
                "score": best_offshore.offshore_score,
                "status": (
                    "GO" if best_offshore.offshore_score >= 6
                    else "MARGINAL" if best_offshore.offshore_score >= 4
                    else "NO-GO"
                ),
                "wave_height": best_offshore.conditions.buoy.wave_height_ft,
                "wind_mph": best_offshore.conditions.wind.speed_mph,
            },
        )

        # ── Weekly summary (JSON in attributes) ─────────────────────────────

        week_data = []
        for d in forecast.days:
            week_data.append({
                "date": d.date.isoformat(),
                "day": d.date.strftime("%a"),
                "inshore": d.inshore_score,
                "nearshore": d.nearshore_score,
                "offshore": d.offshore_score,
                "species": d.best_species,
                "location": d.location_rec,
                "wind_mph": round(d.conditions.wind.speed_mph),
                "wind_dir": d.conditions.wind.direction,
                "waves_ft": round(d.conditions.buoy.wave_height_ft, 1),
                "water_temp_f": round(d.conditions.buoy.water_temp_f, 1),
                "best_window": d.best_window,
            })

        self.set_state(
            "sensor.fishing_forecast_week",
            state=f"{len(forecast.days)} days",
            attributes={
                "friendly_name": "Fishing — Weekly Forecast",
                "icon": "mdi:calendar-week",
                "area": forecast.area,
                "generated": forecast.generated_at,
                "days": week_data,
            },
        )

        # ── Notifications for 8+ days ────────────────────────────────────────

        for d in forecast.days:
            if d.inshore_score >= 8:
                self.call_service(
                    "persistent_notification/create",
                    title=f"🎣 Great fishing {d.date.strftime('%A %b %d')}!",
                    message=(
                        f"Inshore: {d.inshore_score}/10 — "
                        f"{d.best_species} at {d.location_rec}\n"
                        f"Best window: {d.best_window}"
                    ),
                    notification_id=f"fishing_{d.date.isoformat()}",
                )

        # ── Warnings ─────────────────────────────────────────────────────────

        if today.warnings:
            self.set_state(
                "sensor.fishing_warnings",
                state=len(today.warnings),
                attributes={
                    "friendly_name": "Fishing — Warnings",
                    "icon": "mdi:alert",
                    "warnings": today.warnings,
                },
            )
        else:
            self.set_state(
                "sensor.fishing_warnings",
                state=0,
                attributes={
                    "friendly_name": "Fishing — Warnings",
                    "icon": "mdi:check-circle",
                    "warnings": [],
                },
            )

    # ── HTML Report ──────────────────────────────────────────────────────────

    def _write_report(self, forecast: ForecastResult):
        """Generate HTML report and write to HA www/ folder."""
        try:
            from integrations.html_report import generate_html_string

            html = generate_html_string(forecast)
            with open(self.report_path, "w", encoding="utf-8") as f:
                f.write(html)
            self.log(f"Report written to {self.report_path}")
        except Exception:
            self.log(f"Report write failed:\n{traceback.format_exc()}", level="WARNING")
