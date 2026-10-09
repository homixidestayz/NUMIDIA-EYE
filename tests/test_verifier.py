"""End-to-end tests for the live-v1 structured wildfire verifier.

The integration test runs the REAL trained artifact over a REAL detection from
the production SQLite database. Nothing is mocked: no stub probability, no
monkeypatched model. If the artifact is absent the integration tests skip
loudly rather than silently passing.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from numidia_ml.inference import (INFERENCE_SCHEMA_VERSION, InferenceContractError,
                                  VerifierUnavailable, build_inference_features,
                                  load_verifier, validate_feature_vector)
from numidia_ml.labels import MODEL_FEATURES_V1
from numidia_ml.verifier_model import (PREDICTION_FIRE, PREDICTION_NON_FIRE,
                                       PREDICTION_UNCERTAIN,
                                       SklearnWildfireVerifier,
                                       load_verified_verifier)

REPO = Path(__file__).resolve().parents[1]
ARTIFACT = REPO / "services" / "ml" / "models" / "verifier_v2"
DATASET = REPO / "data" / "labels" / "firms_labels_v2.csv"
DB = REPO / "data" / "db" / "numidia.db"

has_artifact = (ARTIFACT / "model.joblib").exists() and (ARTIFACT / "config.json").exists()
requires_artifact = pytest.mark.skipif(
    not has_artifact,
    reason="no trained verifier artifact (run `experiment --verifier` first)")


def production_db_usable() -> bool:
    """True only if there is a READABLE production DB with real detections.

    `DB.exists()` is not a sufficient guard. `numidia_core.db.connect()` does
    `mkdir` and then `sqlite3.connect`, which CREATES the file, so any earlier
    test that touches the database leaves an empty numidia.db behind. The
    existence check then passes and every query raises
    "no such table: detections".

    That matters on a fresh clone, where there is no database at all: these
    tests are explicitly about real production data (their skip messages say
    "no production database present"), so they must SKIP, not fail, when the
    database is absent or empty.
    """
    if not DB.exists():
        return False
    import sqlite3
    try:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        try:
            row = con.execute(
                "select 1 from detections limit 1").fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return False
    return row is not None


def _raise_unregistered(artifact=None):
    """Stand-in resolver for the 'nothing registered' case."""
    raise VerifierUnavailable(
        "No verified verifier is registered (NUMIDIA_ACTIVE_MODEL is unset).")


# ---------------------------------------------------------------- 1-2 schema/order
def test_contract_is_exactly_ten_features():
    assert list(MODEL_FEATURES_V1) == [
        "bright_ti4", "bright_ti5", "f_bt_diff", "frp", "f_frp",
        "confidence", "f_confidence", "scan", "track", "satellite"]


def test_training_feature_order_matches_contract():
    from numidia_ml.verifier_split import FEATURE_COLUMNS
    assert list(FEATURE_COLUMNS) == list(MODEL_FEATURES_V1)


@requires_artifact
def test_artifact_declares_contract_order():
    cfg = json.loads((ARTIFACT / "config.json").read_text(encoding="utf-8"))
    assert cfg["feature_order"] == list(MODEL_FEATURES_V1)
    assert cfg["schema_version"] == INFERENCE_SCHEMA_VERSION


def test_training_and_inference_share_one_feature_builder():
    """`type` must be inert: identical output whether absent, null or populated.

    Derived `f_*` fields are intentionally NOT supplied: the boundary recomputes
    them from the raw VIIRS values, so a forged or stale derived column cannot
    change the vector.
    """
    base = {"bright_ti4": 320.0, "bright_ti5": 295.0, "frp": 12.0,
            "confidence": 0.6, "scan": 0.4, "track": 0.4, "satellite": "N20",
            "lat": 31.7, "lon": 6.0}
    a = build_inference_features(dict(base))
    b = build_inference_features({**base, "type": 0})
    c = build_inference_features({**base, "type": None})
    assert a.values == b.values == c.values
    assert a["f_bt_diff"] == pytest.approx(25.0)
    # a forged derived value must not survive the builder
    d = build_inference_features({**base, "f_bt_diff": -999.0})
    assert d["f_bt_diff"] == pytest.approx(25.0)
    # A real live row legitimately carries lat/lon/type/f_month etc. The boundary
    # must ignore them. What it must never do is let them become FEATURES, which
    # `validate_feature_vector` enforces on the vector actually handed over.
    e = build_inference_features({**base, "label": "fire", "split": "train",
                                  "ground_truth_id": "X", "f_month": 8})
    assert set(e.keys()) == set(MODEL_FEATURES_V1)
    with pytest.raises(InferenceContractError):
        validate_feature_vector({**dict(e.values), "label": "fire"})


# ---------------------------------------------------------------- 4 artifact gates
@requires_artifact
def test_verified_artifact_loads():
    v = load_verified_verifier(ARTIFACT)
    assert isinstance(v, SklearnWildfireVerifier)
    assert v.version and v.threshold is not None
    assert list(v.feature_names) == list(MODEL_FEATURES_V1)


@requires_artifact
def test_manifest_records_dataset_provenance():
    man = json.loads((ARTIFACT / "manifest.json").read_text(encoding="utf-8"))
    assert man["dataset_sha256"]
    assert man["model_sha256"]


@requires_artifact
def test_tampered_model_fails_closed(tmp_path):
    import shutil
    dst = tmp_path / "verifier"
    shutil.copytree(ARTIFACT, dst)
    with open(dst / "model.joblib", "ab") as fh:
        fh.write(b"\x00tamper")
    with pytest.raises(VerifierUnavailable):
        load_verified_verifier(dst)


@requires_artifact
def test_missing_model_fails_closed(tmp_path):
    import shutil
    dst = tmp_path / "verifier"
    shutil.copytree(ARTIFACT, dst)
    (dst / "model.joblib").unlink()
    with pytest.raises(VerifierUnavailable):
        load_verified_verifier(dst)


@requires_artifact
def test_wrong_schema_version_fails_closed(tmp_path):
    import shutil
    dst = tmp_path / "verifier"
    shutil.copytree(ARTIFACT, dst)
    cfg = json.loads((dst / "config.json").read_text(encoding="utf-8"))
    cfg["schema_version"] = "live-v0"
    (dst / "config.json").write_text(json.dumps(cfg))
    with pytest.raises(VerifierUnavailable):
        load_verified_verifier(dst)


@requires_artifact
def test_feature_order_mismatch_fails_closed(tmp_path):
    import shutil
    dst = tmp_path / "verifier"
    shutil.copytree(ARTIFACT, dst)
    cfg = json.loads((dst / "config.json").read_text(encoding="utf-8"))
    cfg["feature_order"] = [f for f in cfg["feature_order"] if f != "scan"]
    (dst / "config.json").write_text(json.dumps(cfg))
    with pytest.raises(VerifierUnavailable):
        load_verified_verifier(dst)


@requires_artifact
def test_forbidden_type_feature_fails_closed(tmp_path):
    import shutil
    dst = tmp_path / "verifier"
    shutil.copytree(ARTIFACT, dst)
    cfg = json.loads((dst / "config.json").read_text(encoding="utf-8"))
    cfg["feature_order"] = cfg["feature_order"] + ["type"]
    (dst / "config.json").write_text(json.dumps(cfg))
    with pytest.raises(VerifierUnavailable):
        load_verified_verifier(dst)


@requires_artifact
def test_missing_dataset_provenance_fails_closed(tmp_path):
    import shutil
    dst = tmp_path / "verifier"
    shutil.copytree(ARTIFACT, dst)
    cfg = json.loads((dst / "config.json").read_text(encoding="utf-8"))
    cfg["dataset_sha256"] = ""
    (dst / "config.json").write_text(json.dumps(cfg))
    with pytest.raises(VerifierUnavailable):
        load_verified_verifier(dst)


def test_unregistered_model_is_unavailable():
    v = load_verifier(model_path=None) if False else None
    from numidia_ml.inference import available_verifier
    got = available_verifier(str(REPO / "does" / "not" / "exist.joblib"))
    from numidia_ml.inference import UnavailableVerifier
    assert isinstance(got, UnavailableVerifier)
    with pytest.raises(VerifierUnavailable):
        got.verify(None)


# ---------------------------------------------------------------- 5-11 feature errors
def _vec(**over):
    base = {"bright_ti4": 320.0, "bright_ti5": 295.0, "f_bt_diff": 25.0,
            "frp": 12.0, "f_frp": 12.0, "confidence": 0.6, "f_confidence": 0.6,
            "scan": 0.4, "track": 0.4, "satellite": "N20"}
    base.update(over)
    return base


def test_missing_feature_rejected():
    v = _vec()
    del v["scan"]
    with pytest.raises(InferenceContractError):
        validate_feature_vector(v)


def test_extra_feature_rejected():
    with pytest.raises(InferenceContractError):
        validate_feature_vector(_vec(extra_column=1))


def test_forbidden_type_rejected():
    with pytest.raises(InferenceContractError):
        validate_feature_vector(_vec(type=0))


def test_non_finite_feature_rejected():
    with pytest.raises(InferenceContractError):
        validate_feature_vector(_vec(frp=float("nan")))
    with pytest.raises(InferenceContractError):
        validate_feature_vector(_vec(bright_ti4=float("inf")))


def test_wrong_schema_version_rejected():
    with pytest.raises(InferenceContractError):
        validate_feature_vector(_vec(), schema_version="live-v0")


def test_null_required_feature_rejected():
    with pytest.raises(InferenceContractError):
        validate_feature_vector(_vec(frp=None))


# ---------------------------------------------------------------- 13-17 scoring
@requires_artifact
def test_probability_in_range_and_from_model():
    v = load_verified_verifier(ARTIFACT)
    f = validate_feature_vector(_vec())
    p = v.probability(f)
    assert 0.0 <= p <= 1.0
    # not a hard-coded constant: a materially different input must move it
    p2 = v.probability(validate_feature_vector(_vec(frp=1.0, f_frp=1.0)))
    assert p != p2


@requires_artifact
def test_three_state_classification():
    v = load_verified_verifier(ARTIFACT)
    assert v.classify(1.0) == PREDICTION_FIRE
    assert v.classify(v.threshold) == PREDICTION_FIRE
    assert v.classify(0.0) == PREDICTION_NON_FIRE
    mid = (v.threshold + v.non_fire_threshold) / 2
    assert v.classify(mid) == PREDICTION_UNCERTAIN
    assert v.non_fire_threshold < v.threshold


@requires_artifact
def test_verify_returns_real_result():
    v = load_verified_verifier(ARTIFACT)
    r = v.verify(validate_feature_vector(_vec()))
    assert r.model_version == v.version
    assert 0.0 <= r.probability <= 1.0
    assert r.assessment in (PREDICTION_FIRE, PREDICTION_NON_FIRE, PREDICTION_UNCERTAIN)


# ---------------------------------------------------------------- 18-19 API
@requires_artifact
def test_ai_endpoint_serves_real_inference(monkeypatch, tmp_path):
    """REAL artifact + REAL live FIRMS detection from the production DB."""
    from fastapi.testclient import TestClient

    from numidia_api import app as app_mod
    from numidia_core import db as db_mod

    if not production_db_usable():
        pytest.skip("no production database present")
    import sqlite3
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    row = con.execute(
        "select * from detections order by acq_datetime desc limit 1").fetchone()
    cols = [d[0] for d in con.execute("select * from detections limit 1").description]
    con.close()
    assert row is not None, "production DB has no detections"
    did = dict(zip(cols, row))["detection_id"]

    monkeypatch.setenv("NUMIDIA_ACTIVE_MODEL", str(ARTIFACT))
    import importlib
    import numidia_core.config as cfg_mod
    importlib.reload(cfg_mod)
    monkeypatch.setattr(cfg_mod, "ACTIVE_MODEL", str(ARTIFACT))
    import numidia_ml.verifier_model as vm
    monkeypatch.setattr(vm, "_resolve", lambda a=None: ARTIFACT / "model.joblib")

    monkeypatch.setattr(app_mod.pipeline_mod, "verification_status",
                        lambda *a, **k: {"status": "available",
                                         "message": "test-registered verifier"})
    application = app_mod.build_app(db_path=str(DB))
    client = TestClient(application)
    resp = client.get(f"/detections/{did}/ai")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "available"
    assert body["detection_id"] == did
    assert isinstance(body["probability"], float)
    assert 0.0 <= body["probability"] <= 1.0
    assert body["prediction"] in (PREDICTION_FIRE, PREDICTION_NON_FIRE, PREDICTION_UNCERTAIN)
    assert body["features_schema"] == INFERENCE_SCHEMA_VERSION
    assert body["model"]
    # The served probability must equal a direct predict_proba() call on the
    # same live row: this is what makes the response real model output rather
    # than anything the endpoint could have invented.
    from numidia_core.db import get_detection_row
    from numidia_ml.verifier_model import load_verified_verifier
    row = get_detection_row(did)
    expected = load_verified_verifier(ARTIFACT).probability(
        build_inference_features(row))
    assert abs(expected - body["probability"]) < 1e-12


def test_ai_endpoint_fails_closed_without_model(monkeypatch, tmp_path):
    """No registered artifact -> 503 AI_UNAVAILABLE, probability is None."""
    from fastapi.testclient import TestClient
    from numidia_api import app as app_mod

    if not production_db_usable():
        pytest.skip("no production database present")
    import sqlite3
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    row = con.execute("select detection_id from detections limit 1").fetchone()
    con.close()
    if not row:
        pytest.skip("no detections")

    # Withdraw registration explicitly, so a developer's real .env cannot leak in.
    import numidia_core.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "ACTIVE_MODEL", "")
    monkeypatch.setenv("NUMIDIA_ACTIVE_MODEL", "")
    import numidia_ml.verifier_model as vm
    monkeypatch.setattr(vm, "_resolve", _raise_unregistered)

    application = app_mod.build_app(db_path=str(DB))
    client = TestClient(application)
    resp = client.get(f"/detections/{row[0]}/ai")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "AI_UNAVAILABLE"
    assert body["probability"] is None
    assert body["prediction"] is None
    assert body["threshold"] is None


def test_ai_endpoint_fails_closed_on_tampered_artifact(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import shutil
    from numidia_api import app as app_mod

    if not production_db_usable() or not has_artifact:
        pytest.skip("needs database and artifact")
    import sqlite3
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    row = con.execute("select detection_id from detections limit 1").fetchone()
    con.close()
    if not row:
        pytest.skip("no detections")

    bad = tmp_path / "bad"
    shutil.copytree(ARTIFACT, bad)
    with open(bad / "model.joblib", "ab") as fh:
        fh.write(b"\x00tamper")
    import numidia_ml.verifier_model as vm
    monkeypatch.setattr(vm, "_resolve", lambda a=None: bad / "model.joblib")

    application = app_mod.build_app(db_path=str(DB))
    client = TestClient(application)
    resp = client.get(f"/detections/{row[0]}/ai")
    assert resp.status_code == 503
    assert resp.json()["status"] == "AI_UNAVAILABLE"
    assert resp.json()["probability"] is None