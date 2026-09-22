"""Application database (SQLite, WAL mode) - the production source of truth.

The API serves ONLY what is in these tables. Tables:
- detections: one row per real FIRMS/VIIRS detection (first-seen wins, so
  `fetched_at` is the true first-ingestion timestamp).
- ingest_runs: every ingestion attempt with provenance; drives freshness.

Freshness rule (enforced in `data_state_summary`): data is LIVE only when a
recent successful ingest run exists AND detections are freshly acquired.
Stale pipelines yield STALE, never LIVE.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .config import DB_PATH, INGEST_STALE_AFTER_MIN, LIVE_WINDOW_HOURS

SCHEMA = """
CREATE TABLE IF NOT EXISTS detections (
  detection_id TEXT PRIMARY KEY,
  lat REAL NOT NULL,
  lon REAL NOT NULL,
  acq_datetime TEXT NOT NULL,
  acq_date TEXT,
  acq_time TEXT,
  satellite TEXT,
  instrument TEXT,
  confidence REAL,
  confidence_raw TEXT,
  bright_ti4 REAL,
  bright_ti5 REAL,
  scan REAL,
  track REAL,
  frp REAL NOT NULL DEFAULT 0,
  daynight TEXT,
  version TEXT,
  source TEXT NOT NULL,
  source_url TEXT,
  fetched_at TEXT NOT NULL,
  wilaya_code TEXT,
  wilaya_name TEXT,
  f_bt_diff REAL,
  f_frp REAL,
  f_confidence REAL,
  f_hour_utc REAL,
  f_month INTEGER,
  f_doy INTEGER,
  f_daynight INTEGER
);
CREATE INDEX IF NOT EXISTS idx_det_acq ON detections(acq_datetime DESC);
CREATE INDEX IF NOT EXISTS idx_det_source ON detections(source);
CREATE TABLE IF NOT EXISTS ingest_runs (
  run_id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  mode TEXT NOT NULL,
  sources TEXT NOT NULL DEFAULT '[]',
  urls TEXT NOT NULL DEFAULT '[]',
  count_new INTEGER NOT NULL DEFAULT 0,
  count_total INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  message TEXT NOT NULL DEFAULT ''
);
"""

DET_COLUMNS = [
    "detection_id", "lat", "lon", "acq_datetime", "acq_date", "acq_time",
    "satellite", "instrument", "confidence", "confidence_raw", "bright_ti4",
    "bright_ti5", "scan", "track", "frp", "daynight", "version", "source",
    "source_url", "fetched_at", "wilaya_code", "wilaya_name",
    "f_bt_diff", "f_frp", "f_confidence", "f_hour_utc", "f_month",
    "f_doy", "f_daynight",
]


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_db_path(path: Path | str | None = None) -> Path:
    return Path(path) if path else DB_PATH


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    db_path = resolve_db_path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db(path: Path | str | None = None) -> Path:
    db_path = resolve_db_path(path)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
    return db_path


def _iso(value, default: str | None = None):
    if value is None:
        return default
    if isinstance(value, str):
        return value
    try:
        ts = pd.to_datetime(value, utc=True)
        if pd.isna(ts):
            return default
        return ts.isoformat()
    except (ValueError, TypeError):
        return default


def _clean_num(value):
    if value is None:
        return None
    try:
        v = float(value)
    except (ValueError, TypeError):
        return None
    return None if pd.isna(v) else v


def upsert_detections(df: pd.DataFrame, path: Path | str | None = None) -> dict:
    """Insert new detections; existing IDs are left untouched (first-seen wins).

    Returns {"new": n, "total": m} where total = detections in DB afterwards.
    """
    if df is None or df.empty:
        with connect(path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM detections").fetchone()[0]
        return {"new": 0, "total": total}

    now = utcnow_iso()
    rows = []
    for _, r in df.iterrows():
        row = {c: (r[c] if c in df.columns else None) for c in DET_COLUMNS}
        row["acq_datetime"] = _iso(row["acq_datetime"], default=now)
        row["fetched_at"] = _iso(row.get("fetched_at"), default=now)
        for c in ("lat", "lon", "confidence", "bright_ti4", "bright_ti5",
                  "scan", "track", "frp", "f_bt_diff", "f_frp",
                  "f_confidence", "f_hour_utc"):
            row[c] = _clean_num(row[c])
        for c in ("f_month", "f_doy", "f_daynight"):
            v = _clean_num(row[c])
            row[c] = int(v) if v is not None else None
        rows.append(tuple(row[c] for c in DET_COLUMNS))

    placeholders = ", ".join(["?"] * len(DET_COLUMNS))
    with connect(path) as conn:
        before = conn.total_changes
        conn.executemany(
            f"INSERT OR IGNORE INTO detections ({', '.join(DET_COLUMNS)}) "
            f"VALUES ({placeholders})",
            rows,
        )
        conn.commit()
        new = conn.total_changes - before
        total = conn.execute("SELECT COUNT(*) FROM detections").fetchone()[0]
    return {"new": new, "total": total}


def record_run(*, mode: str, sources: list, urls: list, count_new: int,
               count_total: int, status: str, message: str = "",
               started_at: str | None = None, finished_at: str | None = None,
               path: Path | str | None = None) -> int:
    started_at = started_at or utcnow_iso()
    finished_at = finished_at or utcnow_iso()
    with connect(path) as conn:
        cur = conn.execute(
            "INSERT INTO ingest_runs (started_at, finished_at, mode, sources,"
            " urls, count_new, count_total, status, message)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (started_at, finished_at, mode, json.dumps(sources),
             json.dumps(urls), count_new, count_total, status, message),
        )
        conn.commit()
        return cur.lastrowid


def latest_runs(limit: int = 5, path: Path | str | None = None) -> list[dict]:
    with connect(path) as conn:
        rows = conn.execute(
            "SELECT * FROM ingest_runs ORDER BY run_id DESC LIMIT ?", (limit,)
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["sources"] = json.loads(d["sources"] or "[]")
        d["urls"] = json.loads(d["urls"] or "[]")
        out.append(d)
    return out


def last_successful_run(path: Path | str | None = None) -> dict | None:
    with connect(path) as conn:
        r = conn.execute(
            "SELECT * FROM ingest_runs WHERE status='ok'"
            " ORDER BY run_id DESC LIMIT 1"
        ).fetchone()
    if r is None:
        return None
    d = dict(r)
    d["sources"] = json.loads(d["sources"] or "[]")
    d["urls"] = json.loads(d["urls"] or "[]")
    return d


def detection_stats(path: Path | str | None = None) -> dict:
    with connect(path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM detections").fetchone()[0]
        sources = [r[0] for r in conn.execute(
            "SELECT DISTINCT source FROM detections").fetchall()]
        satellites = [r[0] for r in conn.execute(
            "SELECT DISTINCT satellite FROM detections WHERE satellite IS NOT NULL"
        ).fetchall()]
        max_acq = conn.execute(
            "SELECT MAX(acq_datetime) FROM detections").fetchone()[0]
    return {"count": count, "sources": sources,
            "satellites": satellites, "max_acq": max_acq}


def load_detection_rows(*, limit: int = 500, source: str | None = None,
                        satellite: str | None = None,
                        path: Path | str | None = None) -> list[dict]:
    query = "SELECT * FROM detections"
    clauses, params = [], []
    if source:
        clauses.append("source = ?")
        params.append(source)
    if satellite:
        clauses.append("satellite = ?")
        params.append(satellite)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY acq_datetime DESC LIMIT ?"
    params.append(limit)
    with connect(path) as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def get_detection_row(detection_id: str,
                      path: Path | str | None = None) -> dict | None:
    with connect(path) as conn:
        r = conn.execute("SELECT * FROM detections WHERE detection_id = ?",
                         (detection_id,)).fetchone()
    return dict(r) if r else None


def data_state_summary(now: datetime | None = None,
                       stale_after_min: int | None = None,
                       path: Path | str | None = None) -> dict:
    """Compute the honest data state from DB contents + ingest history."""
    now = now or datetime.now(timezone.utc)
    stale_after_min = (INGEST_STALE_AFTER_MIN if stale_after_min is None
                       else stale_after_min)
    stats = detection_stats(path)
    runs = latest_runs(limit=1, path=path)
    last_run = runs[0] if runs else None
    last_ok = last_successful_run(path)

    ingest_fresh = False
    last_ok_at = None
    if last_ok and last_ok.get("finished_at"):
        last_ok_at = datetime.fromisoformat(last_ok["finished_at"])
        if last_ok_at.tzinfo is None:
            last_ok_at = last_ok_at.replace(tzinfo=timezone.utc)
        ingest_fresh = (now - last_ok_at) <= timedelta(minutes=stale_after_min)

    live_count = 0
    if stats["count"]:
        cutoff = (now - timedelta(hours=LIVE_WINDOW_HOURS)).isoformat()
        with connect(path) as conn:
            live_count = conn.execute(
                "SELECT COUNT(*) FROM detections WHERE acq_datetime >= ?",
                (cutoff,)).fetchone()[0]

    if stats["count"] == 0:
        state = "UNAVAILABLE"
    elif not ingest_fresh:
        state = "STALE"
    elif live_count > 0:
        state = "LIVE"
    else:
        state = "HISTORICAL"

    return {
        "data_state": state,
        "detections_count": stats["count"],
        "live_count": live_count,
        "ingest_fresh": ingest_fresh,
        "last_ok_at": last_ok_at.isoformat() if last_ok_at else None,
        "max_acq": stats["max_acq"],
        "sources": stats["sources"],
        "satellites": stats["satellites"],
        "last_run": last_run,
    }