"""NUMIDIA EYE API - clean boundary between data and the frontend.

Serves ONLY real data. If a live fetch has never happened, the API serves the
committed real historical FIRMS snapshot and reports an honest data_state.
AI endpoints return 503 AI_UNAVAILABLE until a real model is trained.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from numidia_core import firms as firms_mod
from numidia_core import storage
from numidia_core.config import LIVE_WINDOW_HOURS
from numidia_core.processing import derive_features
from numidia_core.schemas import AiResult, Detection, SystemStatus

app = FastAPI(
    title="NUMIDIA EYE API",
    version="0.1.0",
    description="Wildfire intelligence for Algeria - real data only. Independent prototype, non-official.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # prototype dev boundary; tighten before any production use
    allow_methods=["*"],
    allow_headers=["*"],
)


def _clean(value):
    """NaN/<NA> -> None so pydantic receives clean optional values."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, str) and value.strip().lower() in ("nan", "nat", "none", ""):
        return None
    return value


def _detection_from_row(row: pd.Series) -> Detection:
    now = datetime.now(timezone.utc)
    acq = row.get("acq_datetime")
    acq = pd.to_datetime(acq, utc=True).to_pydatetime() if pd.notna(acq) else now

    state = "LIVE" if (now - acq) <= timedelta(hours=LIVE_WINDOW_HOURS) else "HISTORICAL"

    acq_time = _clean(row.get("acq_time"))
    if acq_time is not None:
        try:
            acq_time = str(int(acq_time)).zfill(4)
        except (ValueError, TypeError):
            pass

    payload = {
        "detection_id": _clean(row.get("detection_id")),
        "lat": _clean(row.get("lat")),
        "lon": _clean(row.get("lon")),
        "acq_datetime": acq,
        "acq_date": _clean(row.get("acq_date")),
        "acq_time": acq_time,
        "satellite": _clean(row.get("satellite")),
        "instrument": _clean(row.get("instrument")),
        "confidence": _clean(row.get("confidence")),
        "confidence_raw": _clean(row.get("confidence_raw")),
        "bright_ti4": _clean(row.get("bright_ti4")),
        "bright_ti5": _clean(row.get("bright_ti5")),
        "scan": _clean(row.get("scan")),
        "track": _clean(row.get("track")),
        "frp": _clean(row.get("frp")),
        "daynight": _clean(row.get("daynight")),
        "version": _clean(row.get("version")),
        "source": _clean(row.get("source")) or "FIRMS",
        "source_url": _clean(row.get("source_url")),
        "fetched_at": pd.to_datetime(row.get("fetched_at"), utc=True).to_pydatetime()
        if pd.notna(row.get("fetched_at")) else now,
        "state": state,
    }
    # pass through derived f_* features for transparency/verifier debugging
    for col in row.index:
        if col.startswith("f_"):
            payload[col] = _clean(row[col])
    return Detection(**payload)


def _load_detections() -> list[Detection]:
    df = storage.load_processed("firms_features")
    source_desc = "data/processed/firms_features.csv"
    if df is None:
        raw = storage.load_raw_snapshot(storage.SAMPLE_RAW)
        if raw is None:
            return []
        df = firms_mod.normalize_raw(
            raw, source="VIIRS_NOAA21_NRT", source_url=None,
            fetched_at=datetime.now(timezone.utc),
        )
        df = firms_mod.validate(df)
        df = derive_features(df)
        source_desc = "data/raw/firms (committed real snapshot)"
    return [d for _, row in df.iterrows() if (d := _detection_from_row(row))], source_desc  # noqa: E203


DETECTIONS, DATA_SOURCE = _load_detections()
BY_ID = {d.detection_id: d for d in DETECTIONS}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat(), "service": "numidia_api"}


@app.get("/system/status", response_model=SystemStatus)
def system_status() -> SystemStatus:
    snap = storage.latest_raw_snapshot()
    live = sum(1 for d in DETECTIONS if d.state == "LIVE")
    last_fetch = max((d.fetched_at for d in DETECTIONS), default=None)

    if not DETECTIONS:
        data_state = "UNAVAILABLE"
    elif live > 0:
        data_state = "LIVE"
    else:
        data_state = "HISTORICAL"

    message = (
        f"Real VIIRS detections: {len(DETECTIONS)} ({live} live). "
        "AI verifier is UNAVAILABLE until a labeled dataset + trained model exist. "
        "Alerts are PROTOTYPE ONLY - not connected to Civil Protection."
    )
    return SystemStatus(
        firms="CONNECTED" if snap is not None else "UNAVAILABLE",
        firms_last_fetch=last_fetch,
        ai="UNAVAILABLE",
        model=None,
        db="OK",
        data_state=data_state,
        detections_count=len(DETECTIONS),
        message=message,
    )


@app.get("/system/data")
def system_data() -> dict:
    return {
        "data_source": DATA_SOURCE,
        "detections": len(DETECTIONS),
        "sources": sorted({d.source for d in DETECTIONS}),
        "satellites": sorted({d.satellite for d in DETECTIONS if d.satellite}),
        "bbox": {"lon_min": -9.0, "lat_min": 18.0, "lon_max": 12.0, "lat_max": 38.0},
        "snapshots": [str(p) for p in storage.list_raw_snapshots()],
        "note": "All values are real FIRMS/VIIRS data. AI fields intentionally absent.",
    }


@app.get("/detections", response_model=list[Detection])
def list_detections(
    source: Optional[str] = None,
    satellite: Optional[str] = None,
    state: Optional[str] = Query(default=None, pattern="^(LIVE|HISTORICAL|SAMPLE|DEMO|UNAVAILABLE)$"),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[Detection]:
    out = DETECTIONS
    if source:
        out = [d for d in out if d.source == source]
    if satellite:
        out = [d for d in out if d.satellite == satellite]
    if state:
        out = [d for d in out if d.state == state]
    out = sorted(out, key=lambda d: d.acq_datetime, reverse=True)
    return out[:limit]


@app.get("/detections/{detection_id}", response_model=Detection)
def get_detection(detection_id: str) -> Detection:
    d = BY_ID.get(detection_id)
    if d is None:
        raise HTTPException(status_code=404, detail="detection not found")
    return d


@app.get("/detections/{detection_id}/ai", response_model=AiResult, status_code=503)
def ai_verify(detection_id: str) -> AiResult:
    """AI verification endpoint.

    Returns an explicit 503 AI_UNAVAILABLE: no fabricated probabilities are
    ever served. This flips to a real model response once trained
    (services/ml) with a labeled dataset and evaluation.
    """
    if detection_id not in BY_ID:
        raise HTTPException(status_code=404, detail="detection not found")
    return AiResult(
        status="AI_UNAVAILABLE",
        detection_id=detection_id,
        message=(
            "No AI verifier is available yet: training requires a labeled "
            "dataset of confirmed fire/non-fire VIIRS events, which have not "
            "been produced. Probability is intentionally NOT reported."
        ),
    )


@app.get("/incidents")
def list_incidents() -> dict:
    """Incident engine is part of a later phase; this is an honest empty state."""
    return {
        "status": "NOT_IMPLEMENTED",
        "incidents": [],
        "message": (
            "Incident clustering needs the AI-verified detections pipeline; "
            "not available until the verifier model is trained. No invented incidents."
        ),
    }