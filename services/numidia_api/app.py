"""NUMIDIA EYE API - production boundary. Serves ONLY the application database.

- Source of truth: NASA FIRMS NRT API -> scheduled ingestion -> SQLite DB.
- Freshness is enforced: stale pipelines serve STALE, never LIVE.
- The FIRMS key lives server-side (env) and is redacted before storage.
- AI endpoints return 503 AI_UNAVAILABLE until a real evaluated verifier
  model exists. No fake probabilities, no LLM-as-verifier, ever.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query

from numidia_core import db as db_mod
from numidia_core import pipeline as pipeline_mod
from numidia_core.config import (
    DB_PATH, DISABLE_SCHEDULER, FIRMS_MAP_KEY, INGEST_INTERVAL_MIN,
    LIVE_WINDOW_HOURS,
)
from numidia_core.schemas import AiResult, Detection, SystemStatus

ALGERIA_BBOX = {"lon_min": -9.0, "lat_min": 18.0, "lon_max": 12.0, "lat_max": 38.0}


def _clean(value):
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, str) and value.strip().lower() in ("nan", "nat", "none", ""):
        return None
    return value


def _row_state(acq_iso: str | None, ingest_fresh: bool,
               now: datetime) -> str:
    """LIVE requires BOTH a fresh acquisition AND a fresh pipeline."""
    if not ingest_fresh or not acq_iso:
        return "HISTORICAL"
    try:
        acq = datetime.fromisoformat(acq_iso)
        if acq.tzinfo is None:
            acq = acq.replace(tzinfo=timezone.utc)
    except ValueError:
        return "HISTORICAL"
    if acq > now + timedelta(minutes=5):
        return "HISTORICAL"  # future-dated acquisition: do not trust as live
    if (now - acq) <= timedelta(hours=LIVE_WINDOW_HOURS):
        return "LIVE"
    return "HISTORICAL"


def _detection_from_row(row: dict, ingest_fresh: bool, now: datetime) -> Detection:
    acq_iso = _clean(row.get("acq_datetime"))
    try:
        acq = datetime.fromisoformat(acq_iso) if acq_iso else now
        if acq.tzinfo is None:
            acq = acq.replace(tzinfo=timezone.utc)
    except ValueError:
        acq = now
    fetched_raw = _clean(row.get("fetched_at"))
    try:
        fetched = datetime.fromisoformat(fetched_raw) if fetched_raw else now
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
    except ValueError:
        fetched = now

    acq_time = _clean(row.get("acq_time"))
    if acq_time is not None:
        try:
            acq_time = str(int(acq_time)).zfill(4)
        except (ValueError, TypeError):
            pass

    state = _row_state(acq_iso, ingest_fresh, now)
    payload = {
        "detection_id": _clean(row.get("detection_id")),
        "lat": _clean(row.get("lat")),
        "lon": _clean(row.get("lon")),
        "acq_datetime": acq,
        "acq_date": _clean(row.get("acq_date")),
        "acq_time": acq_time,
        "satellite": _clean(row.get("satellite")),
        "instrument": _clean(row.get("instrument")),
        "confidence": _clean(row.get("confidence")),
        "confidence_raw": _clean(row.get("confidence_raw")),
        "bright_ti4": _clean(row.get("bright_ti4")),
        "bright_ti5": _clean(row.get("bright_ti5")),
        "scan": _clean(row.get("scan")),
        "track": _clean(row.get("track")),
        "frp": _clean(row.get("frp")),
        "daynight": _clean(row.get("daynight")),
        "version": _clean(row.get("version")),
        "source": _clean(row.get("source")) or "FIRMS",
        "source_url": _clean(row.get("source_url")),
        "fetched_at": fetched,
        "wilaya_code": _clean(row.get("wilaya_code")),
        "wilaya_name": _clean(row.get("wilaya_name")),
        "state": state,
    }
    for key, val in row.items():
        if key.startswith("f_"):
            payload[key] = _clean(val)
    return Detection(**payload)


async def _scheduler_loop(db_path: Path, stop: asyncio.Event) -> None:
    """Periodic production ingestion. Overlaps are skipped, never stacked."""
    running = False

    def _run_once() -> None:
        nonlocal running
        if running:
            return
        running = True
        try:
            summary = pipeline_mod.run_ingest(db_path=db_path)
            print(f"[ingest] {summary['status']} "
                  f"{summary.get('new', 0)} new / {summary.get('total', 0)} stored "
                  f"(mode={summary.get('mode')})")
        finally:
            running = False

    await asyncio.to_thread(_run_once)
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=INGEST_INTERVAL_MIN * 60)
        except asyncio.TimeoutError:
            pass
        if not stop.is_set():
            await asyncio.to_thread(_run_once)


def build_app(db_path: Path | str | None = None) -> FastAPI:
    resolved = db_mod.resolve_db_path(db_path if db_path is not None else DB_PATH)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db_mod.init_db(resolved)
        stop = asyncio.Event()
        task = None
        if not DISABLE_SCHEDULER:
            task = asyncio.create_task(_scheduler_loop(resolved, stop))
            print(f"[api] scheduler on: ingest every {INGEST_INTERVAL_MIN} min -> {resolved}")
        else:
            print("[api] scheduler disabled (NUMIDIA_DISABLE_SCHEDULER)")
        yield
        stop.set()
        if task:
            task.cancel()

    app = FastAPI(
        title="NUMIDIA EYE API",
        version="0.1.0",
        description="Wildfire intelligence for Algeria - real data only. "
                    "Independent prototype, non-official.",
        lifespan=lifespan,
    )
    app.state.db_path = resolved

    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # prototype dev boundary; tighten before production use
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _summary() -> dict:
        return db_mod.data_state_summary(path=app.state.db_path)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok",
                "time": datetime.now(timezone.utc).isoformat(),
                "service": "numidia_api"}

    @app.get("/system/status", response_model=SystemStatus)
    def system_status() -> SystemStatus:
        summary = _summary()
        runs = db_mod.latest_runs(limit=1, path=app.state.db_path)
        last_run = runs[0] if runs else None
        has_key = bool(FIRMS_MAP_KEY)

        if last_run is None:
            firms = "STARTING" if has_key else "NOT_CONFIGURED"
        elif summary["ingest_fresh"]:
            firms = "CONNECTED"
        elif last_run["status"] in ("error", "skipped"):
            firms = "DEGRADED"
        else:
            firms = "STALE"

        verify = pipeline_mod.verification_status()
        ai_state = "READY" if verify["status"] == "READY" else "UNAVAILABLE"
        last_fetch = None
        if summary["last_ok_at"]:
            last_fetch = datetime.fromisoformat(summary["last_ok_at"])
        last_ok = db_mod.last_successful_run(path=app.state.db_path)
        ok_mode = (last_ok or {}).get("mode", "?")
        ok_sources = ", ".join((last_ok or {}).get("sources", []) or ["?"])
        via = (f"via FIRMS NRT API ({ok_sources})" if ok_mode == "api"
               else f"via FIRMS public archive ({ok_sources})")

        if summary["data_state"] == "UNAVAILABLE":
            message = ("No detections in the database yet. The scheduler pulls "
                       "the NASA FIRMS NRT API periodically; until the first "
                       "successful run this API honestly reports UNAVAILABLE.")
        elif summary["data_state"] == "STALE":
            message = (f"Ingestion is stale (last success {summary['last_ok_at']}); "
                       f"serving last available data as HISTORICAL - never as live. "
                       f"{summary['detections_count']} stored detections.")
        elif summary["data_state"] == "LIVE":
            message = (f"Live: {summary['live_count']} freshly acquired VIIRS "
                       f"detections {via}; pipeline healthy.")
        else:
            message = (f"Pipeline healthy but no freshly acquired detections "
                       f"(quiet period or aging data); {summary['detections_count']} "
                       f"stored detections served as HISTORICAL.")

        message += (" AI verifier UNAVAILABLE until a labeled, evaluated model "
                    "exists. Alerts are PROTOTYPE ONLY - not Civil Protection.")

        return SystemStatus(
            firms=firms,
            firms_last_fetch=last_fetch,
            ai=ai_state,
            model=verify["model"],
            db="OK",
            data_state=summary["data_state"],
            detections_count=summary["detections_count"],
            message=message,
        )

    @app.get("/system/data")
    def system_data() -> dict:
        summary = _summary()
        return {
            "data_state": summary["data_state"],
            "ingest_fresh": summary["ingest_fresh"],
            "detections": summary["detections_count"],
            "live": summary["live_count"],
            "sources": summary["sources"],
            "satellites": summary["satellites"],
            "max_acq": summary["max_acq"],
            "last_ok_at": summary["last_ok_at"],
            "bbox": ALGERIA_BBOX,
            "recent_runs": db_mod.latest_runs(limit=5, path=app.state.db_path),
            "verification": pipeline_mod.verification_status(),
            "live_window_hours": LIVE_WINDOW_HOURS,
            "note": ("Production source of truth: NASA FIRMS NRT API -> app "
                     "database. URLs are key-redacted. No sample/fixture data "
                     "is ever served here."),
        }

    @app.get("/detections", response_model=list[Detection])
    def list_detections(
        source: Optional[str] = None,
        satellite: Optional[str] = None,
        state: Optional[str] = Query(
            default=None,
            pattern="^(LIVE|HISTORICAL|STALE|SAMPLE|DEMO|UNAVAILABLE)$"),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> list[Detection]:
        summary = _summary()
        now = datetime.now(timezone.utc)
        rows = db_mod.load_detection_rows(
            limit=limit, source=source, satellite=satellite,
            path=app.state.db_path)
        out = [_detection_from_row(r, summary["ingest_fresh"], now) for r in rows]
        if state:
            out = [d for d in out if d.state == state]
        return out

    @app.get("/detections/{detection_id}", response_model=Detection)
    def get_detection(detection_id: str) -> Detection:
        summary = _summary()
        row = db_mod.get_detection_row(detection_id, path=app.state.db_path)
        if row is None:
            raise HTTPException(status_code=404, detail="detection not found")
        return _detection_from_row(row, summary["ingest_fresh"],
                                   datetime.now(timezone.utc))

    @app.get("/detections/{detection_id}/ai", response_model=AiResult,
             status_code=503)
    def ai_verify(detection_id: str) -> AiResult:
        """AI verification: explicit 503 until a real evaluated model exists."""
        if db_mod.get_detection_row(detection_id,
                                    path=app.state.db_path) is None:
            raise HTTPException(status_code=404, detail="detection not found")
        verify = pipeline_mod.verification_status()
        return AiResult(status=verify["status"], detection_id=detection_id,
                        message=verify["message"])

    @app.get("/incidents")
    def list_incidents() -> dict:
        return {
            "status": "NOT_IMPLEMENTED",
            "incidents": [],
            "message": ("Incident clustering needs the AI-verified detections "
                        "pipeline; not available until the verifier model is "
                        "trained on labeled data. No invented incidents."),
        }

    return app


app = build_app()
