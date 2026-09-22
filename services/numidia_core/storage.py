"""Filesystem helpers: audit snapshots of real ingestions.

Snapshots under data/raw/firms/ are an audit trail (gitignored). They are
NEVER the application's source of truth - production reads the database.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

import pandas as pd

from .config import PROCESSED_DIR, RAW_FIRMS_DIR


def list_raw_snapshots() -> list[Path]:
    if not RAW_FIRMS_DIR.exists():
        return []
    return sorted(RAW_FIRMS_DIR.glob("*.csv"))


def latest_raw_snapshot() -> Path | None:
    snaps = list_raw_snapshots()
    return snaps[-1] if snaps else None


def load_raw_snapshot(path: Path | str | None = None) -> pd.DataFrame | None:
    target = Path(path) if path else latest_raw_snapshot()
    if target is None or not target.exists():
        return None
    return pd.read_csv(target)


def save_audit_snapshot(df: pd.DataFrame, name: str | None = None) -> Path:
    """Persist one ingestion batch as a timestamped audit CSV (gitignored)."""
    RAW_FIRMS_DIR.mkdir(parents=True, exist_ok=True)
    if name is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
        name = f"viirs_algeria_audit_{stamp}.csv"
    path = RAW_FIRMS_DIR / name
    df.to_csv(path, index=False)
    return path


def write_status_sidecar(key: str, payload: dict) -> Path:
    """Worker status JSON under data/processed/ (informational, gitignored)."""
    from datetime import datetime as _dt, timezone as _tz

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / f"{key}_status.json"
    payload["written_at"] = _dt.now(_tz.utc).isoformat()
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path