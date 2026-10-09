"""Attaching environmental context to an incident.

An incident is a CLUSTER, not a point. Its centroid can sit a few kilometres from
the individual detections that formed it, which matters because a 5 km threat
buffer is exactly that scale. So this module does two things that are easy to skip
and expensive to get wrong:

1. Fetches at the centroid, and reports how far the centroid is from the
   detections it represents, so a caller can state the precision instead of
   implying a point measurement.
2. Never lets a missing reading become a number. An incident whose environment
   cannot be fetched gets `status: UNAVAILABLE` and a reason - never a wind speed
   of 0.0 m/s, which would read as "perfectly still" and quietly defeat any
   downwind reasoning done with it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from numidia_env import EnvironmentContext, STATUS_AVAILABLE
from numidia_env.cache import DiskCache
from numidia_env.context import default_cache_dir, get_environment

#: Beyond this the centroid stops being a useful stand-in for the cluster.
MAX_PRECISION_M = 15000.0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin
    r = 6371000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(min(1.0, a ** 0.5))


def centroid_spread_m(incident: dict, members: Optional[list[dict]] = None) -> Optional[float]:
    """Greatest distance from the centroid to a member detection, in metres.

    `members` must be supplied by the caller. `get_incident()` returns
    `member_ids`, not member rows, so a function that looked for
    `incident["member_detections"]` would silently report no spread at all -
    which is exactly the kind of empty-but-present reading that makes a stated
    precision claim untrue.
    """
    clat, clon = incident.get("centroid_lat"), incident.get("centroid_lon")
    if members is None:
        members = incident.get("member_detections") or incident.get("detections") or []
    if clat is None or clon is None or not members:
        return None
    distances = []
    for m in members:
        if not isinstance(m, dict):
            continue
        lat, lon = m.get("lat"), m.get("lon")
        if lat is None or lon is None:
            continue
        distances.append(_haversine_m(float(clat), float(clon), float(lat), float(lon)))
    return max(distances) if distances else None


def environment_for_incident(
    incident: dict,
    *,
    members: Optional[list[dict]] = None,
    cache: Optional[DiskCache] = None,
    fetcher: Optional[Callable[[float, float], dict]] = None,
) -> dict:
    """Environmental context for one incident, with its precision stated.

    Never raises and never returns a measurement it did not get.
    """
    clat = incident.get("centroid_lat")
    clon = incident.get("centroid_lon")
    spread = centroid_spread_m(incident, members)

    if clat is None or clon is None:
        return {
            "status": "UNAVAILABLE",
            "reason": "incident has no centroid to sample",
            "attached_to": "incident_centroid",
            "precision": {
                "centroid_spread_m": round(spread, 1) if spread is not None else None,
                "exceeds_max_precision_m": None,
            },
        }

    ctx: EnvironmentContext = get_environment(
        float(clat), float(clon),
        fetcher=fetcher,
        cache=cache if cache is not None else DiskCache(default_cache_dir()),
    )

    payload = ctx.to_dict()
    payload["attached_to"] = "incident_centroid"
    payload["precision"] = {
        "centroid_spread_m": round(spread, 1) if spread is not None else None,
        "max_precision_m": MAX_PRECISION_M,
        # Say so plainly rather than letting a reader assume point accuracy.
        "exceeds_max_precision_m": (
            None if spread is None else bool(spread > MAX_PRECISION_M)
        ),
        "note": (
            "Sampled at the incident centroid, not at each detection. "
            "Distances here describe the cluster, not a single pixel."
        ),
    }
    if ctx.status == STATUS_AVAILABLE:
        payload["reason"] = None
    return payload