"""AI verification contract: states, evidence, and the honest default.

Statuses: UNAVAILABLE (no model/evidence path) | PENDING | PROCESSING |
VERIFIED | REJECTED | UNCERTAIN. Until a trained, evaluated verifier model is
registered, every query returns UNAVAILABLE with zero evidence rows and no
confidence value. Confidence appears ONLY when produced by an evaluated model.
"""
from __future__ import annotations

from datetime import datetime, timezone

from numidia_core import pipeline as pipeline_mod

from .schemas import VerificationState


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def unavailability_reason() -> str:
    return pipeline_mod.verification_status().get("message", "AI verifier unavailable.")


def detection_verification_state(detection_id: str) -> dict:
    """Verification state for one detection. Always UNAVAILABLE today."""
    return VerificationState(
        status="UNAVAILABLE",
        evaluated=False,
        model=None,
        message=unavailability_reason(),
        evidence=[],
    ).model_dump()


def incident_verification_state(member_count: int) -> dict:
    """Verification state for an incident. Always UNAVAILABLE today."""
    state = detection_verification_state("")
    state["message"] = (
        f"{member_count} detection(s) grouped without validated evidence. "
        + unavailability_reason()
    )
    return state


def contract() -> dict:
    """The verification contract (states, fields, and current readiness)."""
    return {
        "statuses": ["UNAVAILABLE", "PENDING", "PROCESSING",
                     "VERIFIED", "REJECTED", "UNCERTAIN"],
        "status_meanings": {
            "UNAVAILABLE": "no model or evidence path exists; nothing was evaluated",
            "PENDING": "queued for verification by a registered model",
            "PROCESSING": "a registered model is currently evaluating",
            "VERIFIED": "an evaluated model confirmed fire with logged evidence",
            "REJECTED": "an evaluated model rejected fire with logged evidence",
            "UNCERTAIN": "an evaluated model could not decide; evidence logged",
        },
        "evidence_fields": ["source", "model", "model_version", "timestamp",
                            "evidence", "confidence (model-produced only)"],
        "current": {
            "status": "UNAVAILABLE",
            "evaluated": False,
            "model": None,
            "message": unavailability_reason(),
        },
    }
