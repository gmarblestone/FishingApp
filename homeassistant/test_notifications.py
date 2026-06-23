import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fishing_forecast.scorer import generate_forecast


def build_week_days(forecast):
    return [
        {
            "date": d.date.isoformat(),
            "inshore": d.inshore_score,
            "nearshore": d.nearshore_score,
            "offshore": d.offshore_score,
            "species": d.best_species,
            "location": d.location_rec,
            "wind_mph": round(d.conditions.wind.speed_mph),
            "waves_ft": round(d.conditions.buoy.wave_height_ft, 1),
            "best_window": d.best_window,
        }
        for d in forecast.days
    ]


def best_day(days, key, threshold):
    candidates = [day for day in days if day.get(key, 0) >= threshold]
    return max(candidates, key=lambda day: day.get(key, 0), default={})


def inshore_message(days, threshold):
    best = best_day(days, "inshore", threshold)
    if "date" in best:
        return (
            f"{best['date']} looks strong for inshore fishing:\n"
            f"{best['inshore']}/10, {best['species']}, {best['location']}.\n"
            f"Best window: {best['best_window']}."
        )
    return f"No {threshold}+ inshore day is currently in the forecast window."


def offshore_message(days, threshold):
    best = best_day(days, "offshore", threshold)
    if "date" in best:
        return (
            f"{best['date']} looks strong offshore:\n"
            f"{best['offshore']}/10, waves {best['waves_ft']} ft,\n"
            f"wind {best['wind_mph']} mph."
        )
    return f"No {threshold}+ offshore day is currently in the forecast window."


def main():
    parser = argparse.ArgumentParser(description="Test fishing forecast HA notifications locally")
    parser.add_argument("--area", default="matagorda", help="Area key from config")
    parser.add_argument("--days", type=int, default=7, help="Forecast days to generate")
    parser.add_argument("--threshold", type=int, default=8, help="Notification threshold")
    parser.add_argument("--json", action="store_true", help="Print the simulated weekly sensor payload")
    args = parser.parse_args()

    forecast = generate_forecast(args.area, args.days)
    days = build_week_days(forecast)

    print(f"Area: {forecast.area}")
    print(f"Generated: {forecast.generated_at}")
    print()
    print("Inshore notification")
    print(inshore_message(days, args.threshold))
    print()
    print("Offshore notification")
    print(offshore_message(days, args.threshold))

    if args.json:
        print()
        print("Weekly sensor payload")
        print(json.dumps({"area": forecast.area, "generated": forecast.generated_at, "days": days}, indent=2))


if __name__ == "__main__":
    main()