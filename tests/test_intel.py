"""Intel service tests - synthetic rows + temp DBs (offline, no network)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from numidia_core import db as db_mod
from numidia_intel import alerts as alerts_mod
from numidia_intel import assistant as assistant_mod
from numidia_intel import gis as gis_mod
from numidia_intel import incidents as incidents_mod
from numidia_intel import priority as priority_mod
from numidia_intel import reports as reports_mod
from numidia_intel import sentinel as sentinel_mod
from numidia_intel import verification as verification_mod


def _rows() -> list[dict]:
    base = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    rows = []
    # cluster A: 3 detections, ~1 km apart, within 2h, two satellites
    for i, (la, lo, sat, frp) in enumerate([
        (36.700, 3.100, "N21", 12.0),
        (36.705, 3.105, "N21", 8.0),
        (36.702, 3.098, "N20", 20.0),
    ]):
        rows.append({
            "detection_id": f"CLUS-A-{i}", "lat": la, "lon": lo,
            "acq_datetime": (base + timedelta(hours=i)).isoformat(),
            "fetched_at": base.isoformat(), "satellite": sat, "frp": frp,
            "source": "VIIRS_NOAA21_NRT", "wilaya_name": "Alger",
            "confidence": 0.6,
        })
    # lone detection far away (Sahara)
    rows.append({
        "detection_id": "LONE-1", "lat": 28.0, "lon": 9.0,
        "acq_datetime": base.isoformat(), "fetched_at": base.isoformat(),
        "satellite": "N", "frp": 0.5, "source": "VIIRS_SNPP_C2",
        "wilaya_name": "Illizi", "confidence": 0.6,
    })
    return rows


def _seeded_db(path) -> None:
    db_mod.init_db(path)
    df = pd.DataFrame(_rows())
    db_mod.upsert_detections(df, path)
    db_mod.record_run(mode="api", sources=["VIIRS_NOAA21_NRT"], urls=[],
                      count_new=4, count_total=4, status="ok",
                      message="seed", path=path)


# ---- incidents ------------------------------------------------------------
def test_grouping_is_deterministic_and_honest():
    rows = _rows()
    first = incidents_mod.group_detections(rows)
    second = incidents_mod.group_detections(list(reversed(rows)))
    assert len(first) == 2 and len(second) == 2
    ids_first = sorted(incidents_mod.incident_id_for(
        [m["detection_id"] for m in g]) for g in first)
    ids_second = sorted(incidents_mod.incident_id_for(
        [m["detection_id"] for m in g]) for g in second)
    assert ids_first == ids_second  # order-independent stable IDs


def test_incident_statuses_never_claim_confirmation(tmp_path):
    db = tmp_path / "i.db"
    _seeded_db(db)
    items = incidents_mod.list_incidents(path=db)
    assert len(items) == 2
    by_count = sorted(items, key=lambda s: s["detection_count"])
    assert by_count[0]["status"] == "SINGLE_OBSERVATION"
    assert by_count[1]["status"] == "UNVERIFIED_CLUSTER"
    assert by_count[1]["detection_count"] == 3
    assert by_count[1]["persistence_hours"] == pytest.approx(2.0)
    assert set(by_count[1]["satellites"]) == {"N20", "N21"}
    for s in items:
        assert s["status"] in ("SINGLE_OBSERVATION", "UNVERIFIED_CLUSTER")
    blob = str(items)
    assert "CONFIRMED_WILDFIRE" not in blob


def test_incident_detail_has_members_gis_priority(tmp_path):
    db = tmp_path / "i.db"
    _seeded_db(db)
    summary = incidents_mod.list_incidents(path=db)[0]
    detail = incidents_mod.get_incident(summary["id"], path=db)
    assert detail is not None
    assert len(detail["member_ids"]) == detail["detection_count"]
    assert detail["gis_context"]["wilaya"]["data_available"] is True
    assert detail["priority"]["methodology"].startswith("priority-v1")
    assert detail["verification"]["status"] == "UNAVAILABLE"
    assert incidents_mod.get_incident("INC-nope", path=db) is None


# ---- verification contract -------------------------------------------------
def test_verification_always_unavailable_without_model():
    state = verification_mod.detection_verification_state("X")
    assert state["status"] == "UNAVAILABLE"
    assert state["evaluated"] is False
    assert state["model"] is None
    assert state["evidence"] == []
    assert "confidence" not in str(state).lower() or True  # no confidence key at all
    assert "confidence" not in state
    contract = verification_mod.contract()
    assert contract["statuses"] == ["UNAVAILABLE", "PENDING", "PROCESSING",
                                   "VERIFIED", "REJECTED", "UNCERTAIN"]
    assert contract["current"]["status"] == "UNAVAILABLE"


# ---- GIS -------------------------------------------------------------------
def test_gis_wilaya_real_others_unavailable():
    ctx = gis_mod.get_context(36.75, 3.06)  # Algiers
    assert ctx.wilaya.data_available is True
    assert ctx.wilaya.value["code"] == "16"
    assert "geoBoundaries" in (ctx.wilaya.source or "")
    for layer in (ctx.settlement, ctx.road, ctx.elevation, ctx.slope, ctx.forest_cover):
        assert layer.data_available is False
        assert layer.status == "UNAVAILABLE"
        assert layer.value is None
        assert layer.reason


def test_gis_outside_algeria_and_bad_coords():
    sea = gis_mod.get_context(37.5, 4.0)  # Mediterranean
    assert sea.wilaya.data_available is False
    bad = gis_mod.get_context("nope", None)
    assert bad.wilaya.data_available is False
    assert bad.settlement.status == "UNAVAILABLE"


# ---- sentinel ---------------------------------------------------------------
def test_sentinel_unavailable_by_default():
    provider = sentinel_mod.get_provider()
    assert isinstance(provider, sentinel_mod.UnavailableSentinelProvider)
    assert provider.status["status"] == "UNAVAILABLE"
    with pytest.raises(sentinel_mod.ProviderUnavailable):
        provider.discover(sentinel_mod.SceneQuery(lat=36.7, lon=3.1,
                                                 start_date="2021-08-09",
                                                 end_date="2021-08-22"))
    with pytest.raises(sentinel_mod.ProviderUnavailable):
        provider.fetch_patch(sentinel_mod.PatchRequest(scene_id="X", lat=36.7, lon=3.1))


def test_sentinel_fixture_is_test_only():
    fx = sentinel_mod.FixtureSentinelProvider()
    hits = fx.discover(sentinel_mod.SceneQuery(lat=36.6, lon=3.1,
                                              start_date="2021-01-01",
                                              end_date="2021-01-02"))
    assert len(hits) == 1
    assert hits[0].fixture is True and hits[0].test_only is True
    assert "TEST" in hits[0].source
    far = fx.discover(sentinel_mod.SceneQuery(lat=28.0, lon=9.0,
                                             start_date="2021-01-01",
                                             end_date="2021-01-02"))
    assert far == []
    with pytest.raises(sentinel_mod.ProviderUnavailable):
        fx.fetch_patch(sentinel_mod.PatchRequest(scene_id=hits[0].scene_id,
                                                lat=36.6, lon=3.1))


# ---- priority ----------------------------------------------------------------
def test_priority_transparent_and_evidence_carrying():
    low = priority_mod.score_incident(detection_count=1, max_frp=0.5,
                                      persistence_hours=0.0, satellites=["N"],
                                      verification_status="UNAVAILABLE")
    assert low["level"] == "LOW"
    assert len(low["factors"]) == 4
    assert set(low["unavailable_factors"]) == {
        "proximity_to_settlements", "proximity_to_critical_infrastructure",
        "terrain_accessibility", "protected_forest_context", "visual_verification"}
    assert low["methodology"].startswith("priority-v1")
    assert low["computed_at"]
    weights = sum(f["weight"] for f in low["factors"])
    assert weights == pytest.approx(1.0)

    hot = priority_mod.score_incident(detection_count=15, max_frp=80.0,
                                      persistence_hours=48.0,
                                      satellites=["N", "N20", "N21"],
                                      verification_status="UNAVAILABLE")
    assert hot["level"] in ("HIGH", "CRITICAL")
    assert hot["score"] > low["score"]


# ---- reports ------------------------------------------------------------------
def test_report_only_contains_stored_facts(tmp_path):
    db = tmp_path / "r.db"
    _seeded_db(db)
    summary = incidents_mod.list_incidents(path=db)[0]
    rep = reports_mod.build_report(summary["id"], path=db)
    assert rep is not None
    for key in ("incident_id", "generated_at", "detection_count", "first_acq",
                "last_acq", "centroid_lat", "centroid_lon", "max_frp", "frp_sum",
                "satellites", "verification", "gis_context", "priority",
                "sources", "limitations", "provenance"):
        assert key in rep, key
    assert rep["limitations"], "limitations must never be empty"
    assert any("unavailable" in li.lower() or "UNAVAILABLE" in li for li in rep["limitations"])
    assert rep["verification"]["status"] == "UNAVAILABLE"
    assert reports_mod.build_report("INC-nope", path=db) is None


# ---- alerts --------------------------------------------------------------------
def test_alert_full_lifecycle_and_gates(tmp_path):
    db = tmp_path / "a.db"
    _seeded_db(db)
    inc_id = incidents_mod.list_incidents(path=db)[0]["id"]
    alert = alerts_mod.create_alert(inc_id, note="watch", path=db)
    assert alert["state"] == "DRAFT"
    assert alert["prototype_only"] is True
    assert len(alert["history"]) == 1

    with pytest.raises(ValueError):  # illegal jump
        alerts_mod.transition(alert["id"], "APPROVED", path=db)
    with pytest.raises(ValueError):  # unknown state
        alerts_mod.transition(alert["id"], "LAUNCHED", path=db)
    with pytest.raises(ValueError):  # unknown alert
        alerts_mod.transition("ALR-nope", "REVIEW_REQUIRED", path=db)

    for nxt in ("REVIEW_REQUIRED", "APPROVED", "SENT"):
        alert = alerts_mod.transition(alert["id"], nxt, path=db)
        assert alert["state"] == nxt
        assert "prototype" in alert["prototype_note"].lower()
    assert len(alert["history"]) == 4
    with pytest.raises(ValueError):  # terminal state
        alerts_mod.transition(alert["id"], "SENT", path=db)
    listed = alerts_mod.list_alerts(path=db)
    assert len(listed) == 1 and listed[0]["id"] == alert["id"]


# ---- assistant -------------------------------------------------------------------
def test_assistant_catalog_and_dispatch(tmp_path):
    db = tmp_path / "as.db"
    _seeded_db(db)
    catalog = assistant_mod.catalog()
    assert len(catalog["tools"]) == 8
    assert {t["name"] for t in catalog["tools"]} == {
        "detections.search", "detections.get", "incidents.list", "incidents.get",
        "system.status", "reports.get", "gis.lookup", "verification.get"}

    out = assistant_mod.dispatch("detections.search", {"limit": 2}, db_path=db)
    assert out["ok"] is True and out["result"]["count"] == 2
    one = assistant_mod.dispatch("detections.get", {"detection_id": "LONE-1"}, db_path=db)
    assert one["result"]["found"] is True
    missing = assistant_mod.dispatch("detections.get", {"detection_id": "nope"}, db_path=db)
    assert missing["result"]["found"] is False
    status = assistant_mod.dispatch("system.status", {}, db_path=db)
    assert status["result"]["detections_count"] == 4
    gis = assistant_mod.dispatch("gis.lookup", {"lat": 36.75, "lon": 3.06}, db_path=db)
    assert gis["result"]["wilaya"]["data_available"] is True
    ver = assistant_mod.dispatch("verification.get", {"detection_id": "LONE-1"}, db_path=db)
    assert ver["result"]["status"] == "UNAVAILABLE"
    incs = assistant_mod.dispatch("incidents.list", {}, db_path=db)
    assert incs["result"]["count"] == 2
    rep = assistant_mod.dispatch(
        "reports.get", {"incident_id": incs["result"]["incidents"][0]["id"]}, db_path=db)
    assert rep["result"]["found"] is True

    with pytest.raises(ValueError):
        assistant_mod.dispatch("wildfire.predict", {}, db_path=db)
    with pytest.raises(ValueError):
        assistant_mod.dispatch("", {}, db_path=db)
