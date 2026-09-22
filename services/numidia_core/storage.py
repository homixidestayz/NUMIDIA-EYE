"""Filesystem storage: raw snapshots, processed parquet/CSV, status sidecars.

The committed raw sample lives in data/raw/firms/ and is always loaded
offline; live fetches add new snapshot files alongside it.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import PROCESSED_DIR, RAW_FIRMS_DIR

SAMPLE_RAW = RAW_FIRMS_DIR / "viirs_noaa21_1d.csv"


def list_raw_snapshots() -> list[Path]:
    if not RAW_FIRMS_DIR.exists():
        return []
    return sorted(RAW_FIRMS_DIR.glob("*.csv"))


def latest_raw_snapshot() -> Path | None:
    snaps = list_raw_snapshots()
    return snaps[-1] if snaps else None


def load_raw_snapshot(path: Path | str | None = None) -> pd.DataFrame | None:
    """Load a raw FIRMS CSV (un-normalized columns)."""
    target = Path(path) if path else latest_raw_snapshot()
    if target is None or not target.exists():
        return None
    return pd.read_csv(target)


def save_canonical_snapshot(df: pd.DataFrame, name: str = "viirs_algeria_24h.csv") -> Path:
    """Persist canonical (normalized) detections to data/raw/firms/."""
    RAW_FIRMS_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_FIRMS_DIR / name
    df.to_csv(path, index=False)
    return path


def save_processed(df: pd.DataFrame, name: str = "firms_features", sidecar: dict | None = None) -> dict:
    """Write processed features CSV + parquet and a status sidecar JSON."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = PROCESSED_DIR / f"{name}.csv"
    pq_path = PROCESSED_DIR / f"{name}.parquet"
    df.to_csv(csv_path, index=False)
    df.to_parquet(pq_path, index=False)

    if sidecar is None:
        sidecar = {}
    sidecar.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
    sidecar.setdefault("rows", len(df))
    json_path = PROCESSED_DIR / f"{name}_status.json"
    json_path.write_text(json.dumps(sidecar, indent=2, default=str), encoding="utf-8")

    return {
        "csv": str(csv_path),
        "parquet": str(pq_path),
        "status": str(json_path),
        "rows": len(df),
    }


def load_processed(name: str = "firms_features") -> pd.DataFrame | None:
    csv_path = PROCESSED_DIR / f"{name}.csv"
    if not csv_path.exists():
        return None
    df = pd.read_csv(csv_path)
    for col in ("acq_datetime", "fetched_at"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True)
    return df


def write_status_sidecar(key: str, payload: dict) -> Path:
    """Generic status JSON under data/processed/ (informational, gitignored)."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / f"{key}_status.json"
    payload["written_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path