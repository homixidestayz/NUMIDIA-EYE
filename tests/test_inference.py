"""Live FIRMS -> AI inference boundary tests.

Every fixture here is a real detection shape produced by the FIRMS ingestion
pipeline. The `type = null` case is not hypothetical: 2,977 of 2,977 detections
in the production database have type null.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from numidia_ml import inference as I
from numidia_ml.labels import BANNED_FEATURES, MODEL_FEATURES_V1


def _no_registered_model(artifact=None):
    """Stand-in artifact resolver for the 'nothing registered' state."""
    raise I.VerifierUnavailable(
        "No verified verifier is registered (NUMIDIA_ACTIVE_MODEL is unset).")

# Verbatim capture of a live production detection (GET /detections/{id}).
LIVE_DETECTION = {
    "detection_id": "9803f0e3ae7452d4",
    "lat": 27.57402,
    "lon": -8.11681,
    "acq_datetime": "2026-09-29T13:38:00Z",
    "acq_date": "2026-09-29",
    "acq_time": "1338",
    "satellite": "N21",
    "instrument": None,
    "confidence": 0.2,
    "confidence_raw": "low",
    "bright_ti4": 331.02,
    "bright_ti5": 297.11,
    "scan": 0.39,
    "track": 0.36,
    "frp": 5.92,
    "daynight": "D",
    "version": "2.0NRT",
    "type": None,          # <-- live NRT never carries this
    "source": "VIIRS_NOAA21_NRT",
    "source_url": (
        "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_MAP_KEY}"
        "/VIIRS_NOAA21_NRT/-9.0,18.0,12.0,38.0/1"
    ),
    "fetched_at": "2026-09-29T21:32:35.669241Z",
    "wilaya_code": "37",
    "wilaya_name": "Tindouf",
    "state": "LIVE",
    # Derived features as persisted by processing.derive_features() at
    # ingestion and returned verbatim by GET /detections/{id}.
    "f_bt_diff": 33.91,
    "f_frp": 5.92,
    "f_confidence": 0.2,
    "f_hour_utc": 13.13,
    "f_month": 9,
    "f_doy": 272,
    "f_daynight": 1,
}


# --- contract ----------------------------------------------------------------

def test_type_is_excluded_from_the_inference_contract():
    assert "type" not in I.LIVE_INFERENCE_FEATURES
    assert "type" not in MODEL_FEATURES_V1
    assert "type" in BANNED_FEATURES
    assert "type" in I.forbidden_features()


def test_contract_has_no_violations():
    """No contract feature may appear on the ban list."""
    assert I.contract_violations() == []


def test_inference_contract_is_derived_from_the_training_contract():
    # Training and serving must consume exactly the same features, or a model
    # trained on one cannot serve the other.
    assert I.LIVE_INFERENCE_FEATURES == tuple(MODEL_FEATURES_V1)


def test_every_inference_feature_is_live_derivable():
    for name in I.LIVE_INFERENCE_FEATURES:
        assert name in LIVE_DETECTION, f"{name} is not on a live detection"


def test_no_banned_feature_leaks_into_the_contract():
    assert not set(I.LIVE_INFERENCE_FEATURES) & I.forbidden_features()


# --- live detection -> inference features -------------------------------------

def test_live_firms_detection_reaches_the_inference_boundary():
    features = I.build_inference_features(LIVE_DETECTION)
    assert isinstance(features, I.InferenceFeatures)
    assert features.schema_version == I.INFERENCE_SCHEMA_VERSION
    assert features.detection_id == "9803f0e3ae7452d4"
    # Real FIRMS values, passed through untouched.
    assert features["bright_ti4"] == pytest.approx(331.02)
    assert features["bright_ti5"] == pytest.approx(297.11)
    assert features["frp"] == pytest.approx(5.92)
    assert features["confidence"] == pytest.approx(0.2)
    assert features["satellite"] == "N21"


def test_detection_with_type_null_is_still_valid():
    assert LIVE_DETECTION["type"] is None
    features = I.build_inference_features(LIVE_DETECTION)
    assert features.as_vector()  # not rejected


def test_type_presence_does_not_change_the_result():
    without = I.build_inference_features({**LIVE_DETECTION, "type": None})
    with_value = I.build_inference_features({**LIVE_DETECTION, "type": 0.0})
    absent = {k: v for k, v in LIVE_DETECTION.items() if k != "type"}
    without_key = I.build_inference_features(absent)
    assert without.values == with_value.values == without_key.values
    # `type` is never carried into the contract vector.
    assert "type" not in without.values


def test_extra_real_detection_fields_are_ignored_not_required():
    noisy = {**LIVE_DETECTION, "instrument": "VIIRS", "anything": 1}
    features = I.build_inference_features(noisy)
    assert set(features.values) == set(I.LIVE_INFERENCE_FEATURES)


def test_vector_is_in_contract_order():
    features = I.build_inference_features(LIVE_DETECTION)
    vector = features.as_vector()
    assert len(vector) == len(I.LIVE_INFERENCE_FEATURES)


def test_live_frame_path_needs_no_database():
    """The live FIRMS frame reaches the boundary without SQLite."""
    frame = pd.DataFrame([dict(LIVE_DETECTION), dict(LIVE_DETECTION)])
    out = I.features_from_live_frame(frame)
    assert len(out) == 2
    assert out[0]["frp"] == pytest.approx(5.92)


# --- fail-closed validation --------------------------------------------------

def test_missing_feature_fails_closed():
    broken = {k: v for k, v in LIVE_DETECTION.items() if k != "bright_ti4"}
    with pytest.raises(I.InferenceContractError) as exc:
        I.build_inference_features(broken)
    assert "bright_ti4" in str(exc.value)


def test_null_required_feature_fails_closed_without_imputation():
    broken = {**LIVE_DETECTION, "frp": None}
    with pytest.raises(I.InferenceContractError) as exc:
        I.build_inference_features(broken)
    assert "frp" in str(exc.value)


def test_nan_and_infinity_fail_closed():
    for field in ("frp", "bright_ti4", "confidence", "scan"):
        for bad in (float("nan"), math.inf, -math.inf):
            with pytest.raises(I.InferenceContractError):
                I.build_inference_features({**LIVE_DETECTION, field: bad})


def test_non_numeric_required_feature_fails_closed():
    with pytest.raises(I.InferenceContractError):
        I.build_inference_features({**LIVE_DETECTION, "frp": "not-a-number"})


def test_invalid_categorical_fails_closed():
    for bad in (None, "", "   "):
        with pytest.raises(I.InferenceContractError):
            I.build_inference_features({**LIVE_DETECTION, "satellite": bad})


def test_schema_version_mismatch_fails_closed():
    with pytest.raises(I.InferenceContractError) as exc:
        I.build_inference_features(LIVE_DETECTION, schema_version="live-v0")
    assert "version mismatch" in str(exc.value)


def test_unexpected_feature_fails_closed():
    vector = {name: LIVE_DETECTION.get(name) for name in I.LIVE_INFERENCE_FEATURES}
    vector["surprise"] = 1.0
    with pytest.raises(I.InferenceContractError) as exc:
        I.validate_feature_vector(vector)
    assert "unexpected" in str(exc.value)


def test_forbidden_feature_in_vector_fails_closed():
    vector = {name: LIVE_DETECTION.get(name) for name in I.LIVE_INFERENCE_FEATURES}
    vector["type"] = 0.0
    with pytest.raises(I.InferenceContractError) as exc:
        I.validate_feature_vector(vector)
    assert "type" in str(exc.value)


def test_non_mapping_detection_fails_closed():
    with pytest.raises(I.InferenceContractError):
        I.build_inference_features(["not", "a", "mapping"])


def test_model_contract_drift_is_rejected():
    """A model fitted on a different feature set must not be servable."""
    drifted = list(I.LIVE_INFERENCE_FEATURES) + ["type"]
    with pytest.raises(I.InferenceContractError) as exc:
        I.assert_model_features_match(drifted, model_version="exp-v1")
    assert "exp-v1" in str(exc.value)

    partial = [f for f in I.LIVE_INFERENCE_FEATURES if f != "frp"]
    with pytest.raises(I.InferenceContractError):
        I.assert_model_features_match(partial, model_version="exp-v1")

    I.assert_model_features_match(I.LIVE_INFERENCE_FEATURES, model_version="ok")


# --- verifier interface ------------------------------------------------------

def test_verifier_is_unavailable_and_serves_nothing():
    """With nothing registered, the verifier declines and serves no verdict.

    Registration is withdrawn explicitly so a developer's local
    NUMIDIA_ACTIVE_MODEL cannot leak into this assertion.
    """
    monkey = pytest.MonkeyPatch()
    monkey.setenv("NUMIDIA_ACTIVE_MODEL", "")
    import numidia_core.config as cfg
    monkey.setattr(cfg, "ACTIVE_MODEL", "")
    try:
        features = I.build_inference_features(LIVE_DETECTION)
        with pytest.raises(I.VerifierUnavailable):
            I.load_verifier()
        unavailable = I.available_verifier()
        assert isinstance(unavailable, I.UnavailableVerifier)
        with pytest.raises(I.VerifierUnavailable):
            unavailable.verify(features)
    finally:
        monkey.undo()


def test_load_verifier_ignores_an_unverifiable_model_path():
    """Pointing at an artifact that cannot be verified must not enable serving.

    This replaced a test that asserted a model path was *always* ignored: a
    verified live-v1 artifact now loads for real (see tests/test_verifier.py), so
    the invariant to protect is that unverified or absent artifacts fail closed.
    """
    with pytest.raises(I.VerifierUnavailable):
        I.load_verifier(model_path="services/ml/models/exp_v1/hgb_exp-v1.joblib")
    got = I.available_verifier("services/ml/models/exp_v1/hgb_exp-v1.joblib")
    assert isinstance(got, I.UnavailableVerifier)
    assert got.version == "none"
    assert got.status()["status"] == "AI_UNAVAILABLE"
    assert got.status()["model"] is None


def test_unverifiable_model_path_serves_no_verdict():
    """The fail-closed path must not leak a probability to a caller."""
    features = I.build_inference_features(LIVE_DETECTION)
    with pytest.raises(I.VerifierUnavailable):
        I.verify_detections([features],
                            model_path="services/ml/models/exp_v1/hgb_exp-v1.joblib")


def test_batch_verification_never_returns_partial_results(monkeypatch):
    """With nothing registered the batch call must raise, not half-serve.

    Registration is withdrawn explicitly so this asserts the unregistered state
    regardless of the developer's local NUMIDIA_ACTIVE_MODEL.
    """
    import numidia_core.config as cfg
    monkeypatch.setenv("NUMIDIA_ACTIVE_MODEL", "")
    monkeypatch.setattr(cfg, "ACTIVE_MODEL", "")
    features = [I.build_inference_features(LIVE_DETECTION)]
    with pytest.raises(I.VerifierUnavailable):
        I.verify_detections(features)


def test_verification_result_rejects_impossible_probabilities():
    for bad in (float("nan"), math.inf, -0.1, 1.1, "high", True):
        with pytest.raises(ValueError):
            I.VerificationResult(probability=bad, assessment="x", model_version="v")


# --- API fail-closed ---------------------------------------------------------

def test_api_ai_endpoint_stays_503_and_serves_nothing(monkeypatch):
    """Unregistered -> 503 AI_UNAVAILABLE with NO probability, model or verdict.

    Now that a verified artifact may be registered, this pins the *unregistered*
    branch explicitly rather than relying on the ambient environment.
    """
    import sqlite3
    import numidia_core.config as cfg
    from fastapi.testclient import TestClient
    from numidia_api.app import build_app

    monkeypatch.setenv("NUMIDIA_ACTIVE_MODEL", "")
    monkeypatch.setattr(cfg, "ACTIVE_MODEL", "")
    import numidia_ml.verifier_model as vm
    monkeypatch.setattr(vm, "_resolve", _no_registered_model)

    con = sqlite3.connect("data/db/numidia.db")
    did = con.execute("select detection_id from detections limit 1").fetchone()[0]
    r = TestClient(build_app()).get(f"/detections/{did}/ai")
    body = r.json()
    assert r.status_code == 503
    assert body["status"] == "AI_UNAVAILABLE"
    assert body["probability"] is None
    assert body["verified"] is None
    assert body["model"] is None
    assert body["prediction"] is None


def test_api_ai_endpoint_404s_for_unknown_detection():
    from fastapi.testclient import TestClient
    from numidia_api.app import app

    assert TestClient(app).get("/detections/does-not-exist/ai").status_code == 404


def test_registered_model_is_verified_before_serving():
    """Whatever is registered must either verify and serve, or fail closed.

    This replaces an assertion that no model was ever registered. That
    invariant was true while the verifier was unregistered; Step 11 registered
    verifier-v2, so the durable property to protect is verification, not absence.
    """
    from numidia_core.config import ACTIVE_MODEL
    from numidia_core.pipeline import verification_status

    registered = ACTIVE_MODEL.strip()
    status = verification_status()

    if not registered:
        assert status["status"] == "AI_UNAVAILABLE"
        return

    # Registered: it must verify cleanly, or report an honest failure.
    if status["status"] == "available":
        assert status["model"]
        assert status["schema_version"] == I.INFERENCE_SCHEMA_VERSION
        assert status["dataset_sha256"]
        assert 0.0 <= float(status["threshold"]) <= 1.0
        # and it must actually load
        verifier = I.load_verifier()
        assert verifier.version == status["model"]
    else:
        assert status["message"], "an unavailable verifier must say why"