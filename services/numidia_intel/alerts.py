"""Alert workflow foundation: prototype-only alert objects with gated states.

DRAFT -> REVIEW_REQUIRED -> APPROVED -> SENT. Forward-only transitions with
per-transition history. Every alert response carries prototype_only=true and
the standing disclaimer: no automatic Civil Protection notification exists.
Stored in the application database (`alerts` table, created lazily here so
ingestion code stays frozen).
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from numidia_core import db as db_mod

from .schemas import AlertOut

TRANSITIONS: dict[str, tuple[str, ...]] = {
    "DRAFT": ("REVIEW_REQUIRED",),
    "REVIEW_REQUIRED": ("APPROVED",),
    "APPROVED": ("SENT",),
    "SENT": (),
}

PROTOTYPE_NOTE = ("Prototype alert workflow only. No integration with Civil "
                  "Protection or any authority exists; SENT means recorded as "
                  "sent inside this prototype, nothing more.")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_tables(path: Path | str | None = None) -> None:
    db_path = db_mod.resolve_db_path(path)
    with db_mod.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
              id TEXT PRIMARY KEY,
              incident_id TEXT NOT NULL,
              note TEXT NOT NULL DEFAULT '',
              state TEXT NOT NULL DEFAULT 'DRAFT',
              history TEXT NOT NULL DEFAULT '[]',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
        """)
        conn.commit()


def _row_to_alert(row: sqlite3.Row) -> dict:
    import json

    d = dict(row)
    try:
        history = json.loads(d.get("history") or "[]")
    except (ValueError, TypeError):
        history = []
    return {
        "id": d["id"],
        "incident_id": d["incident_id"],
        "note": d.get("note") or "",
        "state": d["state"],
        "history": history,
        "created_at": d["created_at"],
        "updated_at": d["updated_at"],
        "prototype_only": True,
    }


def create_alert(incident_id: str, note: str = "",
                 path: Path | str | None = None) -> dict:
    """Create an alert in DRAFT state for a real incident ID (checked by caller)."""
    import json

    ensure_tables(path)
    now = _now_iso()
    alert_id = f"ALR-{uuid.uuid4().hex[:12]}"
    history = [{"at": now, "from": None, "to": "DRAFT", "note": note}]
    with db_mod.connect(path) as conn:
        conn.execute(
            "INSERT INTO alerts (id, incident_id, note, state, history,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (alert_id, incident_id, note, "DRAFT", json.dumps(history), now, now),
        )
        conn.commit()
    return get_alert(alert_id, path=path)


def get_alert(alert_id: str, path: Path | str | None = None) -> dict | None:
    ensure_tables(path)
    with db_mod.connect(path) as conn:
        row = conn.execute("SELECT * FROM alerts WHERE id = ?",
                           (alert_id,)).fetchone()
    return _row_to_alert(row) if row else None


def list_alerts(path: Path | str | None = None) -> list[dict]:
    ensure_tables(path)
    with db_mod.connect(path) as conn:
        rows = conn.execute(
            "SELECT * FROM alerts ORDER BY created_at DESC").fetchall()
    return [_row_to_alert(r) for r in rows]


def transition(alert_id: str, to_state: str,
               path: Path | str | None = None) -> dict:
    """Move an alert forward one gated step. Raises ValueError on misuse."""
    import json

    if to_state not in TRANSITIONS:
        raise ValueError(f"unknown alert state: {to_state!r}")
    current = get_alert(alert_id, path=path)
    if current is None:
        raise ValueError(f"unknown alert: {alert_id!r}")
    allowed = TRANSITIONS.get(current["state"], ())
    if to_state not in allowed:
        raise ValueError(
            f"transition {current['state']} -> {to_state} not allowed "
            f"(allowed: {list(allowed) or 'none - terminal state'})")
    now = _now_iso()
    history = list(current["history"]) + [
        {"at": now, "from": current["state"], "to": to_state}]
    with db_mod.connect(path) as conn:
        conn.execute("UPDATE alerts SET state = ?, history = ?, updated_at = ?"
                     " WHERE id = ?",
                     (to_state, json.dumps(history), now, alert_id))
        conn.commit()
    out = get_alert(alert_id, path=path)
    out["prototype_note"] = PROTOTYPE_NOTE
    return out


def validate_out(payload: dict) -> dict:
    """Validate an alert payload through the pydantic schema (for API use)."""
    return AlertOut(**payload).model_dump()
