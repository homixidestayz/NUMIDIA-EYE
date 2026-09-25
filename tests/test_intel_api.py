"""Intel API tests - new endpoints on temp DBs (offline, fixture-style seeds)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi.testclient import TestClient

os.environ["NUMIDIA_DISABLE_SCHEDULER"] = "1"

from numidia_api.app import build_app  # noqa: E402
from numidia_core import db as db_mod  # noqa: E402


def _seed(path, fresh_hours: float | None = 2.0) -> None:
    """Seed 3 fresh-ish detections + 1 old one; returns nothing (ids known)."""
    db_mod.init_db(path)
    now = datetime.now(timezone.utc)
    acq_new = now - timedelta(hours=fresh_hours or 0)
    acq_old = now - timedelta(days=10)
    rows = [
        {"detection_id": "T-1", "lat": 36.70, "lon": 3.10,
         "acq_datetime": acq_new.isoformat(), "fetched_at": now.isoformat(),
         "satellite": "N21", "frp": 15.0, "source": "VIIRS_NOAA21_NRT",
         "confidence": 0.6, "wilaya_name": "Alger", "daynight": "N"},
        {"detection_id": "T-2", "lat": 36.71, "lon": 3.11,
         "acq_datetime": (acq_new + timedelta(hours=1)).isoformat(),
         "fetched_at": now.isoformat(), "satellite": "N20", "frp": 4.0,
         "source": "VIIRS_NOAA20_NRT", "confidence": 0.6,
         "wilaya_name": "Alger", "daynight": "D"},
        {"detection_id": "T-3", "lat": 28.00, "lon": 9.00,
         "acq_datetime": acq_new.isoformat(), "fetched_at": now.isoformat(),
         "satellite": "N", "frp": 0.4, "source": "VIIRS_SNPP_C2",
         "confidence": 0.2, "wilaya_name": "Illizi", "daynight": "N"},
        {"detection_id": "T-OLD", "lat": 35.00, "lon": 5.00,
         "acq_datetime": acq_old.isoformat(),
         "fetched_at": (now - timedelta(days=9)).isoformat(),
         "satellite": "N21", "frp": 2.0, "source": "VIIRS_NOAA21_NRT",
         "confidence": 0.6, "wilaya_name": "M'Sila", "daynight": "N"},
    ]
    db_mod.upsert_detections(pd.DataFrame(rows), path)
    db_mod.record_run(mode="api", sources=["VIIRS_NOAA21_NRT"], urls=[],
                      count_new=4, count_total=4, status="ok",
                      message="seed", path=path)


def _client(tmp_path, name="api2.db"):
    db = tmp_path / name
    _seed(db)
    return TestClient(build_app(db))


def test_recent_endpoint(tmp_path):
    c = _client(tmp_path)
    body = c.get("/detections/recent").json()
    assert len(body) == 4
    acqs = [d["acq_datetime"] for d in body]
    assert acqs == sorted(acqs, reverse=True)
    assert len(c.get("/detections/recent", params={"limit": 2}).json()) == 2


def test_detection_filters(tmp_path):
    c = _client(tmp_path)
    assert len(c.get("/detections", params={"satellite": "N20"}).json()) == 1
    assert len(c.get("/detections", params={"min_frp": 10}).json()) == 1
    assert len(c.get("/detections", params={"max_frp": 1}).json()) == 1
    assert len(c.get("/detections", params={"min_confidence": 0.5}).json()) == 3
    assert len(c.get("/detections", params={"max_confidence": 0.3}).json()) == 1
    assert len(c.get("/detections", params={"bbox": "3.0,36.6,3.2,36.8"}).json()) == 2
    assert len(c.get("/detections", params={"bbox": "8.9,27.9,9.1,28.1"}).json()) == 1
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert len(c.get("/detections", params={"since": since}).json()) == 3
    until = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    assert len(c.get("/detections", params={"until": until}).json()) == 1
    assert c.get("/detections", params={"bbox": "nope"}).status_code == 400
    assert c.get("/detections", params={"bbox": "3.2,36.8,3.0,36.6"}).status_code == 400
    assert c.get("/detections", params={"since": "yesterday"}).status_code == 400


def test_incidents_endpoints(tmp_path):
    c = _client(tmp_path)
    body = c.get("/incidents").json()
    assert body["status"] == "OK"
    assert body["count"] == 3  # cluster(2) + lone + old = 3 groups
    assert "methodology" in body
    for inc in body["incidents"]:
        assert inc["status"] in ("SINGLE_OBSERVATION", "UNVERIFIED_CLUSTER")
    blob = str(body)
    assert "CONFIRMED_WILDFIRE" not in blob
    first = body["incidents"][0]
    detail = c.get(f"/incidents/{first['id']}").json()
    assert detail["member_ids"]
    assert detail["gis_context"]["wilaya"]["data_available"] is True
    assert detail["priority"]["methodology"].startswith("priority-v1")
    assert detail["verification"]["status"] == "UNAVAILABLE"
    assert c.get("/incidents/INC-nope").status_code == 404


def test_incidents_empty_db(tmp_path):
    db = tmp_path / "empty2.db"
    db_mod.init_db(db)
    c = TestClient(build_app(db))
    body = c.get("/incidents").json()
    assert body["status"] == "EMPTY"
    assert body["incidents"] == []


def test_report_endpoint(tmp_path):
    c = _client(tmp_path)
    inc_id = c.get("/incidents").json()["incidents"][0]["id"]
    rep = c.get(f"/incidents/{inc_id}/report").json()
    for key in ("incident_id", "detection_count", "max_frp", "frp_sum",
                "satellites", "verification", "gis_context", "priority",
                "sources", "limitations", "provenance"):
        assert key in rep, key
    assert rep["sources"], "sources must come from member rows"
    assert c.get("/incidents/INC-nope/report").status_code == 404


def test_alerts_lifecycle_api(tmp_path):
    c = _client(tmp_path)
    inc_id = c.get("/incidents").json()["incidents"][0]["id"]
    assert c.post("/alerts", json={}).status_code == 400
    assert c.post("/alerts", json={"incident_id": "INC-nope"}).status_code == 404
    created = c.post("/alerts", json={"incident_id": inc_id, "note": "watch"}).json()
    assert created["state"] == "DRAFT"
    assert created["prototype_only"] is True
    assert c.post(f"/alerts/{created['id']}/transition",
                  json={"to_state": "APPROVED"}).status_code == 400
    for nxt in ("REVIEW_REQUIRED", "APPROVED", "SENT"):
        moved = c.post(f"/alerts/{created['id']}/transition",
                       json={"to_state": nxt}).json()
        assert moved["state"] == nxt
    listed = c.get("/alerts").json()
    assert listed["count"] == 1
    assert "prototype" in listed["prototype_note"].lower()


def test_assistant_endpoints(tmp_path):
    c = _client(tmp_path)
    tools = c.get("/assistant/tools").json()["tools"]
    assert len(tools) == 8
    out = c.post("/assistant/query",
                 json={"tool": "system.status", "args": {}}).json()
    assert out["ok"] is True
    assert out["result"]["detections_count"] == 4
    gis = c.post("/assistant/query",
                 json={"tool": "gis.lookup",
                       "args": {"lat": 36.75, "lon": 3.06}}).json()
    assert gis["result"]["wilaya"]["value"]["code"] == "16"
    assert c.post("/assistant/query",
                  json={"tool": "nope", "args": {}}).status_code == 400
    assert c.post("/assistant/query", json={"args": {}}).status_code == 400


def test_assistant_malformed_limit_returns_400_not_500(tmp_path):
    # C1 regression: null / non-numeric limits must be controlled 400s.
    c = _client(tmp_path)
    for tool in ("detections.search", "incidents.list"):
        for bad in (None, "abc", [1], {"n": 1}):
            r = c.post("/assistant/query",
                       json={"tool": tool, "args": {"limit": bad}})
            assert r.status_code == 400, (tool, bad, r.status_code)
    # valid numeric limits (incl. numeric strings) keep working
    for good, expect in ((5, 4), ("3", 3), (500, 4)):
        r = c.post("/assistant/query",
                   json={"tool": "detections.search", "args": {"limit": good}})
        assert r.status_code == 200
        assert r.json()["result"]["count"] == expect


def test_ai_gate_still_503(tmp_path):
    c = _client(tmp_path)
    r = c.get("/detections/T-1/ai")
    assert r.status_code == 503
    assert r.json()["status"] == "AI_UNAVAILABLE"
    assert r.json()["probability"] is None


def test_existing_shapes_unchanged(tmp_path):
    c = _client(tmp_path)
    assert c.get("/health").json()["status"] == "ok"
    status = c.get("/system/status").json()
    assert status["ai"] == "UNAVAILABLE"
    assert status["data_state"] in ("LIVE", "HISTORICAL")
    det = c.get("/detections/T-1").json()
    assert det["detection_id"] == "T-1"
    assert c.get("/detections/nope").status_code == 404
