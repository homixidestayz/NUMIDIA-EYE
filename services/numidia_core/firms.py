"""Real NASA FIRMS / VIIRS ingestion.

Two live paths (both real satellite data):
1. NRT Area API  - Algeria bbox, needs FIRMS_MAP_KEY (fast, small).
2. Public global archive CSV - no key (24h/48h/7d).

Everything is normalized into the canonical Detection schema with provenance
(source, source_url, fetched_at) and validated against the Algeria bbox.
"""
from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone

import pandas as pd
import requests

from .config import ALGERIA_BBOX, FIRMS_API_BASE, FIRMS_ARCHIVE_BASE, FIRMS_MAP_KEY, FIRMS_SOURCES

CANONICAL_COLUMNS = [
    "detection_id", "lat", "lon", "acq_datetime", "acq_date", "acq_time",
    "satellite", "instrument", "confidence", "confidence_raw",
    "bright_ti4", "bright_ti5", "scan", "track", "frp", "daynight",
    "version", "source", "source_url", "fetched_at",
]

CONFIDENCE_MAP = {
    "high": 1.0, "nominal": 0.6, "low": 0.2,
    "h": 1.0, "n": 0.6, "l": 0.2,
}

# Public archive layout:  {base}/{subpath}/csv/{prefix}_Global_{period}.csv
ARCHIVE_LAYOUT = {
    "VIIRS_NOAA21_C2": ("noaa-21-viirs-c2", "J2_VIIRS_C2"),
    "VIIRS_SNPP_C2": ("suomi-npp-viirs-c2", "SUOMI_VIIRS_C2"),
    "VIIRS_NOAA20_C2": ("noaa-20-viirs-c2", "J1_VIIRS_C2"),
}


def confidence_to_num(raw) -> float | None:
    """Map FIRMS confidence (h/n/l or high/nominal/low or 0-100) to 0..1."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        v = float(raw)
        return v / 100.0 if v > 1 else min(max(v, 0.0), 1.0)
    s = str(raw).strip().lower()
    if s in CONFIDENCE_MAP:
        return CONFIDENCE_MAP[s]
    try:
        v = float(s)
        return v / 100.0 if v > 1 else min(max(v, 0.0), 1.0)
    except ValueError:
        return None


def redact_url(url: str | None, map_key: str | None = None) -> str | None:
    """Redact the FIRMS MAP_KEY from a URL before storage or API exposure.

    NRT Area API URLs embed the secret key; it must never reach the database,
    logs-as-data, or any client. The key lives server-side only (env).
    """
    if not url:
        return url
    key = (map_key or FIRMS_MAP_KEY).strip()
    if key and key in url:
        return url.replace(key, "{FIRMS_MAP_KEY}")
    return url


def _detection_id(lat, lon, acq_iso, satellite, source) -> str:
    h = hashlib.sha1(f"{lat}|{lon}|{acq_iso}|{satellite}|{source}".encode("utf-8"))
    return h.hexdigest()[:16]


def normalize_raw(raw: pd.DataFrame, *, source: str, source_url: str | None,
                  fetched_at: datetime) -> pd.DataFrame:
    """Normalize a raw FIRMS frame (NRT API or archive CSV) -> canonical schema."""
    if raw is None or raw.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)
    d = raw.copy()
    d = d.rename(columns={"latitude": "lat", "longitude": "lon"})
    for col, dt in (("lat", float), ("lon", float), ("frp", float),
                    ("bright_ti4", float), ("bright_ti5", float),
                    ("scan", float), ("track", float)):
        d[col] = pd.to_numeric(d[col], errors="coerce").astype(dt) if col in d else None

    d["acq_time"] = d["acq_time"].astype(str).str.strip().str.zfill(4)
    d["acq_datetime"] = pd.to_datetime(
        d["acq_date"].astype(str).str.strip() + " " + d["acq_time"],
        format="%Y-%m-%d %H%M", utc=True,
    )
    d["confidence_raw"] = d.get("confidence", pd.Series(dtype=str)).map(
        lambda v: str(v) if pd.notna(v) else None)
    d["confidence"] = d["confidence_raw"].map(confidence_to_num)
    d["daynight"] = d["daynight"].astype(str).str.upper().str[0] if "daynight" in d else ""

    d["source"] = source
    d["source_url"] = source_url
    d["fetched_at"] = fetched_at

    d["acq_date"] = d["acq_datetime"].dt.strftime("%Y-%m-%d")
    d["acq_time"] = d["acq_datetime"].dt.strftime("%H%M")
    sat_col = (
        d["satellite"].astype(str).str.strip().fillna("")
        if "satellite" in d.columns
        else pd.Series("", index=d.index)
    )
    d["detection_id"] = [
        _detection_id(la, lo, ts.isoformat(), sa, source)
        for la, lo, ts, sa in zip(
            d["lat"].tolist(), d["lon"].tolist(), d["acq_datetime"].tolist(),
            sat_col.tolist(),
        )
    ]
    for c in CANONICAL_COLUMNS:
        if c not in d.columns:
            d[c] = None
    return d[CANONICAL_COLUMNS].copy()


def validate(df: pd.DataFrame, bbox=None) -> pd.DataFrame:
    """Drop invalid rows: out-of-bbox, NaN coordinates, duplicates."""
    if df.empty:
        return df
    b = bbox or ALGERIA_BBOX
    out = df.dropna(subset=["lat", "lon"]).copy()
    out = out[
        (out["lat"] >= b["lat_min"]) & (out["lat"] <= b["lat_max"])
        & (out["lon"] >= b["lon_min"]) & (out["lon"] <= b["lon_max"])
    ]
    out = out.drop_duplicates(
        subset=["lat", "lon", "acq_datetime", "satellite"], keep="first"
    ).reset_index(drop=True)
    return out


# ---------------------------------------------------------------- fetch paths
def bbox_str(bbox=None) -> str:
    b = bbox or ALGERIA_BBOX
    return f"{b['lon_min']},{b['lat_min']},{b['lon_max']},{b['lat_max']}"


def fetch_nrt_area(map_key: str | None = None, sources=None, day: int = 1,
                   bbox=None) -> pd.DataFrame:
    """FIRMS NRT Area API (real, needs key). Returns one raw frame with 'source'."""
    key = (map_key or FIRMS_MAP_KEY).strip()
    if not key:
        raise RuntimeError("FIRMS_MAP_KEY required for NRT Area API.")
    if day not in (1, 2):
        raise ValueError("NRT area API supports day=1 (24h) or day=2 (48h).")
    sources = sources or FIRMS_SOURCES
    frames = []
    for src in sources:
        url = f"{FIRMS_API_BASE}/{key}/{src}/{day}/{bbox_str(bbox)}"
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        if not r.text.strip():
            continue
        fr = pd.read_csv(io.StringIO(r.text))
        fr["_firms_source"] = src
        fr["_firms_url"] = url
        frames.append(fr)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def fetch_archive(archive_source: str, period: str = "24h") -> tuple[pd.DataFrame, str]:
    """Public FIRMS global archive CSV. Returns (raw frame, url)."""
    if archive_source not in ARCHIVE_LAYOUT:
        raise ValueError(f"unknown archive source {archive_source!r}")
    if period not in ("24h", "48h", "7d"):
        raise ValueError("period must be one of 24h, 48h, 7d")
    subpath, prefix = ARCHIVE_LAYOUT[archive_source]
    url = f"{FIRMS_ARCHIVE_BASE}/{subpath}/csv/{prefix}_Global_{period}.csv"
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    raw = pd.read_csv(io.StringIO(r.text))
    raw["_firms_source"] = archive_source
    raw["_firms_url"] = url
    return raw, url


def fetch_detections(map_key: str | None = None, mode: str = "auto",
                     day: int = 1) -> tuple[pd.DataFrame, dict]:
    """Fetch + normalize + validate real detections.

    Returns (canonical df, meta) where meta has: source, url, fetched_at,
    state ('LIVE'|'HISTORICAL' - computed later at serve time from acq time).
    Raises RuntimeError when no source is reachable/available (failure is
    reported honestly, never replaced with fake data).
    """
    fetched_at = datetime.now(timezone.utc)
    if mode == "auto":
        mode = "api" if (map_key or FIRMS_MAP_KEY) else "archive"

    if mode == "api":
        raw = fetch_nrt_area(map_key=map_key, day=day)
        sources = list(raw["_firms_source"].unique()) if not raw.empty else []
        urls = list(raw["_firms_url"].unique()) if not raw.empty else []
        per_source = mode
    else:
        # archive fallback: merge three VIIRS sources for one period
        frames, urls = [], []
        for key in ARCHIVE_LAYOUT:
            fr, url = fetch_archive(key, period="24h")
            frames.append(fr)
            urls.append(url)
        raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        sources = list(ARCHIVE_LAYOUT)
        per_source = "PUBLIC_ARCHIVE"

    if raw.empty:
        raise RuntimeError("FIRMS returned no data for the requested window.")

    parts = []
    if "_firms_source" in raw.columns:
        for src in raw["_firms_source"].unique():
            sub = raw[raw["_firms_source"] == src]
            url = sub["_firms_url"].iloc[0] if "_firms_url" in sub.columns else None
            norm = normalize_raw(sub.drop(columns=["_firms_source", "_firms_url"]),
                                 source=str(src), source_url=str(url), fetched_at=fetched_at)
            parts.append(norm)
    else:
        norm = normalize_raw(raw, source="FIRMS", source_url=None, fetched_at=fetched_at)
        parts.append(norm)

    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=CANONICAL_COLUMNS)
    df = validate(df)
    meta = {
        "source": per_source,
        "sources": sources,
        "urls": urls,
        "fetched_at": fetched_at,
        "count": len(df),
        "mode": mode,
    }
    return df, meta