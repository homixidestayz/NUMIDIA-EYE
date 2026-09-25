"""Incident domain model: deterministic spatiotemporal grouping of detections.

A FIRMS detection is NOT a confirmed wildfire. An incident is an honest
cluster container: one or more detections close in space and time, with
persistence, satellite agreement and GIS context attached - and an explicit
UNVERIFIED status until validated evidence exists.

Grouping is deterministic (time-ordered greedy chaining, no randomness), so
incident IDs are stable across rebuilds: INC-<sha1(sorted member ids)[:12]>.
Computed on demand from the database; no extra ingestion state required.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from numidia_core import db as db_mod

from . import gis as gis_mod
from . import priority as priority_mod
from . import verification as verification_mod

# Chaining thresholds (methodology "incident-v1", published, not tuned ML).
SPATIAL_EPS_DEG = 0.03   # ~3 km chaining radius between consecutive members
TEMPORAL_GAP_HOURS = 24.0  # max gap between a detection and an open incident
METHODOLOGY = "incident-v1 (time-ordered greedy chaining, eps=0.03deg, gap=24h)"


def _haversine_deg(lat1: float, lon1: float,
                   lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """Great-circle distance in degrees between one point and arrays."""
    lat1r, lon1r = np.radians(lat1), np.radians(lon1)
    lat2r, lon2r = np.radians(lat2), np.radians(lon2)
    dlat, dlon = lat2r - lat1r, lon2r - lon1r
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2.0) ** 2
    return np.degrees(2 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0))))


def _parse_acq(value) -> datetime | None:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def group_detections(rows: list[dict]) -> list[list[dict]]:
    """Chain detections (time-ordered) into incident member lists.

    A detection joins the most recently active open incident whose last
    member is within SPATIAL_EPS_DEG and TEMPORAL_GAP_HOURS; otherwise it
    opens a new incident. Rows without usable coordinates/time stand alone.
    """
    timed = []
    for r in rows:
        ts = _parse_acq(r.get("acq_datetime"))
        try:
            lat, lon = float(r.get("lat")), float(r.get("lon"))
        except (TypeError, ValueError):
            lat, lon = None, None
        timed.append((ts, lat, lon, r))
    timed.sort(key=lambda t: (t[0] is None, t[0]))

    incidents: list[dict] = []  # {members, last_ts, last_lat, last_lon}
    for ts, lat, lon, r in timed:
        best, best_ts = None, None
        if ts is not None and lat is not None:
            for inc in incidents:
                if inc["last_ts"] is None or inc["last_lat"] is None:
                    continue
                gap_h = (ts - inc["last_ts"]).total_seconds() / 3600.0
                if gap_h < 0 or gap_h > TEMPORAL_GAP_HOURS:
                    continue
                d = _haversine_deg(
                    lat, lon,
                    np.array([inc["last_lat"]]), np.array([inc["last_lon"]]))[0]
                if d <= SPATIAL_EPS_DEG and (best is None or inc["last_ts"] > best_ts):
                    best, best_ts = inc, inc["last_ts"]
        if best is None:
            incidents.append({"members": [r], "last_ts": ts,
                              "last_lat": lat, "last_lon": lon})
        else:
            best["members"].append(r)
            best["last_ts"] = ts
            best["last_lat"] = lat
            best["last_lon"] = lon
    return [inc["members"] for inc in incidents]


def incident_id_for(member_ids: list[str]) -> str:
    digest = hashlib.sha1("|".join(sorted(member_ids)).encode("utf-8")).hexdigest()
    return f"INC-{digest[:12]}"


def summarize(members: list[dict]) -> dict:
    """Build an IncidentSummary-shaped dict from member rows (DB rows)."""
    ids = [str(m.get("detection_id")) for m in members if m.get("detection_id")]
    inc_id = incident_id_for(ids) if ids else "INC-empty"
    clean_lats, clean_lons = [], []
    for m in members:
        try:
            clean_lats.append(float(m["lat"]))
            clean_lons.append(float(m["lon"]))
        except (TypeError, ValueError):
            continue  # non-numeric coordinates never join the centroid
    times = sorted(t for t in (_parse_acq(m.get("acq_datetime")) for m in members) if t)
    frps = []
    for m in members:
        try:
            frps.append(float(m.get("frp") or 0.0))
        except (TypeError, ValueError):
            continue
    sats = sorted({str(m["satellite"]) for m in members if m.get("satellite")})
    wilayas = sorted({str(m["wilaya_name"]) for m in members if m.get("wilaya_name")})
    first, last = (times[0], times[-1]) if times else (None, None)
    persist_h = ((last - first).total_seconds() / 3600.0) if first and last else 0.0
    verification = verification_mod.incident_verification_state(len(members))
    priority = priority_mod.score_incident(
        detection_count=len(members), max_frp=max(frps) if frps else 0.0,
        persistence_hours=persist_h, satellites=sats,
        verification_status=verification["status"],
    )
    return {
        "id": inc_id,
        "status": "SINGLE_OBSERVATION" if len(members) == 1 else "UNVERIFIED_CLUSTER",
        "detection_count": len(members),
        "first_acq": first.isoformat() if first else None,
        "last_acq": last.isoformat() if last else None,
        "persistence_hours": round(persist_h, 3),
        "centroid_lat": round(float(np.mean(clean_lats)), 5) if clean_lats else None,
        "centroid_lon": round(float(np.mean(clean_lons)), 5) if clean_lons else None,
        "max_frp": round(max(frps), 3) if frps else 0.0,
        "satellites": sats,
        "wilayas": wilayas,
        "verification": verification,
        "priority": priority,
    }


def list_incidents(limit: int = 200, path: Path | str | None = None) -> list[dict]:
    """Group stored detections into incident summaries (newest first)."""
    rows = db_mod.load_detection_rows(limit=5000, path=path)
    groups = group_detections(rows)
    summaries = [summarize(g) for g in groups if g]
    summaries.sort(key=lambda s: (s["last_acq"] is None, s["last_acq"]), reverse=True)
    return summaries[:limit]


def get_incident(incident_id: str, path: Path | str | None = None) -> dict | None:
    """Full incident detail (members + GIS + verification + priority)."""
    for summary in list_incidents(limit=5000, path=path):
        if summary["id"] == incident_id:
            rows = db_mod.load_detection_rows(limit=5000, path=path)
            member_ids = set()
            for group in group_detections(rows):
                if summarize(group)["id"] == incident_id:
                    member_ids = {str(m.get("detection_id")) for m in group}
                    break
            detail = dict(summary)
            detail["member_ids"] = sorted(member_ids)
            if summary["centroid_lat"] is not None:
                detail["gis_context"] = gis_mod.get_context(
                    summary["centroid_lat"], summary["centroid_lon"]).model_dump()
            else:
                detail["gis_context"] = None
            return detail
    return None


def methodology() -> dict:
    return {
        "methodology": METHODOLOGY,
        "spatial_eps_deg": SPATIAL_EPS_DEG,
        "temporal_gap_hours": TEMPORAL_GAP_HOURS,
        "status_vocabulary": ["SINGLE_OBSERVATION", "UNVERIFIED_CLUSTER"],
        "confirmation_policy": ("No incident is ever labeled a confirmed wildfire "
                                "without validated evidence; see verification state."),
    }


def validate_summary(summary: dict) -> dict:
    """Validate an incident summary through the response schema (API use)."""
    from .schemas import IncidentSummary

    return IncidentSummary(**summary).model_dump(mode="json")


def validate_detail(detail: dict) -> dict:
    """Validate an incident detail through the response schema (API use)."""
    from .schemas import IncidentDetail

    return IncidentDetail(**detail).model_dump(mode="json")
