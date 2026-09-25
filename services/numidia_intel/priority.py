"""Priority engine foundation: transparent, rule-based, evidence-carrying.

Methodology priority-v1 (published, deterministic, no ML, no arbitrary score):
only factors backed by REAL data contribute. Every factor carries its value,
normalization, weight and evidence string; unavailable factors are listed
separately and contribute zero. Result: level + score + full breakdown +
methodology version + timestamp.

Weights v1: thermal intensity 0.40, persistence 0.25, detection count 0.20,
multi-satellite agreement 0.15. Normalization caps: FRP 100 MW (log),
persistence 72 h, count 20 detections.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

METHODOLOGY = ("priority-v1: score = 0.40*frp_norm + 0.25*persist_norm + "
               "0.20*count_norm + 0.15*sat_agree; caps frp=100MW(log), "
               "persistence=72h, count=20; tiers LOW<0.25<=MODERATE<0.5<=HIGH<0.75<=CRITICAL")

WEIGHTS = {"thermal_intensity": 0.40, "persistence": 0.25,
           "detection_count": 0.20, "satellite_agreement": 0.15}

UNAVAILABLE_FACTOR_NAMES = [
    "proximity_to_settlements",
    "proximity_to_critical_infrastructure",
    "terrain_accessibility",
    "protected_forest_context",
    "visual_verification",
]


def _norm_frp(frp: float) -> float:
    try:
        v = float(frp)
    except (TypeError, ValueError):
        return 0.0
    if v <= 0:
        return 0.0
    return min(1.0, math.log10(1.0 + v) / math.log10(101.0))


def _norm_capped(value: float, cap: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, v) / cap)


def score_incident(*, detection_count: int, max_frp: float,
                   persistence_hours: float, satellites: list[str],
                   verification_status: str = "UNAVAILABLE") -> dict:
    """Score an incident from real factors only. Returns a PriorityResult dict."""
    frp_n = _norm_frp(max_frp)
    persist_n = _norm_capped(persistence_hours, 72.0)
    count_n = _norm_capped(detection_count, 20.0)
    try:
        sats = {str(s) for s in (satellites or []) if s}
    except TypeError:
        sats = set()
    sat_n = min(1.0, len(sats) / 3.0)

    factors = [
        {"name": "thermal_intensity", "value": round(float(max_frp or 0.0), 3),
         "normalized": round(frp_n, 4), "weight": WEIGHTS["thermal_intensity"],
         "evidence": f"max FRP {round(float(max_frp or 0.0), 3)} MW across members"},
        {"name": "persistence", "value": round(float(persistence_hours or 0.0), 3),
         "normalized": round(persist_n, 4), "weight": WEIGHTS["persistence"],
         "evidence": f"{round(float(persistence_hours or 0.0), 3)} h between first/last acquisition"},
        {"name": "detection_count", "value": int(detection_count or 0),
         "normalized": round(count_n, 4), "weight": WEIGHTS["detection_count"],
         "evidence": f"{int(detection_count or 0)} grouped detection(s)"},
        {"name": "satellite_agreement",
         "value": float(len(sats)),
         "normalized": round(sat_n, 4), "weight": WEIGHTS["satellite_agreement"],
         "evidence": f"{len(sats)} distinct satellite(s): {sorted(sats) or 'none'}"},
    ]
    score = round(sum(f["normalized"] * f["weight"] for f in factors), 4)
    if score < 0.25:
        level = "LOW"
    elif score < 0.5:
        level = "MODERATE"
    elif score < 0.75:
        level = "HIGH"
    else:
        level = "CRITICAL"
    unavailable = list(UNAVAILABLE_FACTOR_NAMES)
    if (verification_status or "UNAVAILABLE") != "UNAVAILABLE":
        pass  # future evaluated verification may contribute; today it cannot
    return {
        "level": level,
        "score": score,
        "factors": factors,
        "unavailable_factors": unavailable,
        "methodology": METHODOLOGY,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
