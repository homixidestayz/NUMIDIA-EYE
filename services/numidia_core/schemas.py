"""Shared API/data schemas (pydantic)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

# LIVE and HISTORICAL describe detection freshness; STALE means the ingestion
# pipeline itself is too old to trust (never shown as LIVE); SAMPLE/DEMO are
# for explicitly labelled non-production views; UNAVAILABLE = no data at all.
DataState = Literal["LIVE", "HISTORICAL", "STALE", "SAMPLE", "DEMO", "UNAVAILABLE"]


class Detection(BaseModel):
    """One real active-fire detection from NASA FIRMS/VIIRS."""

    model_config = ConfigDict(extra="allow")

    detection_id: str
    lat: float
    lon: float
    acq_datetime: datetime      # source timestamp (satellite observation, UTC)
    acq_date: str
    acq_time: str
    satellite: Optional[str] = None
    instrument: Optional[str] = None
    confidence: Optional[float] = None      # normalized 0..1 (never fabricated)
    confidence_raw: Optional[str] = None    # original FIRMS value
    bright_ti4: Optional[float] = None      # I4 band brightness temp (K)
    bright_ti5: Optional[float] = None      # I5 band brightness temp (K)
    scan: Optional[float] = None
    track: Optional[float] = None
    frp: float = 0.0                        # Fire Radiative Power (MW) - VIIRS
    daynight: Optional[str] = None          # D / N
    version: Optional[str] = None           # e.g. 2.0NRT
    source: str                             # e.g. VIIRS_NOAA21_NRT
    source_url: Optional[str] = None        # API key ALWAYS redacted
    fetched_at: datetime                    # ingestion timestamp (UTC)
    wilaya_code: Optional[str] = None       # e.g. "16" (GIS enrichment)
    wilaya_name: Optional[str] = None       # e.g. "Alger" (GIS enrichment)
    state: DataState = "HISTORICAL"
    # AI fields are absent until an actual evaluated model exists.


class AiResult(BaseModel):
    status: str = "AI_UNAVAILABLE"
    detection_id: Optional[str] = None
    probability: Optional[float] = None
    verified: Optional[bool] = None
    model: Optional[str] = None
    message: str


class IngestRun(BaseModel):
    run_id: Optional[int] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    mode: str                                # api | archive | skipped
    sources: list[str] = []
    urls: list[str] = []                     # redacted
    count_new: int = 0
    count_total: int = 0
    status: str                              # ok | error | skipped
    message: str = ""


class Incident(BaseModel):
    id: str
    status: str = "OPEN"
    # Populated by the incident engine in a later phase.


class SystemStatus(BaseModel):
    firms: str = "NOT_CONFIGURED"      # CONNECTED / STALE / DEGRADED / NOT_CONFIGURED / STARTING
    firms_last_fetch: Optional[datetime] = None
    ai: str = "UNAVAILABLE"            # READY / UNAVAILABLE
    model: Optional[str] = None
    db: str = "OK"
    data_state: DataState = "UNAVAILABLE"
    detections_count: int = 0
    message: str = ""