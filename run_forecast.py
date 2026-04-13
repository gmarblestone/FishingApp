"""
Fishing Forecast — CLI entry point and scheduler.

Usage:
    python run_forecast.py forecast              # Print forecast to console
    python run_forecast.py server                # Start REST server for HA
    python run_forecast.py push                  # Push sensors to HA via REST API
    python run_forecast.py calendar              # Export .ics file
    python run_forecast.py schedule              # Run server + daily refresh scheduler
"""

import argparse
import json
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def cmd_forecast(args):
    from fishing_forecast.scorer import generate_forecast

    result = generate_forecast(args.area, args.days)
    print(json.dumps(result.to_dict(), indent=2))


def cmd_server(args):
    from integrations.ha_server import app
    from fishing_forecast.config import SERVER_HOST, SERVER_PORT

    host = args.host or SERVER_HOST
    port = args.port or SERVER_PORT
    logger.info("Starting server on %s:%d", host, port)
    app.run(host=host, port=port, debug=False)


def cmd_push(args):
    from integrations.ha_webhook import push_forecast_to_ha

    push_forecast_to_ha(args.area)
    print("Sensors pushed to Home Assistant.")


def cmd_report(args):
    from integrations.html_report import open_report, generate_html

    if args.no_open:
        path = generate_html(args.area, args.output)
    else:
        path = open_report(args.area, args.output)
    print(f"Report: {path}")


def cmd_calendar(args):
    from integrations.calendar_export import generate_ics

    path = generate_ics(args.area, args.output, args.min_score)
    print(f"Calendar exported to: {path}")


def cmd_schedule(args):
    from apscheduler.schedulers.background import BackgroundScheduler
    from integrations.ha_server import app, _get_or_refresh
    from fishing_forecast.config import SERVER_HOST, SERVER_PORT

    scheduler = BackgroundScheduler()

    # Refresh forecast data at 5 AM and 12 PM daily
    scheduler.add_job(
        lambda: _get_or_refresh(args.area, force=True),
        "cron",
        hour="5,12",
        id="forecast_refresh",
    )
    scheduler.start()
    logger.info("Scheduler started — refreshing at 5 AM and 12 PM")

    host = args.host or SERVER_HOST
    port = args.port or SERVER_PORT
    logger.info("Starting server on %s:%d", host, port)
    app.run(host=host, port=port, debug=False)


def main():
    parser = argparse.ArgumentParser(description="Fishing Forecast")
    parser.add_argument("--area", default="matagorda", help="Area key from config")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # forecast
    p_forecast = subparsers.add_parser("forecast", help="Print forecast JSON")
    p_forecast.add_argument("--days", type=int, default=7)

    # server
    p_server = subparsers.add_parser("server", help="Start REST server for HA")
    p_server.add_argument("--host", default=None)
    p_server.add_argument("--port", type=int, default=None)

    # push
    subparsers.add_parser("push", help="Push sensors to HA")

    # calendar
    p_cal = subparsers.add_parser("calendar", help="Export .ics calendar")
    p_cal.add_argument("--output", default="fishing_forecast.ics")
    p_cal.add_argument("--min-score", type=int, default=6)

    # report
    p_report = subparsers.add_parser("report", help="Generate HTML report and open in browser")
    p_report.add_argument("--output", default="fishing_forecast.html")
    p_report.add_argument("--no-open", action="store_true", help="Don't open browser")

    # schedule
    p_sched = subparsers.add_parser("schedule", help="Server + auto-refresh scheduler")
    p_sched.add_argument("--host", default=None)
    p_sched.add_argument("--port", type=int, default=None)

    args = parser.parse_args()

    commands = {
        "forecast": cmd_forecast,
        "server": cmd_server,
        "push": cmd_push,
        "calendar": cmd_calendar,
        "report": cmd_report,
        "schedule": cmd_schedule,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
