"""Production ingestion pipeline.

FIRMS API (NRT, server-side key) -> normalize -> validate -> feature
extraction -> GIS enrichment -> application database -> ingest-run record.

New detections automatically flow through every stage on each run. The ML
verification hook (`verification_status`) reports AI_UNAVAILABLE until a
trained, evaluated verifier model is registered - no fake probabilities or
classifications are ever produced, and no LLM stands in for the verifier.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import db as db_mod
from . import firms as firms_mod
from .config import ACTIVE_MODEL, DB_PATH, FIRMS_MAP_KEY, INGEST_DAY, INGEST_MODE
from .enrichment import assign_wilaya, clip_to_algeria
from .processing import derive_features
from .storage import save_audit_snapshot


def verification_status(model_path: str | None = None) -> dict:
    """Honest AI readiness check. Always UNAVAILABLE until a real verifier."""
    mp = (model_path or ACTIVE_MODEL).strip()
    if not mp:
        return {
            "status": "AI_UNAVAILABLE",
            "model": None,
            "message": (
                "No trained verifier is registered (NUMIDIA_ACTIVE_MODEL is "
                "unset). Training requires a labeled dataset of confirmed "
                "fire/non-fire VIIRS events - see docs/labeling-proposal.md. "
                "Probabilities are intentionally NOT served."
            ),
        }
    if not Path(mp).exists():
        return {
            "status": "AI_UNAVAILABLE",
            "model": mp,
            "message": "Registered model file is missing; refusing to serve.",
        }
    return {
        "status": "AI_UNAVAILABLE",
        "model": mp,
        "message": (
            "A model file exists but no evaluated verifier module is wired "
            "into the pipeline - unevaluated predictions are refused."
        ),
    }


def process_frame(df: pd.DataFrame, db_path: Path | str | None = None) -> dict:
    """Validate -> features -> wilaya enrichment -> Algeria clip -> DB upsert."""
    valid = firms_mod.validate(df)
    feats = derive_features(valid)
    in_algeria, excluded = clip_to_algeria(feats)
    res = db_mod.upsert_detections(in_algeria, path=db_path)
    return {"validated": len(valid), "with_features": len(feats),
            "excluded_outside_algeria": excluded,
            "in_algeria": len(in_algeria),
            "new": res["new"], "total": res["total"]}


def run_ingest(db_path: Path | str | None = None, map_key: str | None = None,
               mode: str | None = None, day: int | None = None,
               audit: bool = True) -> dict:
    """One full ingestion run. Returns a summary; failures record error runs."""
    db_path = db_mod.resolve_db_path(db_path)
    db_mod.init_db(db_path)
    started = db_mod.utcnow_iso()
    mode = (mode or INGEST_MODE).lower()
    day = INGEST_DAY if day is None else day
    key = (map_key if map_key is not None else FIRMS_MAP_KEY).strip()

    if mode == "api" and not key:
        msg = ("FIRMS_MAP_KEY is not configured on the server; NRT fetch "
               "refused (no key is ever requested from, or exposed to, clients).")
        db_mod.record_run(mode="api", sources=[], urls=[], count_new=0,
                          count_total=db_mod.detection_stats(db_path)["count"],
                          status="skipped", message=msg,
                          started_at=started, path=db_path)
        return {"status": "skipped", "mode": mode, "message": msg,
                "verification": verification_status()}

    try:
        df, meta = firms_mod.fetch_detections(
            map_key=key or None, mode=mode, day=day)
    except Exception as exc:  # noqa: BLE001 - record honestly, never fabricate
        # The exception text carries the request URL: redact the key first.
        msg = f"FIRMS fetch failed: {firms_mod.redact_key_from_text(str(exc), key)}"
        db_mod.record_run(
            mode=mode, sources=[], urls=[], count_new=0,
            count_total=db_mod.detection_stats(db_path)["count"],
            status="error", message=msg[:500],
            started_at=started, path=db_path)
        return {"status": "error", "mode": mode, "message": msg,
                "verification": verification_status()}

    counts = process_frame(df, db_path)
    redacted_urls = [firms_mod.redact_url(u, key) for u in meta.get("urls", [])]
    # Store redacted provenance on the fresh batch (key never touches the DB).
    _redact_stored_urls(db_path, df["detection_id"].tolist()
                        if "detection_id" in df.columns else [], key)

    db_mod.record_run(
        mode=meta.get("mode", mode), sources=meta.get("sources", []),
        urls=redacted_urls, count_new=counts["new"],
        count_total=counts["total"], status="ok",
        message=(f"{counts['new']} new / {counts['total']} stored "
                 f"({counts['excluded_outside_algeria']} outside-Algeria "
                 f"bbox rows excluded)"),
        started_at=started, finished_at=meta["fetched_at"].isoformat()
        if hasattr(meta.get("fetched_at"), "isoformat") else None,
        path=db_path)

    audit_path = None
    if audit and counts["with_features"]:
        rows = db_mod.load_detection_rows(
            limit=counts["with_features"], path=db_path)
        audit_path = save_audit_snapshot(pd.DataFrame(rows))

    return {"status": "ok", "mode": meta.get("mode", mode),
            "sources": meta.get("sources", []), "urls": redacted_urls,
            "new": counts["new"], "total": counts["total"],
            "audit": str(audit_path) if audit_path else None,
            "verification": verification_status()}


def _redact_stored_urls(db_path, detection_ids: list, key: str) -> None:
    """Ensure no raw key survives in stored source_url values."""
    if not detection_ids or not key:
        return
    import sqlite3

    with db_mod.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT detection_id, source_url FROM detections WHERE source_url LIKE ?",
            (f"%{key}%",)).fetchall()
        for det_id, url in rows:
            conn.execute("UPDATE detections SET source_url = ? WHERE detection_id = ?",
                         (firms_mod.redact_url(url, key), det_id))
        conn.commit()