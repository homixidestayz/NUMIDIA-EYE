"""API tests - offline, using the committed real FIRMS sample (no network)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from numidia_api.app import app, DETECTIONS

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_detections_real_data():
    assert len(DETECTIONS) > 0, "sample must load"
    r = client.get("/detections")
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 1
    det = body[0]
    # no AI/hardcoded fields may exist on a real detection
    assert "probability" not in det
    assert "verified" not in det
    assert det["state"] in {"LIVE", "HISTORICAL"}
    assert det["frp"] is not None


def test_detections_filters():
    ids = {d["detection_id"] for d in client.get("/detections").json()}
    some_id = next(iter(ids))
    r = client.get("/detections", params={"state": "HISTORICAL"})
    assert r.status_code == 200
    assert all(d["state"] == "HISTORICAL" for d in r.json())
    r = client.get("/detections", params={"limit": 5})
    assert len(r.json()) == 5
    r = client.get("/detections", params={"state": "UNAVAILABLE"})
    assert r.json() == []


def test_detection_detail_and_404():
    some_id = DETECTIONS[0].detection_id
    r = client.get(f"/detections/{some_id}")
    assert r.status_code == 200
    assert r.json()["detection_id"] == some_id
    assert client.get("/detections/nope").status_code == 404


def test_ai_verifier_honestly_unavailable():
    some_id = DETECTIONS[0].detection_id
    r = client.get(f"/detections/{some_id}/ai")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "AI_UNAVAILABLE"
    assert body["probability"] is None
    assert body["verified"] is None


def test_system_status_honest():
    r = client.get("/system/status")
    assert r.status_code == 200
    body = r.json()
    assert body["ai"] == "UNAVAILABLE"
    assert body["db"] == "OK"
    assert body["detections_count"] == len(DETECTIONS)
    assert body["data_state"] in {"LIVE", "HISTORICAL", "UNAVAILABLE"}
    assert body["firms"] in {"CONNECTED", "UNAVAILABLE"}


def test_incidents_honest_empty():
    r = client.get("/incidents")
    assert r.status_code == 200
    body = r.json()
    assert body["incidents"] == []
    assert body["status"] == "NOT_IMPLEMENTED"


def test_system_data_provenance():
    r = client.get("/system/data")
    assert r.status_code == 200
    body = r.json()
    assert body["detections"] == len(DETECTIONS)
    assert "N21" in body["satellites"]