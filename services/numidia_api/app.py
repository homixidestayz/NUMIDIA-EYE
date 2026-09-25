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
from numidia_intel import alerts as alerts_mod
from numidia_intel import assistant as assistant_mod
from numidia_intel import incidents as incidents_mod
from numidia_intel import reports as reports_mod

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
    # Harden against legacy rows missing derived fields: fall back to the
    # authoritative acquisition timestamp (never invent, only re-derive).
    acq_date = _clean(row.get("acq_date")) or acq.strftime("%Y-%m-%d")
    acq_time = acq_time or acq.strftime("%H%M")

    state = _row_state(acq_iso, ingest_fresh, now)
    payload = {
        "detection_id": _clean(row.get("detection_id")),
        "lat": _clean(row.get("lat")),
        "lon": _clean(row.get("lon")),
        "acq_datetime": acq,
        "acq_date": acq_date,
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
        "type": _clean(row.get("type")),
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


def _parse_iso(value: str | None, name: str) -> datetime | None:
    if value is None:
        return None
    try:
        ts = datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400,
                            detail=f"malformed {name} (expected ISO datetime)")
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def _parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    try:
        lon_min, lat_min, lon_max, lat_max = (float(p) for p in value.split(","))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="malformed bbox (expected lon_min,lat_min,lon_max,lat_max)")
    if not (lon_min <= lon_max and lat_min <= lat_max):
        raise HTTPException(status_code=400,
                            detail="malformed bbox (min must be <= max)")
    return lon_min, lat_min, lon_max, lat_max


def _apply_detection_filters(
    dets: list[Detection], *, state=None, since=None, until=None,
    min_confidence=None, max_confidence=None, min_frp=None,
    max_frp=None, bbox=None,
) -> list[Detection]:
    """Post-filters over the most-recent `limit` rows (documented semantic)."""
    since_ts = _parse_iso(since, "since")
    until_ts = _parse_iso(until, "until")
    box = _parse_bbox(bbox)
    out = []
    for d in dets:
        if state and d.state != state:
            continue
        if since_ts and d.acq_datetime < since_ts:
            continue
        if until_ts and d.acq_datetime > until_ts:
            continue
        if min_confidence is not None and (d.confidence is None
                                           or d.confidence < min_confidence):
            continue
        if max_confidence is not None and (d.confidence is None
                                           or d.confidence > max_confidence):
            continue
        if min_frp is not None and d.frp < min_frp:
            continue
        if max_frp is not None and d.frp > max_frp:
            continue
        if box:
            lon_min, lat_min, lon_max, lat_max = box
            if not (lon_min <= d.lon <= lon_max and lat_min <= d.lat <= lat_max):
                continue
        out.append(d)
    return out


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
        since: Optional[str] = Query(
            default=None, description="ISO datetime; keep acq_datetime >= since"),
        until: Optional[str] = Query(
            default=None, description="ISO datetime; keep acq_datetime <= until"),
        min_confidence: Optional[float] = Query(default=None, ge=0.0, le=1.0),
        max_confidence: Optional[float] = Query(default=None, ge=0.0, le=1.0),
        min_frp: Optional[float] = Query(default=None, ge=0.0),
        max_frp: Optional[float] = Query(default=None, ge=0.0),
        bbox: Optional[str] = Query(
            default=None,
            description="lon_min,lat_min,lon_max,lat_max (WGS84)"),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> list[Detection]:
        summary = _summary()
        now = datetime.now(timezone.utc)
        rows = db_mod.load_detection_rows(
            limit=limit, source=source, satellite=satellite,
            path=app.state.db_path)
        out = [_detection_from_row(r, summary["ingest_fresh"], now) for r in rows]
        out = _apply_detection_filters(
            out, state=state, since=since, until=until,
            min_confidence=min_confidence, max_confidence=max_confidence,
            min_frp=min_frp, max_frp=max_frp, bbox=bbox)
        return out

    @app.get("/detections/recent", response_model=list[Detection])
    def recent_detections(
        source: Optional[str] = None,
        satellite: Optional[str] = None,
        limit: int = Query(default=50, ge=1, le=1000),
    ) -> list[Detection]:
        """Most recent detections first (same item shape as /detections)."""
        summary = _summary()
        now = datetime.now(timezone.utc)
        rows = db_mod.load_detection_rows(
            limit=limit, source=source, satellite=satellite,
            path=app.state.db_path)
        return [_detection_from_row(r, summary["ingest_fresh"], now) for r in rows]

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
    def list_incidents(limit: int = Query(default=100, ge=1, le=1000)) -> dict:
        """Real incident clusters grouped from stored detections.

        Statuses are SINGLE_OBSERVATION / UNVERIFIED_CLUSTER - never
        "confirmed wildfire". Empty database -> honest EMPTY state.
        """
        items = incidents_mod.list_incidents(limit=limit, path=app.state.db_path)
        return {
            "status": "OK" if items else "EMPTY",
            "count": len(items),
            "incidents": [incidents_mod.validate_summary(s) for s in items],
            "methodology": incidents_mod.methodology(),
            "note": ("Incidents are deterministic spatiotemporal groupings of "
                     "real FIRMS detections, not confirmed wildfires. "
                     "Verification state is attached per incident."),
        }

    @app.get("/incidents/{incident_id}")
    def get_incident(incident_id: str) -> dict:
        detail = incidents_mod.get_incident(incident_id, path=app.state.db_path)
        if detail is None:
            raise HTTPException(status_code=404, detail="incident not found")
        return incidents_mod.validate_detail(detail)

    @app.get("/incidents/{incident_id}/report")
    def get_incident_report(incident_id: str) -> dict:
        report = reports_mod.build_report(incident_id, path=app.state.db_path)
        if report is None:
            raise HTTPException(status_code=404, detail="incident not found")
        return reports_mod.validate_report(report)

    @app.post("/alerts", status_code=201)
    def create_alert(payload: dict) -> dict:
        """Open a DRAFT prototype alert for a real incident."""
        incident_id = payload.get("incident_id") if isinstance(payload, dict) else None
        if not incident_id:
            raise HTTPException(status_code=400, detail="incident_id is required")
        if incidents_mod.get_incident(str(incident_id), path=app.state.db_path) is None:
            raise HTTPException(status_code=404, detail="incident not found")
        note = str(payload.get("note", ""))[:2000]
        alert = alerts_mod.create_alert(str(incident_id), note, path=app.state.db_path)
        return alerts_mod.validate_out(alert)

    @app.get("/alerts")
    def list_alerts() -> dict:
        items = [alerts_mod.validate_out(a)
                 for a in alerts_mod.list_alerts(path=app.state.db_path)]
        return {"count": len(items), "alerts": items,
                "prototype_note": alerts_mod.PROTOTYPE_NOTE}

    @app.post("/alerts/{alert_id}/transition")
    def transition_alert(alert_id: str, payload: dict) -> dict:
        to_state = payload.get("to_state") if isinstance(payload, dict) else None
        try:
            return alerts_mod.transition(str(alert_id), str(to_state),
                                         path=app.state.db_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/assistant/tools")
    def assistant_tools() -> dict:
        return assistant_mod.catalog()

    @app.post("/assistant/query")
    def assistant_query(payload: dict) -> dict:
        if not isinstance(payload, dict) or "tool" not in payload:
            raise HTTPException(status_code=400,
                                detail="body must be {tool: <name>, args: {...}}")
        try:
            return assistant_mod.dispatch(payload.get("tool"),
                                          payload.get("args") or {},
                                          db_path=app.state.db_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    return app


app = build_app()
