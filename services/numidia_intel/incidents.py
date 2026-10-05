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
import math
from collections.abc import Iterator
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

# Grid cell size of the incident candidate index. Same scale as the chaining
# radius, so only a handful of neighbouring cells can hold a match.
_CELL_DEG = SPATIAL_EPS_DEG


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


def _cell(lat: float, lon: float) -> tuple[int, int]:
    """Grid cell of a point, for the incident candidate index."""
    return (math.floor(lat / _CELL_DEG), math.floor(lon / _CELL_DEG))


def _candidate_cells(lat: float, lon: float) -> Iterator[tuple[int, int]]:
    """Cells that can contain any incident within SPATIAL_EPS_DEG of the point.

    A great-circle distance of at most SPATIAL_EPS_DEG implies
    |dlat| <= SPATIAL_EPS_DEG and |dlon| <= SPATIAL_EPS_DEG / cos(lat), so
    scanning that many cells either side of the point's cell is a guaranteed
    SUPERSET of the matching incidents. A superset is safe: the exact distance
    and time-gap tests still decide every candidate, so this only prunes work,
    never results.
    """
    ci, cj = _cell(lat, lon)
    cos_lat = max(math.cos(math.radians(min(abs(lat), 89.0))), 1e-6)
    span = max(SPATIAL_EPS_DEG, SPATIAL_EPS_DEG / cos_lat)
    ring = int(math.ceil(span / _CELL_DEG)) + 1
    for di in range(-ring, ring + 1):
        for dj in range(-ring, ring + 1):
            yield (ci + di, cj + dj)


def group_detections(rows: list[dict]) -> list[list[dict]]:
    """Chain detections (time-ordered) into incident member lists.

    A detection joins the most recently active open incident whose last
    member is within SPATIAL_EPS_DEG and TEMPORAL_GAP_HOURS; otherwise it
    opens a new incident. Rows without usable coordinates/time stand alone.

    Candidate incidents are looked up through a uniform grid index on the last
    member's position instead of scanning every open incident, which keeps this
    linear rather than quadratic in the number of detections. The chaining rule
    itself is unchanged: the winner is still the matching incident with the
    greatest last acquisition time, ties broken by creation order, and the
    distance test is the same great-circle comparison. test_intel_grouping.py
    pins the two implementations to identical output.
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
    index: dict[tuple[int, int], set[int]] = {}  # cell -> incident indices

    def reindex(idx: int, lat: float | None, lon: float | None) -> None:
        """Keep the open incident under the cell of its LAST member position."""
        for cell, members in index.items():
            if idx in members:
                members.discard(idx)
                if not members:
                    del index[cell]
                break
        if lat is not None and lon is not None:
            index.setdefault(_cell(lat, lon), set()).add(idx)

    for ts, lat, lon, r in timed:
        best, best_ts, best_idx = None, None, None
        if ts is not None and lat is not None and lon is not None:
            seen: set[int] = set()
            for cell in _candidate_cells(lat, lon):
                seen.update(index.get(cell, ()))
            if seen:
                # Sorted scan: deterministic, and `idx` is the creation order
                # used as the tie-break between equal last timestamps.
                cands = [(i, incidents[i]) for i in sorted(seen)]
                # Incidents are re-indexed when their last member moves, so
                # every candidate has usable coordinates and a last timestamp.
                gaps = [(ts - inc["last_ts"]).total_seconds() / 3600.0
                        for _, inc in cands]
                keep = [c for c, g in enumerate(gaps) if 0.0 <= g <= TEMPORAL_GAP_HOURS]
                if keep:
                    lats = np.array([cands[c][1]["last_lat"] for c in keep])
                    lons = np.array([cands[c][1]["last_lon"] for c in keep])
                    dists = _haversine_deg(lat, lon, lats, lons)
                    for c, dist in zip(keep, dists):
                        if dist > SPATIAL_EPS_DEG:
                            continue
                        idx, inc = cands[c]
                        last_ts = inc["last_ts"]
                        if (best is None or last_ts > best_ts
                                or (last_ts == best_ts and idx < best_idx)):
                            best, best_ts, best_idx = inc, last_ts, idx
        if best is None:
            incidents.append({"members": [r], "last_ts": ts,
                              "last_lat": lat, "last_lon": lon})
            if ts is not None and lat is not None and lon is not None:
                index.setdefault(_cell(lat, lon), set()).add(len(incidents) - 1)
        else:
            best["members"].append(r)
            best["last_ts"] = ts
            best["last_lat"] = lat
            best["last_lon"] = lon
            reindex(best_idx, lat, lon)
    return [inc["members"] for inc in incidents]


def incident_id_for(member_ids: list[str]) -> str:
    digest = hashlib.sha1("|".join(sorted(member_ids)).encode("utf-8")).hexdigest()
    return f"INC-{digest[:12]}"


def summarize(members: list[dict], reason: str | None = None) -> dict:
    """Build an IncidentSummary-shaped dict from member rows (DB rows).

    `reason` is the already-resolved model verification message; see
    verification.incident_verification_state for why callers that summarize many
    groups must resolve it once.
    """
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
    verification = verification_mod.incident_verification_state(len(members), reason)
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
    # Resolved once for every group: the message is the same for all of them,
    # but resolving it loads and hashes the model artifact each time.
    reason = verification_mod.unavailability_reason()
    groups = group_detections(rows)
    summaries = [summarize(g, reason) for g in groups if g]
    summaries.sort(key=lambda s: (s["last_acq"] is None, s["last_acq"]), reverse=True)
    return summaries[:limit]


def get_incident(incident_id: str, path: Path | str | None = None) -> dict | None:
    """Full incident detail (members + GIS + verification + priority)."""
    # One grouping pass over the rows, then the first matching group wins.
    # Incident ids are derived from member ids, so the id a group produces here
    # is exactly the one list_incidents would have produced for it.
    rows = db_mod.load_detection_rows(limit=5000, path=path)
    reason = verification_mod.unavailability_reason()
    for group in group_detections(rows):
        summary = summarize(group, reason)
        if summary["id"] != incident_id:
            continue
        detail = dict(summary)
        detail["member_ids"] = sorted({str(m.get("detection_id")) for m in group})
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
