"""Production inference contract and verifier interface.

This module wires *live* FIRMS detections to a verifier without requiring a database
and without requiring a model. It deliberately does NOT train, select, tune or
register anything.

Division of responsibility:

    NASA FIRMS NRT API
        -> firms.fetch_detections()              normalize
        -> processing.derive_features()          feature extraction
        -> inference.build_inference_features()   <-- THIS MODULE: the boundary
        -> WildfireVerifier.verify()              verdict

    normalized detection -> SQLite                persistence, independent

SQLite is an operational cache and history, never the AI's source of truth. Nothing
in this module imports the database layer, and `features_from_live_frame` operates on
a live frame directly, so the live path is exercisable with no DB at all.

Feature contract
----------------
`LIVE_INFERENCE_FEATURES` is derived from `labels.MODEL_FEATURES_V1` rather than
restated, so the training contract and the serving contract cannot silently drift
apart. Every listed feature must be suppliable by a live FIRMS/NRT detection.

`type` is deliberately absent and additionally listed as forbidden. It exists in the
historical archives but is null in live NRT data and in the whole 2026 test cohort, so
it identifies the split rather than the physics. It is never imputed, never defaulted,
and its missingness is never used as a signal.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol, Sequence

from numidia_ml.labels import BANNED_FEATURES, MODEL_FEATURES_V1

# --------------------------------------------------------------------------- contract

AI_UNAVAILABLE = "AI_UNAVAILABLE"

#: Bumped whenever the feature set or its semantics change. A verifier declares the
#: version it was fitted against; a mismatch fails closed rather than silently
#: reinterpreting a column.
INFERENCE_SCHEMA_VERSION = "live-v1"

#: The canonical, ordered live inference contract. Derived, never duplicated.
LIVE_INFERENCE_FEATURES: tuple[str, ...] = tuple(MODEL_FEATURES_V1)

#: Features that must be present AND finite. A live detection always carries these.
NUMERIC_REQUIRED: tuple[str, ...] = (
    "bright_ti4", "bright_ti5", "f_bt_diff", "frp", "f_frp",
)

#: Features FIRMS may legitimately leave empty. Present-but-null is valid; a
#: non-finite value is not. An absent key is an error (no silent defaulting).
NUMERIC_NULLABLE: tuple[str, ...] = (
    "confidence", "f_confidence", "scan", "track",
)

#: Categorical contract features, required and non-empty.
CATEGORICAL_REQUIRED: tuple[str, ...] = ("satellite",)

#: Derived fields: recomputed by the shared ingestion derivation rather than trusted
#: from the caller's row, so serving and training cannot diverge.
DERIVED_FEATURES: frozenset[str] = frozenset({"f_bt_diff", "f_frp", "f_confidence"})


def forbidden_features() -> frozenset[str]:
    """Columns that must never reach a model, at fit time or at serving time.

    Superset of the training-time ban list. The label/partition columns are named
    explicitly so the ban survives a refactor of `BANNED_FEATURES`.
    """
    return frozenset(BANNED_FEATURES) | {
        "type", "label", "ground_truth_id", "label_source", "event_id", "split",
        "fold", "cohort", "acq_year", "match_distance_m",
    }


def contract_violations() -> list[str]:
    """Contract fields that appear on the ban list. Expected to be empty.

    Asserted by the test-suite so that reintroducing a training-only column fails
    loudly instead of shipping.
    """
    return sorted(set(LIVE_INFERENCE_FEATURES) & forbidden_features())


# --------------------------------------------------------------------------- errors
class InferenceContractError(ValueError):
    """Runtime features do not satisfy the live inference contract. Fail closed."""


class VerifierUnavailable(RuntimeError):
    """No approved verifier can serve a probability. Fail closed."""


# --------------------------------------------------------------------------- value types
@dataclass(frozen=True)
class InferenceFeatures:
    """One validated live feature vector, in contract order."""

    values: dict[str, Any]
    schema_version: str = INFERENCE_SCHEMA_VERSION
    detection_id: str | None = None

    def __getitem__(self, key: str) -> Any:
        return self.values[key]

    def __contains__(self, key: str) -> bool:
        return key in self.values

    def __iter__(self):
        return iter(self.values)

    def keys(self):
        return self.values.keys()

    def items(self):
        return self.values.items()

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def as_vector(self) -> list[Any]:
        return [self.values[name] for name in LIVE_INFERENCE_FEATURES]


@dataclass(frozen=True)
class VerificationResult:
    """A served verdict. Only ever produced by an approved verifier."""

    probability: float
    assessment: str
    model_version: str
    threshold: float | None = None
    schema_version: str = INFERENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if isinstance(self.probability, bool) or not isinstance(
                self.probability, (int, float)):
            raise ValueError("probability must be a real number")
        if not math.isfinite(float(self.probability)):
            raise ValueError("probability must be finite")
        if not 0.0 <= float(self.probability) <= 1.0:
            raise ValueError("probability must lie in [0, 1]")


# --------------------------------------------------------------------------- validation
def _finite_number(value: Any) -> float:
    """Coerce to a finite float or raise. Never guesses, never imputes."""
    if isinstance(value, bool) or value is None:
        raise InferenceContractError(f"must be a finite numeric, got {value!r}")
    if isinstance(value, (int, float)):
        try:
            out = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise InferenceContractError(
                f"must be numeric, got {value!r}") from exc
    elif isinstance(value, str):
        # A numeric string is tolerated (SQLite returns text in places); a
        # non-numeric one is a contract violation, not something to interpret.
        try:
            out = float(value.strip())
        except (TypeError, ValueError) as exc:
            raise InferenceContractError(
                f"must be numeric, got {value!r}") from exc
    else:
        raise InferenceContractError(
            f"must be numeric, got {type(value).__name__}")
    if not math.isfinite(out):
        raise InferenceContractError(f"must be finite, got {value!r}")
    return out


def _clean_number(value: Any) -> float | None:
    """Like `_finite_number` but maps an invalid value to None instead of raising."""
    try:
        return _finite_number(value)
    except InferenceContractError:
        return None


def validate_feature_vector(
    features: Mapping[str, Any],
    *,
    schema_version: str = INFERENCE_SCHEMA_VERSION,
    detection_id: str | None = None,
) -> InferenceFeatures:
    """Validate an explicitly supplied feature vector against the live contract.

    Used when a caller (or a future model's own declared contract) hands features
    over directly, as opposed to deriving them from a live detection.
    """
    if schema_version != INFERENCE_SCHEMA_VERSION:
        raise InferenceContractError(
            f"feature schema version mismatch: runtime expects "
            f"{INFERENCE_SCHEMA_VERSION!r}, caller supplied {schema_version!r}"
        )
    if not isinstance(features, Mapping):
        raise InferenceContractError(
            f"expected a mapping of features, got {type(features).__name__}")

    hits = sorted(set(features) & forbidden_features())
    if hits:
        raise InferenceContractError(
            f"forbidden training-only or unavailable features are not permitted in "
            f"the live inference contract: {', '.join(hits)}"
        )

    missing = [n for n in LIVE_INFERENCE_FEATURES if n not in features]
    if missing:
        raise InferenceContractError(
            f"missing required inference features: {', '.join(missing)}")
    extra = sorted(set(features) - set(LIVE_INFERENCE_FEATURES))
    if extra:
        raise InferenceContractError(
            f"unexpected features outside the live inference contract: "
            f"{', '.join(extra)}")

    values: dict[str, Any] = {}

    for name in NUMERIC_REQUIRED:
        raw = features[name]
        if raw is None:
            raise InferenceContractError(f"{name} is required and must not be null")
        num = _clean_number(raw)
        if num is None:
            raise InferenceContractError(
                f"{name} must be a finite numeric, got {raw!r}")
        values[name] = num

    for name in NUMERIC_NULLABLE:
        raw = features[name]
        if raw is None:
            values[name] = None
            continue
        num = _clean_number(raw)
        if num is None:
            raise InferenceContractError(
                f"{name} must be null or a finite numeric, got {raw!r}")
        values[name] = num

    for name in CATEGORICAL_REQUIRED:
        raw = features[name]
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            raise InferenceContractError(
                f"{name} is required and must be a non-empty value, got {raw!r}")
        values[name] = str(raw)

    return InferenceFeatures(values=values, schema_version=schema_version,
                             detection_id=detection_id)


def build_inference_features(
    detection: Mapping[str, Any],
    *,
    schema_version: str = INFERENCE_SCHEMA_VERSION,
) -> InferenceFeatures:
    """Build the inference vector for ONE canonical normalized FIRMS detection.

    Accepts a full live row (canonical FIRMS columns plus derived `f_*` fields and
    GIS enrichment) and selects only the live contract. Extra columns are ignored by
    design: a real detection legitimately carries `lat`, `lon`, `wilaya_name`, `type`,
    `f_month` and so on. None of those may be *features*, and none should fail the
    build merely by being present on the row.

    Derived features are recomputed by the same `processing.derive_features` the
    ingestion pipeline uses, so a stale or forged `f_*` value on a row cannot reach
    the model. `type` is never read: null, absent or populated, the result is
    identical and its missingness carries no signal.
    """
    if schema_version != INFERENCE_SCHEMA_VERSION:
        raise InferenceContractError(
            f"feature schema version mismatch: runtime expects "
            f"{INFERENCE_SCHEMA_VERSION!r}, caller supplied {schema_version!r}"
        )
    if isinstance(detection, InferenceFeatures):
        return detection
    if isinstance(detection, Mapping):
        row = dict(detection)
    else:
        raise InferenceContractError(
            f"expected a mapping-like detection, got {type(detection).__name__}")

    # Name a missing SOURCE column by its real name before derivation, so the error
    # points at the field the caller has to fix.
    source_required = [f for f in LIVE_INFERENCE_FEATURES
                       if f not in DERIVED_FEATURES]
    absent = [f for f in source_required if f not in row]
    if absent:
        raise InferenceContractError(
            f"missing required inference features: {', '.join(absent)}")

    from numidia_core.processing import derive_features

    derived = derive_features(_as_frame(row))
    selected = {name: _column_value(derived, name, row) for name in LIVE_INFERENCE_FEATURES}
    return validate_feature_vector(selected, schema_version=schema_version,
                                   detection_id=row.get("detection_id"))


def features_from_live_frame(frame) -> list[InferenceFeatures]:
    """Build inference vectors straight from a live FIRMS frame. No database.

    This is the live path: `firms.fetch_detections()` -> here. Persistence to SQLite
    is a separate, optional step, so the AI boundary is reachable with no stored
    history at all.
    """
    import pandas as pd

    from numidia_core.processing import derive_features

    if not isinstance(frame, pd.DataFrame):
        raise InferenceContractError(
            f"expected a DataFrame of live detections, got {type(frame).__name__}")
    if frame.empty:
        raise InferenceContractError("live FIRMS frame is empty")

    enriched = derive_features(frame)
    out: list[InferenceFeatures] = []
    failures: list[str] = []
    for row in enriched.to_dict("records"):
        try:
            out.append(build_inference_features(row))
        except InferenceContractError as exc:
            failures.append(str(exc))
    if not out:
        # Every row failed: that is a contract mismatch, not per-row data noise.
        raise InferenceContractError(
            f"no live detection satisfied the inference contract ({len(failures)} "
            f"rejected); first error: {failures[0]}"
        )
    return out


def assert_model_features_match(
    model_features: Sequence[str],
    *,
    model_version: str = "unknown",
) -> None:
    """A verifier's own contract must equal the runtime contract, exactly.

    Guards the silent-corruption case: a model fitted on a different feature set
    would otherwise produce plausible, wrong probabilities.
    """
    declared = list(model_features)
    missing = sorted(set(LIVE_INFERENCE_FEATURES) - set(declared))
    extra = sorted(set(declared) - set(LIVE_INFERENCE_FEATURES))
    if missing or extra:
        raise InferenceContractError(
            f"model {model_version!r} feature contract does not match runtime "
            f"{INFERENCE_SCHEMA_VERSION!r}: missing={missing or 'none'} "
            f"unexpected={extra or 'none'}"
        )


# --------------------------------------------------------------------------- internals
def _as_frame(row: dict):
    import pandas as pd

    return pd.DataFrame([row])


def _column_value(frame, name: str, fallback_row: dict) -> Any:
    """Read one contract column off a derived frame, with the source row as backstop."""
    if name in frame.columns:
        series = frame[name]
        if len(series):
            value = series.iloc[0]
            if not (isinstance(value, float) and value != value):  # NaN
                return fallback_row.get(name)
            return value
    return fallback_row.get(name)


# --------------------------------------------------------------------------- verifier
class WildfireVerifier(Protocol):
    """The verifier interface the production path depends on."""

    version: str
    feature_names: tuple[str, ...]
    schema_version: str

    def verify(self, features: InferenceFeatures) -> VerificationResult:
        """Score one detection, or raise `VerifierUnavailable`."""
        ...


class UnavailableVerifier:
    """The only implementation registered today. Always fails closed.

    It exists so the live path can be wired and exercised end to end while still
    serving nothing: no probability, no verdict, no confidence, no model. Not a
    default, not a zero, not a prior, and stable across repeated calls.
    """

    version = "none"
    feature_names = LIVE_INFERENCE_FEATURES
    schema_version = INFERENCE_SCHEMA_VERSION

    def __init__(self, message: str | None = None) -> None:
        self.message = message or (
            "No evaluated wildfire verifier is registered. Probabilities are "
            "intentionally NOT served."
        )

    def verify(self, features: InferenceFeatures) -> VerificationResult:
        raise VerifierUnavailable(self.message)

    def status(self) -> dict:
        return {"status": AI_UNAVAILABLE, "model": None, "message": self.message}

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "UnavailableVerifier(AI_UNAVAILABLE)"


def load_verifier(*, model_path: str | None = None,
                  message: str | None = None) -> WildfireVerifier:
    """Return the verifier for the serving path.

    Always returns an `UnavailableVerifier` today. `model_path` is accepted for
    signature compatibility with a future registry and is deliberately ignored:
    pointing `NUMIDIA_ACTIVE_MODEL` at a file must not by itself enable serving,
    which is the behaviour `pipeline.verification_status()` already guarantees.
    """
    del model_path
    return UnavailableVerifier(message)


def verify_detections(features: Iterable[InferenceFeatures],
                      *, model_path: str | None = None) -> list[VerificationResult]:
    """Score a batch of live detections.

    Raises `VerifierUnavailable` as soon as the verifier declines, so a caller can
    never observe a partial result set that looks like successful scoring.
    """
    verifier = load_verifier(model_path=model_path)
    return [verifier.verify(f) for f in features]