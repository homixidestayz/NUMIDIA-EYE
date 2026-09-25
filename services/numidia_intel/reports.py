"""Structured incident-report service: reports strictly from stored data.

A report contains only what the database (plus deterministic computation over
it) supports: IDs, timestamps, coordinates, satellites, FRP, verification
state, GIS evidence, priority factors, sources, and an explicit limitations
section. Anything not in the database appears under limitations, never as a
claimed fact.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from . import gis as gis_mod
from . import incidents as incidents_mod

REPORT_METHODOLOGY = "report-v1 (incident detail + priority-v1 + gis + verification contract)"


def base_limitations(summary: dict) -> list[str]:
    out = [
        "Independent prototype, non-official data product; not Civil Protection output.",
        "Incident members are grouped FIRMS detections, not confirmed wildfires.",
        "AI verification unavailable: no evaluated verifier model is registered.",
        "GIS context limited to wilaya polygons; settlement/road/elevation/slope/forest layers unavailable.",
    ]
    if len(summary.get("satellites", [])) < 2:
        out.append("Single-satellite observation: no multi-satellite agreement for this incident.")
    if summary.get("detection_count", 0) == 1:
        out.append("Single detection: persistence cannot be assessed.")
    return out


def build_report(incident_id: str, path: Path | str | None = None) -> dict | None:
    """Assemble the report document for an incident, or None if unknown."""
    detail = incidents_mod.get_incident(incident_id, path=path)
    if detail is None:
        return None
    rows_member_frps: list[float] = []
    try:
        from numidia_core import db as db_mod

        for det_id in detail.get("member_ids", []):
            row = db_mod.get_detection_row(det_id, path=path)
            if row and row.get("frp") is not None:
                try:
                    rows_member_frps.append(float(row["frp"]))
                except (TypeError, ValueError):
                    continue
    except Exception:  # noqa: BLE001 - report degrades honestly, never invents
        rows_member_frps = []
    gis_ctx = detail.get("gis_context")
    if gis_ctx is None and detail.get("centroid_lat") is not None:
        gis_ctx = gis_mod.get_context(
            detail["centroid_lat"], detail["centroid_lon"]).model_dump()
    return {
        "incident_id": detail["id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "detection_count": detail["detection_count"],
        "first_acq": detail["first_acq"],
        "last_acq": detail["last_acq"],
        "centroid_lat": detail["centroid_lat"],
        "centroid_lon": detail["centroid_lon"],
        "max_frp": detail["max_frp"],
        "frp_sum": round(sum(rows_member_frps), 3),
        "satellites": detail["satellites"],
        "verification": detail["verification"],
        "gis_context": gis_ctx,
        "priority": detail["priority"],
        "sources": member_sources(detail, path),
        "limitations": base_limitations(detail),
        "provenance": {
            "methodology": REPORT_METHODOLOGY,
            "incident_methodology": incidents_mod.methodology()["methodology"],
            "generator": "numidia_intel.reports.build_report",
        },
    }


def validate_report(report: dict) -> dict:
    """Validate a report document through the response schema (API use)."""
    from .schemas import ReportDoc

    return ReportDoc(**report).model_dump(mode="json")


def member_sources(detail: dict, path) -> list[str]:
    """Distinct FIRMS source strings across member rows (empty when none)."""
    try:
        from numidia_core import db as db_mod

        sources = set()
        for det_id in detail.get("member_ids", []):
            row = db_mod.get_detection_row(det_id, path=path)
            if row and row.get("source"):
                sources.add(str(row["source"]))
        return sorted(sources)
    except Exception:  # noqa: BLE001
        return []
