"""
Configuration for fishing forecast data sources and scoring weights.
Edit AREAS to add new locations. Edit WEIGHTS to tune scoring.
"""

# ── Areas ────────────────────────────────────────────────────────────────────
AREAS = {
    "matagorda": {
        "name": "Matagorda / Sargent, TX",
        "tide_stations": ["8773037", "8772985"],
        "buoy_ids": ["42019", "42035"],
        "nws_office": "HGX",
        "nws_gridpoint": "HGX/53,51",
        "lat": 28.77,
        "lon": -95.62,
        "marine_zones": ["GMZ330", "GMZ335"],
    },
    "galveston": {
        "name": "Galveston, TX",
        "tide_stations": ["8771450", "8771013"],
        "buoy_ids": ["42035"],
        "nws_office": "HGX",
        "nws_gridpoint": "HGX/85,75",
        "lat": 29.31,
        "lon": -94.79,
        "marine_zones": ["GMZ335", "GMZ355"],
    },
    "freeport": {
        "name": "Freeport / Surfside, TX",
        "tide_stations": ["8772440", "8772471"],
        "buoy_ids": ["42019", "42035"],
        "nws_office": "HGX",
        "nws_gridpoint": "HGX/73,65",
        "lat": 29.08,
        "lon": -95.11,
        "marine_zones": ["GMZ335", "GMZ355"],
    },
    "port_oconnor": {
        "name": "Port O'Connor / Espiritu Santo Bay, TX",
        "tide_stations": ["8773259", "8773146"],
        "buoy_ids": ["42019"],
        "nws_office": "CRP",
        "nws_gridpoint": "CRP/149,62",
        "lat": 28.44,
        "lon": -96.40,
        "marine_zones": ["GMZ330", "GMZ335"],
    },
    "port_aransas": {
        "name": "Port Aransas / Mustang Island, TX",
        "tide_stations": ["8775237", "8775241"],
        "buoy_ids": ["42020"],
        "nws_office": "CRP",
        "nws_gridpoint": "CRP/124,35",
        "lat": 27.83,
        "lon": -97.05,
        "marine_zones": ["GMZ250", "GMZ255"],
    },
    "corpus_christi": {
        "name": "Corpus Christi / Upper Laguna Madre, TX",
        "tide_stations": ["8775870", "8775792"],
        "buoy_ids": ["42020"],
        "nws_office": "CRP",
        "nws_gridpoint": "CRP/113,26",
        "lat": 27.64,
        "lon": -97.24,
        "marine_zones": ["GMZ250", "GMZ255"],
    },
    "south_padre": {
        "name": "South Padre Island / Lower Laguna Madre, TX",
        "tide_stations": ["8779770", "8779748"],
        "buoy_ids": ["42020"],
        "nws_office": "BRO",
        "nws_gridpoint": "BRO/91,12",
        "lat": 26.07,
        "lon": -97.17,
        "marine_zones": ["GMZ130", "GMZ155"],
    },
    "rockport": {
        "name": "Rockport / Aransas Bay, TX",
        "tide_stations": ["8774770"],
        "buoy_ids": ["42020"],
        "nws_office": "CRP",
        "nws_gridpoint": "CRP/136,44",
        "lat": 28.02,
        "lon": -96.99,
        "marine_zones": ["GMZ250", "GMZ255"],
    },
}

DEFAULT_AREA = "matagorda"

# ── NOAA API endpoints ───────────────────────────────────────────────────────
NOAA_TIDES_API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
NDBC_OBSERVATION_URL = "https://www.ndbc.noaa.gov/data/realtime2/{station}.txt"
NWS_API_BASE = "https://api.weather.gov"

# ── Scoring weights (must sum to 1.0 per category) ──────────────────────────
INSHORE_WEIGHTS = {
    "tide": 0.30,
    "wind": 0.25,
    "pressure": 0.20,
    "solunar": 0.15,
    "water_temp": 0.05,
    "cloud_cover": 0.05,
}

NEARSHORE_WEIGHTS = {
    "wind": 0.30,
    "swell": 0.25,
    "tide": 0.20,
    "pressure": 0.15,
    "solunar": 0.05,
    "water_temp": 0.05,
}

OFFSHORE_WEIGHTS = {
    "swell": 0.35,
    "wind": 0.30,
    "pressure": 0.15,
    "weather_window": 0.10,
    "solunar": 0.05,
    "water_temp": 0.05,
}

# ── Thresholds ───────────────────────────────────────────────────────────────
WIND_IDEAL_MPH = 10
WIND_FISHABLE_MPH = 15
WIND_OFFSHORE_MAX_MPH = 12
WAVE_OFFSHORE_IDEAL_FT = 2.0
WAVE_OFFSHORE_MAX_FT = 4.0
PRESSURE_STABLE_RANGE_MB = 2.0  # +/- from 1013

# ── Species / season triggers ────────────────────────────────────────────────
SPECIES_TEMP_RANGES = {
    "redfish": {"min": 55, "max": 88, "ideal_min": 65, "ideal_max": 82},
    "trout": {"min": 48, "max": 85, "ideal_min": 55, "ideal_max": 75},
    "flounder": {"min": 50, "max": 82, "ideal_min": 58, "ideal_max": 72},
}

# ── Home Assistant ───────────────────────────────────────────────────────────
HA_URL = "http://homeassistant.local:8123"
HA_TOKEN = ""  # Long-lived access token — set via env var HA_TOKEN

# ── Server ───────────────────────────────────────────────────────────────────
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 5055
