"""Production verifier backed by a trained live-v1 artifact.

Fail-closed by construction. Every one of the following returns
`VerifierUnavailable` rather than a fabricated probability:

  * artifact file missing / unreadable
  * manifest or config missing or malformed
  * model file SHA does not match the manifest
  * dataset provenance SHA absent
  * declared schema_version != runtime `INFERENCE_SCHEMA_VERSION`
  * declared feature list != runtime `LIVE_INFERENCE_FEATURES` (order-sensitive)
  * a forbidden feature (`type`, label columns) appears in the feature list
  * threshold missing or outside [0, 1]
  * a loaded model that cannot produce a finite probability in [0, 1]
  * non-finite or missing features at call time (via inference validation)

The live FIRMS observation is the only input. SQLite is never consulted here.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib

from numidia_ml.inference import (INFERENCE_SCHEMA_VERSION, InferenceFeatures,
                                  VerifierUnavailable, assert_model_features_match,
                                  forbidden_features)

PREDICTION_FIRE = "FIRE"
PREDICTION_NON_FIRE = "NON_FIRE"
PREDICTION_UNCERTAIN = "UNCERTAIN"


def _read_json(p: Path, what: str) -> dict:
    if not p.exists():
        raise VerifierUnavailable(f"artifact {what} missing: {p.name}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise VerifierUnavailable(f"artifact {what} is unreadable: {exc}") from exc


def _sha256(p: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve(artifact: Path | str | None) -> Path:
    """Locate the registered artifact's model file.

    Accepts a file or a directory (the artifact directory is the natural unit,
    since config/manifest/metrics live beside the model). `NUMIDIA_ACTIVE_MODEL`
    is read at call time so an operator can register or withdraw a model without
    reimporting the process.
    """
    if artifact is not None:
        p = Path(artifact)
        return p / "model.joblib" if p.is_dir() else p
    from numidia_core.config import ACTIVE_MODEL
    mp = (ACTIVE_MODEL or "").strip()
    if not mp:
        raise VerifierUnavailable(
            "No verified verifier is registered (NUMIDIA_ACTIVE_MODEL is unset).")
    p = Path(mp)
    if p.is_dir():
        return p / "model.joblib"
    if not p.exists():
        # a bare filename is not enough: the artifact must be complete
        for cand in (p.parent / "model.joblib",
                     REPO_ROOT / "services" / "ml" / "models" / p.name / "model.joblib"):
            if cand.exists():
                return cand
    return p


REPO_ROOT = Path(__file__).resolve().parents[2]


class SklearnWildfireVerifier:
    """Real inference from a trained live-v1 pipeline. No default predictions."""

    version = "unknown"
    feature_names: tuple[str, ...] = ()
    schema_version = INFERENCE_SCHEMA_VERSION

    def __init__(self, model_path: Path | str, *, verify: bool = True) -> None:
        model_file = Path(model_path)
        root = model_file.parent
        self.model_path = model_file

        config = _read_json(root / "config.json", "config")
        manifest = _read_json(root / "manifest.json", "manifest")

        schema = str(config.get("schema_version", ""))
        if schema != INFERENCE_SCHEMA_VERSION:
            raise VerifierUnavailable(
                f"artifact schema_version {schema!r} != runtime "
                f"{INFERENCE_SCHEMA_VERSION!r}; refusing to reinterpret columns")

        feats = list(config.get("feature_order") or config.get("features") or [])
        if not feats:
            raise VerifierUnavailable("artifact declares no feature order")
        try:
            assert_model_features_match(feats, model_version=str(config.get("model_version")))
        except Exception as exc:  # noqa: BLE001
            raise VerifierUnavailable(str(exc)) from exc
        banned = sorted(set(feats) & forbidden_features())
        if banned:
            raise VerifierUnavailable(
                f"artifact feature list contains forbidden features: {banned}")

        if not config.get("dataset_sha256"):
            raise VerifierUnavailable(
                "artifact records no dataset provenance SHA; refusing to serve")
        if manifest.get("dataset_sha256") != config.get("dataset_sha256"):
            raise VerifierUnavailable(
                "artifact manifest/config dataset provenance disagree")

        thr = config.get("threshold")
        if thr is None or not (0.0 <= float(thr) <= 1.0):
            raise VerifierUnavailable(f"artifact threshold invalid: {thr!r}")
        band = config.get("uncertainty_band") or {}
        non_fire_thr = band.get("non_fire_threshold")
        if non_fire_thr is not None and not (0.0 <= float(non_fire_thr) <= 1.0):
            raise VerifierUnavailable(
                f"artifact non-fire threshold invalid: {non_fire_thr!r}")

        if not model_file.exists():
            raise VerifierUnavailable(f"model file missing: {model_file}")
        if verify:
            want = manifest.get("model_sha256")
            if want and _sha256(model_file) != want:
                raise VerifierUnavailable(
                    "model file SHA does not match the manifest; artifact was "
                    "modified after training")

        try:
            model = joblib.load(model_file)
        except Exception as exc:  # noqa: BLE001
            raise VerifierUnavailable(f"model is unloadable: {exc}") from exc

        self.model = model
        self.config = config
        self.manifest = manifest
        self.version = str(config.get("model_version", "unknown"))
        self.feature_names = tuple(feats)
        self.schema_version = schema
        self.threshold = float(thr)
        self.non_fire_threshold = (float(non_fire_thr)
                                   if non_fire_thr is not None else None)
        self.calibrated = bool(config.get("calibrated", False))
        self.scope = str(config.get("scope", ""))

    # ------------------------------------------------------------------ scoring
    def probability(self, features: InferenceFeatures) -> float:
        import pandas as pd

        row = pd.DataFrame([{name: features[name] for name in self.feature_names}],
                           columns=list(self.feature_names))
        try:
            proba = self.model.predict_proba(row)
        except Exception as exc:  # noqa: BLE001
            raise VerifierUnavailable(f"model inference failed: {exc}") from exc
        p = float(proba[0][1])
        if not (0.0 <= p <= 1.0):
            raise VerifierUnavailable(f"model produced out-of-range probability {p}")
        return p

    def classify(self, p: float) -> str:
        """FIRE / NON_FIRE / UNCERTAIN from the artifact's own thresholds.

        The band is a documented operating margin, not a claim of calibrated
        scientific confidence.
        """
        if p >= self.threshold:
            return PREDICTION_FIRE
        if self.non_fire_threshold is not None and p <= self.non_fire_threshold:
            return PREDICTION_NON_FIRE
        return PREDICTION_UNCERTAIN

    def verify(self, features: InferenceFeatures):
        from numidia_ml.inference import VerificationResult

        p = self.probability(features)
        pred = self.classify(p)
        return VerificationResult(
            probability=p, assessment=pred, model_version=self.version,
            threshold=self.threshold, schema_version=self.schema_version)

    def status(self) -> dict:
        return {
            "status": "available",
            "model": self.version,
            "model_path": str(self.model_path),
            "schema_version": self.schema_version,
            "features_schema": self.schema_version,
            "threshold": self.threshold,
            "non_fire_threshold": self.non_fire_threshold,
            "calibrated": self.calibrated,
            "dataset_sha256": self.config.get("dataset_sha256"),
            "scope": self.scope,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"SklearnWildfireVerifier({self.version!r}, thr={self.threshold})"


def load_verified_verifier(artifact: Path | str | None = None,
                           *, verify: bool = True) -> SklearnWildfireVerifier:
    """Load and fully verify. Raises VerifierUnavailable on any doubt."""
    return SklearnWildfireVerifier(_resolve(artifact), verify=verify)