"""Central configuration for NUMIDIA EYE (project-local, .env aware)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

DATA_DIR = REPO_ROOT / "data"
RAW_FIRMS_DIR = DATA_DIR / "raw" / "firms"
PROCESSED_DIR = DATA_DIR / "processed"
GIS_DIR = DATA_DIR / "gis"
EVAL_DIR = DATA_DIR / "evaluation"
WILAYA_GEOJSON = GIS_DIR / "algeria_wilayas.geojson"

# Algeria bounding box used for FIRMS queries (matches .github workflow).
ALGERIA_BBOX = {"lon_min": -9.0, "lat_min": 18.0, "lon_max": 12.0, "lat_max": 38.0}

FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY", "").strip()
FIRMS_API_BASE = os.getenv(
    "FIRMS_API_BASE", "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
)
FIRMS_ARCHIVE_BASE = os.getenv(
    "FIRMS_ARCHIVE_BASE", "https://firms.modaps.eosdis.nasa.gov/data/active_fire"
)
FIRMS_SOURCES = [
    s.strip()
    for s in os.getenv(
        "FIRMS_SOURCES", "VIIRS_NOAA21_NRT,VIIRS_SNPP_NRT,VIIRS_NOAA20_NRT"
    ).split(",")
    if s.strip()
]

NUMIDIA_API_HOST = os.getenv("NUMIDIA_API_HOST", "0.0.0.0")
NUMIDIA_API_PORT = int(os.getenv("NUMIDIA_API_PORT", "8000"))

# A detection is "LIVE" while its acquisition time is this fresh.
LIVE_WINDOW_HOURS = 26.0