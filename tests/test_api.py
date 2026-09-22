"""API tests - temp databases seeded from the test fixture (never production).

The scheduler is disabled here (NUMIDIA_DISABLE_SCHEDULER=1); each test builds
its own app instance against its own database via the build_app factory.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

os.environ["NUMIDIA_DISABLE_SCHEDULER"] = "1"
os.environ["FIRMS_MAP_KEY"] = "TEST-SECRET-KEY-12345"

from numidia_api.app import build_app  # noqa: E402
from numidia_core import db as db_mod  # noqa: E402
from numidia_core import pipeline as pipeline_mod  # noqa: E402
from numidia_core.firms import normalize_raw, redact_url  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "firms_noaa21_sample_1d.csv"


def _seeded_db(path) -> None:
    """Seed via the REAL production path (validate→features→clip→upsert)."""
    db_mod.init_db(path)
    raw = pd.read_csv(FIXTURE)
    df = normalize_raw(raw, source="VIIRS_NOAA21_NRT",
                       source_url="https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
                                  "TEST-SECRET-KEY-12345/VIIRS_NOAA21_NRT/1/x",
                       fetched_at=datetime(2026, 9, 17, 12, tzinfo=timezone.utc))
    # Pipeline redacts before storage; mirror that here.
    df["source_url"] = df["source_url"].map(lambda u: redact_url(u, "TEST-SECRET-KEY-12345"))
    counts = pipeline_mod.process_frame(df, path)
    assert (counts["new"], counts["excluded_outside_algeria"]) == (186, 64)
    db_mod.record_run(mode="api", sources=["VIIRS_NOAA21_NRT"],
                      urls=["https://firms.../{FIRMS_MAP_KEY}/..."],
                      count_new=counts["new"], count_total=counts["total"],
                      status="ok", message="seed", path=path)


@pytest.fixture()
def client(tmp_path):
    db = tmp_path / "api.db"
    _seeded_db(db)
    with TestClient(build_app(db)) as c:
        yield c


@pytest.fixture()
def empty_client(tmp_path):
    db = tmp_path / "empty.db"
    db_mod.init_db(db)
    with TestClient(build_app(db)) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_detections_real_rows_no_ai_fields(client):
    r = client.get("/detections")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 100  # default limit
    det = body[0]
    assert "probability" not in det
    assert "verified" not in det
    assert det["frp"] is not None
    assert det["wilaya_code"] is not None


def test_detections_filters(client):
    r = client.get("/detections", params={"limit": 5})
    assert len(r.json()) == 5
    r = client.get("/detections", params={"state": "LIVE"})
    assert r.status_code == 200  # fixture data is old: expect empty, honestly
    assert r.json() == []
    r = client.get("/detections", params={"source": "VIIRS_NOAA21_NRT",
                                          "limit": 3})
    assert len(r.json()) == 3


def test_detection_detail_and_404(client):
    some_id = client.get("/detections", params={"limit": 1}).json()[0]["detection_id"]
    r = client.get(f"/detections/{some_id}")
    assert r.status_code == 200
    assert r.json()["detection_id"] == some_id
    assert client.get("/detections/nope").status_code == 404


def test_ai_verifier_honestly_unavailable(client):
    some_id = client.get("/detections", params={"limit": 1}).json()[0]["detection_id"]
    r = client.get(f"/detections/{some_id}/ai")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "AI_UNAVAILABLE"
    assert body["probability"] is None
    assert body["verified"] is None


def test_system_status_honest(client):
    body = client.get("/system/status").json()
    assert body["ai"] == "UNAVAILABLE"
    assert body["db"] == "OK"
    assert body["detections_count"] == 186
    assert body["data_state"] == "HISTORICAL"  # fresh run, aging fixture data
    assert body["firms"] == "CONNECTED"


def test_incidents_honest_empty(client):
    body = client.get("/incidents").json()
    assert body["incidents"] == []
    assert body["status"] == "NOT_IMPLEMENTED"


def test_system_data_provenance(client):
    body = client.get("/system/data").json()
    assert body["detections"] == 186
    assert body["sources"] == ["VIIRS_NOAA21_NRT"]
    assert body["recent_runs"][0]["status"] == "ok"


def test_key_never_leaks_to_clients(client):
    for path in ["/system/status", "/system/data", "/detections?limit=5",
                 "/incidents"]:
        r = client.get(path)
        assert "TEST-SECRET-KEY-12345" not in r.text, f"key leaked via {path}"
    some_id = client.get("/detections", params={"limit": 1}).json()[0]["detection_id"]
    for path in [f"/detections/{some_id}", f"/detections/{some_id}/ai"]:
        assert "TEST-SECRET-KEY-12345" not in client.get(path).text


def test_empty_db_is_unavailable(empty_client):
    assert empty_client.get("/detections").json() == []
    body = empty_client.get("/system/status").json()
    assert body["data_state"] == "UNAVAILABLE"
    assert body["detections_count"] == 0
    assert empty_client.get("/detections/nope").status_code == 404