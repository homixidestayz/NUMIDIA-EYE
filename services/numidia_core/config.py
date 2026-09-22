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

# --- Production database & ingestion -------------------------------------
_db_env = os.getenv("NUMIDIA_DB_PATH", "").strip()
DB_PATH = Path(_db_env) if _db_env else DATA_DIR / "db" / "numidia.db"

# Scheduler: fetch fresh detections this often (minutes). Server-side only.
INGEST_INTERVAL_MIN = int(os.getenv("NUMIDIA_INGEST_INTERVAL_MIN", "30"))
# Data older than this without a successful ingest run is STALE, never LIVE.
INGEST_STALE_AFTER_MIN = int(os.getenv("NUMIDIA_STALE_AFTER_MIN", "180"))
# Ingestion mode: "api" (NRT, requires FIRMS_MAP_KEY - the production path)
# or "archive" (public archives, explicit backfill/testing only).
INGEST_MODE = os.getenv("NUMIDIA_INGEST_MODE", "api").strip().lower()
INGEST_DAY = int(os.getenv("NUMIDIA_INGEST_DAY", "1"))

DISABLE_SCHEDULER = os.getenv("NUMIDIA_DISABLE_SCHEDULER", "").strip().lower() in (
    "1", "true", "yes",
)

# Path to a TRAINED + EVALUATED verifier model. Empty/absent = no AI served.
ACTIVE_MODEL = os.getenv("NUMIDIA_ACTIVE_MODEL", "").strip()