# Fishing Forecast

Scores upcoming fishing days 1–10 for **inshore**, **nearshore**, and **offshore** using live public data from NOAA, NDBC, and NWS. Recommends target species, best/worst time windows, and where to fish (back lakes vs ICW vs open bay) based on water temperature, wind, tides, and pressure.

**Runs entirely inside Home Assistant** as a custom add-on — sandboxed Docker container, one-click install from the Add-on Store. Sets HA sensors directly, writes an HTML report to the sidebar, and refreshes automatically.

## Architecture

```
FishingApp/
├── fishing_forecast/              Core engine
│   ├── config.py                  Areas, tide stations, buoy IDs, scoring weights
│   ├── fetcher.py                 Pulls NOAA tides (hi/lo + hourly), NDBC buoy, NWS forecast
│   ├── models.py                  Dataclasses: TideData, BuoyData, DayForecast, etc.
│   └── scorer.py                  Scores each day, picks species, location, time windows
├── integrations/
│   ├── html_report.py             Self-contained HTML report with SVG charts
│   ├── calendar_export.py         .ics export for Google Calendar
│   └── ha_server.py               (legacy) standalone REST server
├── fishing_forecast_addon/        HA Add-on (Docker)
│   ├── config.yaml                Add-on metadata, options, schema
│   ├── Dockerfile                 Alpine + Python + requests
│   ├── build.yaml                 Multi-arch build config
│   └── rootfs/
│       ├── run.sh                 Entry point — fetch, score, push sensors, write report
│       └── app/                   Python code (copied from core engine)
│           ├── fishing_forecast/
│           ├── integrations/
│           └── push_sensors.py    Pushes sensors via HA Supervisor API
├── homeassistant/
│   └── dashboard.yaml             Lovelace dashboard card
├── repository.yaml                HA Add-on Store repository registration
└── run_forecast.py                CLI entry point (standalone use)
```

## Home Assistant Setup (Add-on)

This is the primary deployment method. Everything runs inside HA in a sandboxed container.

### 1. Add the repository

- **Settings → Add-ons → Add-on Store → ⋮ (top right) → Repositories**
- Add your repo URL (after pushing to GitHub):
  ```
  https://github.com/grantma/FishingApp
  ```

### 2. Install the add-on

- Find **Fishing Forecast** in the Add-on Store
- Click **Install**
- No dependencies to configure — Python and requests are bundled in the container

### 3. Configure (optional)

In the add-on **Configuration** tab:

| Option | Default | Description |
|--------|---------|-------------|
| `area` | `matagorda` | Area key from config.py |
| `refresh_hours` | `5,12` | Comma-separated hours (24h) to auto-refresh |
| `report_path` | `/config/www/fishing_forecast.html` | Where to write the HTML report |

### 4. Start the add-on

Click **Start**. The add-on will:
- Fetch live data from NOAA, NDBC, and NWS
- Score each day and set 14 sensor entities via the Supervisor API
- Write the full HTML report to `/config/www/`
- Auto-refresh at the configured hours (default: 5 AM and 12 PM)
- Show the HTML report in the HA sidebar (Fishing Forecast panel)

### 5. Add the dashboard card (optional)

Use the Lovelace raw config editor to paste the card from `homeassistant/dashboard.yaml`.

Settings → Add-ons → AppDaemon → Restart

That's it. The app will:
- Fetch live data from NOAA, NDBC, and NWS
- Score each day and set 12+ sensor entities
- Write the full HTML report to `/config/www/`
- Refresh automatically at 5 AM and 12 PM
- Send persistent notifications for days scoring 8+

### Verify installation

- **Add-on Log** tab — look for `Fishing Forecast starting` and `Forecast complete`
- **Developer Tools → States** — filter for `fishing` — you should see 14 sensors
- **Sidebar** — "Fishing Forecast" panel with the full HTML report

## Sensors Created

All sensors are created automatically by the add-on:

| Sensor | State | Key Attributes |
|--------|-------|----------------|
| `sensor.fishing_inshore_score` | 1–10 | species, location, best_window, key_factor |
| `sensor.fishing_nearshore_score` | 1–10 | — |
| `sensor.fishing_offshore_score` | 1–10 | status (GO/MARGINAL/NO-GO), wave_height |
| `sensor.fishing_water_temp` | °F | — |
| `sensor.fishing_wind` | mph | direction, gust_mph |
| `sensor.fishing_waves` | ft | period_sec |
| `sensor.fishing_pressure` | mb | trend (rising/falling/stable) |
| `sensor.fishing_species` | species name | — |
| `sensor.fishing_location` | location name | reason |
| `sensor.fishing_best_window` | time window | worst_window |
| `sensor.fishing_best_inshore_day` | day name | score, species, location |
| `sensor.fishing_best_offshore_day` | day name | score, status, wave_height |
| `sensor.fishing_forecast_week` | "7 days" | days (JSON array with full week data) |
| `sensor.fishing_warnings` | count | warnings (list) |

## CLI Commands (Standalone)

The CLI still works for local use without Home Assistant. All commands accept `--area <key>` (default: `matagorda`).

### Print forecast JSON

```bash
python run_forecast.py forecast
python run_forecast.py forecast --days 5
```

### Generate HTML report

```bash
python run_forecast.py report                    # opens in browser
python run_forecast.py report --no-open          # generate only
python run_forecast.py report --output my.html   # custom filename
```

The report includes:
- Gauge dials for inshore/nearshore/offshore scores
- Tide chart (SVG area chart with hi/lo markers)
- Wind compass arrow with speed
- Wave height bar with threshold markers
- Best/worst fishing windows timeline
- Inshore panel with location recommendation (back lakes, ICW, bay, flats)
- Offshore panel with GO/NO-GO assessment
- Dark mode (auto-detects system theme + manual toggle)
- Mobile responsive
- Click "Export PDF" button or Ctrl+P → Save as PDF

### Export Google Calendar events

```bash
python run_forecast.py calendar
python run_forecast.py calendar --min-score 7    # only great days
python run_forecast.py calendar --output week.ics
```

Creates an `.ics` file with events on days scoring 6+ (or custom threshold). Import into Google Calendar via Settings → Import.

### Setup for CLI

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows
# source .venv/bin/activate         # Linux/Mac
pip install -r requirements.txt
```

## Data Sources

All public, no API keys required:

| Source | What it provides |
|--------|-----------------|
| [NOAA Tides & Currents](https://tidesandcurrents.noaa.gov/) | Hourly tide predictions, hi/lo times |
| [NDBC Buoys](https://www.ndbc.noaa.gov/) | Wave height, period, water temp, barometric pressure |
| [NWS API](https://api.weather.gov/) | 7-day wind, temperature, cloud cover, rain chance |

## Scoring

Each day is scored 1–10 for three categories using weighted factors:

**Inshore** (bays, flats, ICW): tide movement 30%, wind 25%, pressure 20%, solunar 15%, water temp 5%, cloud cover 5%

**Nearshore** (surf, jetties, piers): wind 30%, swell 25%, tide 20%, pressure 15%, solunar 5%, water temp 5%

**Offshore** (Gulf deep sea): swell 35%, wind 30%, pressure 15%, weather window 10%, solunar 5%, water temp 5%

Offshore uses stricter wind thresholds (max 12 mph vs 15 mph inshore), so it will score lower most days — that's expected.

## Location Recommendations

The inshore panel recommends where to fish based on conditions:

| Conditions | Recommendation |
|------------|---------------|
| Water < 60°F | Back Lakes & Deep Holes — fish concentrate in warm protected water |
| Post-front, rising pressure, wind > 12 | ICW & Protected — shelter from north wind |
| Wind 12–18 mph | ICW & Lee Shorelines |
| Wind 18+ mph | ICW only — open bay is dangerous |
| 68–80°F, calm | Open Bay Flats & Reefs — prime wade/drift |
| Water > 82°F | Deep Reefs & Channels — dawn-only or night fishing |
| October–November | Passes, Drains & Jetties — fall flounder run |

## Available Areas

Select from the add-on Configuration tab dropdown, or pass `--area <key>` to the CLI:

| Key | Area | Tide Stations | Buoy | NWS Grid |
|-----|------|--------------|------|----------|
| `matagorda` | Matagorda / Sargent, TX | 8773037, 8772985 | 42019, 42035 | HGX/53,51 |
| `galveston` | Galveston, TX | 8771450, 8771013 | 42035 | HGX/85,75 |
| `freeport` | Freeport / Surfside, TX | 8772440, 8772471 | 42019, 42035 | HGX/73,65 |
| `port_oconnor` | Port O'Connor, TX | 8773259, 8773146 | 42019 | CRP/149,62 |
| `port_aransas` | Port Aransas, TX | 8775237, 8775241 | 42020 | CRP/124,35 |
| `corpus_christi` | Corpus Christi, TX | 8775870, 8775792 | 42020 | CRP/113,26 |
| `south_padre` | South Padre Island, TX | 8779770, 8779748 | 42020 | BRO/91,12 |
| `rockport` | Rockport / Aransas Bay, TX | 8774770 | 42020 | CRP/136,44 |

## Adding Custom Areas

Edit `fishing_forecast/config.py` → `AREAS` dict to add your own:

```python
"my_area": {
    "name": "My Area, TX",
    "tide_stations": ["STATION_ID"],
    "buoy_ids": ["BUOY_ID"],
    "nws_gridpoint": "OFFICE/X,Y",
    "lat": 0.0, "lon": 0.0,
    "marine_zones": ["GMZ000"],
},
```

Find station IDs at [NOAA Tides](https://tidesandcurrents.noaa.gov/tide_predictions.html) and buoy IDs at [NDBC](https://www.ndbc.noaa.gov/). Look up NWS gridpoints at `https://api.weather.gov/points/{lat},{lon}`.

## Legacy: External Server Mode

The original Flask server and webhook approach still works if you prefer running outside HA:

```bash
python run_forecast.py server                    # REST API on port 5055
python run_forecast.py schedule                  # Server + auto-refresh at 5AM/12PM
set HA_TOKEN=<token> && python run_forecast.py push  # Push sensors via HA REST API
```

See `integrations/ha_server.py` and `integrations/ha_webhook.py`. These files are kept for reference but are **not needed** with the add-on deployment.
