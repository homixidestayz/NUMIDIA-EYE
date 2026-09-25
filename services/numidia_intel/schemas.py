"""Response schemas for the intelligence layer (pydantic).

These shapes are part of the frontend contract (see docs/api-contract.md).
Field names are stable: additive changes only.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict

VerificationStatus = Literal[
    "UNAVAILABLE", "PENDING", "PROCESSING", "VERIFIED", "REJECTED", "UNCERTAIN",
]

AlertState = Literal["DRAFT", "REVIEW_REQUIRED", "APPROVED", "SENT"]


class VerificationEvidence(BaseModel):
    source: str
    model: Optional[str] = None
    model_version: Optional[str] = None
    timestamp: str
    evidence: dict[str, Any] = {}
    confidence: Optional[float] = None  # only when an evaluated model produced it


class VerificationState(BaseModel):
    status: VerificationStatus = "UNAVAILABLE"
    evaluated: bool = False
    model: Optional[str] = None
    message: str = ""
    evidence: list[VerificationEvidence] = []


class GisLayer(BaseModel):
    data_available: bool
    status: Literal["OK", "UNAVAILABLE"] = "UNAVAILABLE"
    value: Optional[Any] = None
    source: Optional[str] = None
    reason: Optional[str] = None


class GisContext(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None
    wilaya: GisLayer
    settlement: GisLayer
    road: GisLayer
    elevation: GisLayer
    slope: GisLayer
    forest_cover: GisLayer


class PriorityFactor(BaseModel):
    name: str
    value: Optional[float] = None
    normalized: Optional[float] = None
    weight: float = 0.0
    evidence: str = ""


class PriorityResult(BaseModel):
    level: Literal["LOW", "MODERATE", "HIGH", "CRITICAL", "UNKNOWN"] = "UNKNOWN"
    score: Optional[float] = None
    factors: list[PriorityFactor] = []
    unavailable_factors: list[str] = []
    methodology: str = ""
    computed_at: str = ""


class IncidentSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    status: str  # SINGLE_OBSERVATION | UNVERIFIED_CLUSTER (never "confirmed wildfire")
    detection_count: int
    first_acq: Optional[str] = None
    last_acq: Optional[str] = None
    persistence_hours: float = 0.0
    centroid_lat: Optional[float] = None
    centroid_lon: Optional[float] = None
    max_frp: float = 0.0
    satellites: list[str] = []
    wilayas: list[str] = []
    verification: VerificationState = VerificationState()
    priority: PriorityResult = PriorityResult()


class IncidentDetail(IncidentSummary):
    member_ids: list[str] = []
    gis_context: Optional[GisContext] = None


class ReportDoc(BaseModel):
    model_config = ConfigDict(extra="allow")

    incident_id: str
    generated_at: str
    detection_count: int
    first_acq: Optional[str] = None
    last_acq: Optional[str] = None
    centroid_lat: Optional[float] = None
    centroid_lon: Optional[float] = None
    max_frp: float = 0.0
    frp_sum: float = 0.0
    satellites: list[str] = []
    verification: VerificationState = VerificationState()
    gis_context: Optional[GisContext] = None
    priority: PriorityResult = PriorityResult()
    sources: list[str] = []
    limitations: list[str] = []
    provenance: dict[str, Any] = {}


class AlertOut(BaseModel):
    id: str
    incident_id: str
    note: str = ""
    state: AlertState = "DRAFT"
    history: list[dict[str, Any]] = []
    created_at: str = ""
    updated_at: str = ""
    prototype_only: bool = True
