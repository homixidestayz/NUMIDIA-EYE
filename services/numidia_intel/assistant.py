"""Chatbot backend foundation: a tool-oriented retrieval interface.

This is NOT an LLM classifier and contains no language model. It is a strict
dispatcher over read-only retrieval tools so that an eventual assistant (built
by the frontend team or later backend work) answers from NUMIDIA EYE data
rather than inventing facts. Unknown tools/args are rejected, never guessed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from numidia_core import db as db_mod

from . import gis as gis_mod
from . import incidents as incidents_mod
from . import reports as reports_mod
from . import verification as verification_mod


def _parse_limit(args: dict) -> int:
    """Parse the `limit` arg; malformed values raise ValueError (API maps to 400)."""
    try:
        limit = int(args.get("limit", 20))
    except (TypeError, ValueError):
        raise ValueError("limit must be an integer 1..200")
    return max(1, min(200, limit))


def _tool_detections_search(args: dict, db_path) -> dict:
    from numidia_api.app import _detection_from_row  # local import: API presentation stays in API layer
    from datetime import datetime, timezone

    limit = _parse_limit(args)
    rows = db_mod.load_detection_rows(
        limit=limit, source=args.get("source"), satellite=args.get("satellite"),
        path=db_path)
    summary = db_mod.data_state_summary(path=db_path)
    now = datetime.now(timezone.utc)
    return {
        "count": len(rows),
        "detections": [
            _detection_from_row(r, summary["ingest_fresh"], now).model_dump(mode="json")
            for r in rows
        ],
    }


def _tool_detections_get(args: dict, db_path) -> dict:
    from datetime import datetime, timezone

    from numidia_api.app import _detection_from_row

    det_id = str(args.get("detection_id", ""))
    row = db_mod.get_detection_row(det_id, path=db_path)
    if row is None:
        return {"found": False, "detection_id": det_id}
    summary = db_mod.data_state_summary(path=db_path)
    det = _detection_from_row(row, summary["ingest_fresh"], datetime.now(timezone.utc))
    return {"found": True, "detection": det.model_dump(mode="json")}


def _tool_incidents_list(args: dict, db_path) -> dict:
    limit = _parse_limit(args)
    items = incidents_mod.list_incidents(limit=limit, path=db_path)
    return {"count": len(items), "incidents": items}


def _tool_incidents_get(args: dict, db_path) -> dict:
    inc = incidents_mod.get_incident(str(args.get("incident_id", "")), path=db_path)
    return {"found": inc is not None, "incident": inc}


def _tool_system_status(args: dict, db_path) -> dict:
    return db_mod.data_state_summary(path=db_path)


def _tool_reports_get(args: dict, db_path) -> dict:
    rep = reports_mod.build_report(str(args.get("incident_id", "")), path=db_path)
    return {"found": rep is not None, "report": rep}


def _tool_gis_lookup(args: dict, db_path) -> dict:
    return gis_mod.get_context(args.get("lat"), args.get("lon")).model_dump()


def _tool_verification_get(args: dict, db_path) -> dict:
    return verification_mod.detection_verification_state(str(args.get("detection_id", "")))


TOOLS: dict[str, dict[str, Any]] = {
    "detections.search": {
        "description": "Search stored FIRMS detections (newest first). Retrieval only.",
        "args": {"limit": "int 1..200 (default 20)", "source": "optional source string",
                 "satellite": "optional satellite code"},
        "handler": _tool_detections_search,
    },
    "detections.get": {
        "description": "Get one stored detection by ID. Retrieval only.",
        "args": {"detection_id": "required string"},
        "handler": _tool_detections_get,
    },
    "incidents.list": {
        "description": "List incident clusters (unverified groupings, newest first).",
        "args": {"limit": "int 1..200 (default 20)"},
        "handler": _tool_incidents_list,
    },
    "incidents.get": {
        "description": "Get one incident with members, verification, GIS and priority.",
        "args": {"incident_id": "required string"},
        "handler": _tool_incidents_get,
    },
    "system.status": {
        "description": "Database freshness summary (data_state, counts, last run).",
        "args": {},
        "handler": _tool_system_status,
    },
    "reports.get": {
        "description": "Build the structured report for an incident from stored data.",
        "args": {"incident_id": "required string"},
        "handler": _tool_reports_get,
    },
    "gis.lookup": {
        "description": "GIS context for coordinates (wilaya real; other layers UNAVAILABLE).",
        "args": {"lat": "required float", "lon": "required float"},
        "handler": _tool_gis_lookup,
    },
    "verification.get": {
        "description": "AI verification state for a detection (UNAVAILABLE until a model registers).",
        "args": {"detection_id": "required string"},
        "handler": _tool_verification_get,
    },
}


def catalog() -> dict:
    """Public tool catalog (no handlers, safe to expose)."""
    return {"tools": [
        {"name": name, "description": spec["description"], "args": spec["args"]}
        for name, spec in TOOLS.items()
    ]}


def dispatch(tool: str, args: dict | None,
             db_path: Path | str | None = None) -> dict:
    """Run one retrieval tool. Unknown tools/args are rejected, never guessed."""
    spec = TOOLS.get(tool or "")
    if spec is None:
        raise ValueError(f"unknown tool: {tool!r}. See /assistant/tools for the catalog.")
    handler: Callable = spec["handler"]
    return {"tool": tool, "ok": True, "result": handler(dict(args or {}), db_path)}
