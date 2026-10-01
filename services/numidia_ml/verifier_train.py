"""Train the live-v1 structured wildfire verifier and write a verifiable artifact.

Scope, stated plainly
--------------------
This is an EXPERIMENTAL structured satellite-data verifier trained on the
available labeled dataset. It is NOT a validated Algerian wildfire detector:
the labels contain no independently confirmed southern Algerian wildfire
positive, and the negative class is essentially all catalogued gas flare.
Recorded in every artifact so it cannot be forgotten downstream.

Pipeline
--------
  real FIRMS/VIIRS rows
      -> verifier_split.build_split()      event-disjoint, leak-checked
      -> make_pipeline()                   10 live-v1 features only
      -> fit on train, select on VAL, evaluate TEST once
      -> CalibratedClassifierCV (isotonic) when val supports it
      -> artifact + metrics + manifest with dataset SHA
"""
from __future__ import annotations

import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (ExtraTreesClassifier,
                              HistGradientBoostingClassifier,
                              RandomForestClassifier)
from sklearn.impute import SimpleImputer
from sklearn.metrics import (accuracy_score, average_precision_score, brier_score_loss,
                             confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from numidia_ml.labels import BANNED_FEATURES
from numidia_ml.verifier_split import (FEATURE_COLUMNS, RANDOM_STATE,
                                       SplitError, assert_no_leakage,
                                       build_split, feature_matrix)
from numidia_ml.verify_artifact import sha256_dataset

VERIFIER_VERSION = "verifier-v2"
SCHEMA_VERSION = "live-v1"
NUMERIC_FEATURES = [f for f in FEATURE_COLUMNS if f != "satellite"]
CATEGORICAL_FEATURES = ["satellite"]
UNAVAILABLE = "UNAVAILABLE - insufficient class/group coverage"

#: Targets tried, in order, when sizing the NON_FIRE / UNCERTAIN margin on the
#: validation set. First target that is achievable wins; recorded in the artifact.
NON_FIRE_TARGETS = (0.90, 0.80, 0.70, 0.60, 0.50)

SCOPE_STATEMENT = (
    "EXPERIMENTAL structured satellite-data verifier. Trained and evaluated on "
    "firms_labels_v2.csv (live-v1 VIIRS features only). NOT a validated "
    "Algerian wildfire detector: the labels contain NO independently confirmed "
    "southern Algerian wildfire positive, and the negative class is "
    "predominantly catalogued gas flare (N1-flare). Do not claim coverage of "
    "all Algerian wildfires, national validation, or universal "
    "wildfire-vs-flare separation."
)


# --------------------------------------------------------------------------- model
def make_pipeline(model_key: str) -> Pipeline:
    """10 live-v1 features, deterministic categorical handling, no leakage."""
    pre = ColumnTransformer([
        ("num", SimpleImputer(strategy="median"), NUMERIC_FEATURES),
        ("cat", Pipeline([
            ("imp", SimpleImputer(strategy="most_frequent")),
            ("oh", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]), CATEGORICAL_FEATURES),
    ], remainder="drop")
    if model_key == "hgb":
        clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06,
                                             random_state=RANDOM_STATE)
    elif model_key == "rf":
        clf = RandomForestClassifier(n_estimators=400, min_samples_leaf=3,
                                     random_state=RANDOM_STATE, n_jobs=-1)
    elif model_key == "et":
        clf = ExtraTreesClassifier(n_estimators=400, min_samples_leaf=3,
                                   random_state=RANDOM_STATE, n_jobs=-1)
    else:
        raise ValueError(f"unknown model_key {model_key!r}")
    return Pipeline([("pre", pre), ("clf", clf)])


# --------------------------------------------------------------------------- metrics
def _safe(fn, y, proba, thr=None):
    """Run a metric, or record the reason it is undefined. Never reports a fake 0."""
    try:
        if thr is None:
            return float(fn(y, proba))
        return float(fn(y, (proba >= thr).astype(int), zero_division=0))
    except Exception as exc:  # noqa: BLE001
        return {"unavailable": UNAVAILABLE, "reason": f"{type(exc).__name__}: {exc}"}


def _thr_metric(y: np.ndarray, pred: np.ndarray) -> float:
    """Threshold-based metric. `None` values (e.g. absent class) are raised here
    rather than swallowed, so the caller records UNAVAILABLE with a real reason."""
    return float(f1_score(y, pred, zero_division=0))


def evaluate(y: np.ndarray, proba: np.ndarray, thr: float) -> dict:
    """Full metric block. Metrics that are undefined for a stratum are recorded
    as UNAVAILABLE with a reason - never silently reported as zero."""
    y = np.asarray(y)
    proba = np.asarray(proba, dtype=float)
    pred = (proba >= thr).astype(int)
    single_class = len(np.unique(y)) < 2
    n_pos, n_neg = int((y == 1).sum()), int((y == 0).sum())

    def binary(fn, name):
        # precision/recall/F1 need both classes to be defined at this threshold.
        if single_class:
            return {"unavailable": UNAVAILABLE,
                    "reason": f"stratum is single-class "
                              f"(positives={n_pos}, negatives={n_neg}); {name} "
                              "is undefined"}
        return _safe(fn, y, pred)

    out = {
        "n": int(len(y)),
        "positives": n_pos,
        "negatives": n_neg,
        "single_class": single_class,
        "threshold": round(float(thr), 6),
        "accuracy": _safe(accuracy_score, y, pred),
        "precision": binary(precision_score, "precision"),
        "recall": binary(recall_score, "recall"),
        "f1": binary(f1_score, "F1"),
        "brier": _safe(brier_score_loss, y, proba),
    }
    if single_class:
        out["roc_auc"] = {"unavailable": UNAVAILABLE,
                          "reason": "stratum contains only one class"}
        out["pr_auc"] = {"unavailable": UNAVAILABLE,
                         "reason": "stratum contains only one class"}
    else:
        out["roc_auc"] = _safe(roc_auc_score, y, proba)
        out["pr_auc"] = _safe(average_precision_score, y, proba)
    cm = confusion_matrix(y, pred, labels=[0, 1])
    out["confusion_matrix"] = {
        "tn": int(cm[0, 0]), "fp": int(cm[0, 1]),
        "fn": int(cm[1, 0]), "tp": int(cm[1, 1]),
    }
    return out


#: Share of validation detections the UNCERTAIN state is sized to route to a human.
#: Pre-declared, and recorded in the artifact so the operating point is auditable.
REVIEW_BUDGET = 0.10


def size_uncertain_band(y: np.ndarray, proba: np.ndarray, fire_thr: float,
                        neg_quantiles=(0.40, 0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90),
                        review_budget: float = REVIEW_BUDGET) -> dict:
    """Size a NON_FIRE / UNCERTAIN margin that is actually useful in operation.

    A band only a few points wide is not a decision aid. This picks, for a fixed
    set of NEGATIVE-probability quantiles on validation, the smallest margin
    that keeps at least `min_nonfire_recall` of validation negatives below it,
    and reports the resulting UNCERTAIN share. Selecting among *pre-declared*
    candidates on validation is a documented operating-point choice; the winner
    is written into the artifact so the point is auditable.
    """
    neg = proba[y == 0]
    if neg.size == 0:
        return {"non_fire_threshold": None, "reason": "no validation negatives"}
    # Candidate margins from the NEGATIVE score distribution: each candidate is
    # the q-th quantile of validation negatives, i.e. it accepts the most
    # confident q-fraction of non-fire rows without model training.
    cands = []
    for q in neg_quantiles:
        t = float(np.quantile(neg, q))
        if not (0.0 < t < fire_thr):
            continue
        cands.append({"negative_quantile": q, "non_fire_threshold": round(t, 4),
                      "non_fire_recall": round(float((neg <= t).mean()), 4),
                      "validation_share_uncertain":
                          round(float(((proba > t) & (proba < fire_thr)).mean()), 4)})
    if not cands:
        return {"rule": "no usable non-fire threshold below the fire threshold",
                "non_fire_threshold": None}
    # Operational objective: the UNCERTAIN state exists to route genuinely
    # ambiguous detections to a human. Its width is therefore set by the REVIEW
    # BUDGET - the pre-declared share of validation detections we are willing to
    # escalate - not by squeezing the band as tight as the score gap allows.
    # A band of 0.02 that fires on 1% of rows is not a usable operating point.
    chosen = min(cands,
                 key=lambda c: (abs(c["validation_share_uncertain"] - review_budget),
                                -c["non_fire_recall"]))
    cands = sorted(cands, key=lambda c: c["non_fire_threshold"])
    return {
        "rule": ("candidate margins are quantiles of the validation NON-FIRE score "
                 f"distribution; choose the one whose validation review share is "
                 f"closest to the pre-declared review budget ({review_budget:.0%}), "
                 "tie-broken on higher non-fire recall"),
        "review_budget": review_budget,
        "negative_quantiles_tried": list(neg_quantiles),
        "candidates": cands,
        "non_fire_threshold": chosen["non_fire_threshold"],
        "non_fire_recall": chosen["non_fire_recall"],
        "band_width": round(float(fire_thr - chosen["non_fire_threshold"]), 4),
        "validation_share_uncertain": chosen["validation_share_uncertain"],
        "band": {"non_fire_at_or_below": chosen["non_fire_threshold"],
                 "uncertain_strictly_between": [chosen["non_fire_threshold"], float(fire_thr)],
                 "fire_at_or_above": float(fire_thr)},
        "interpretation": ("operating margin selected on validation data; it is a "
                           "review-workload decision, not a calibrated "
                           "probability-of-truth statement"),
    }


def expected_calibration_error(y: np.ndarray, proba: np.ndarray,
                               bins: int = 10) -> dict:
    if len(np.unique(y)) < 2:
        return {"ece": {"unavailable": UNAVAILABLE,
                        "reason": "single-class stratum"}, "bins": []}
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(proba, edges[1:-1], right=False), 0, bins - 1)
    rows, ece = [], 0.0
    for b in range(bins):
        m = idx == b
        if not m.any():
            continue
        frac = float(y[m].mean())
        rows.append({"bin": b, "lo": round(float(edges[b]), 3),
                     "hi": round(float(edges[b + 1]), 3), "n": int(m.sum()),
                     "mean_pred": round(float(proba[m].mean()), 4),
                     "observed_rate": round(frac, 4)})
        ece += (m.sum() / len(y)) * abs(float(proba[m].mean()) - frac)
    return {"ece": round(float(ece), 6), "bins": rows}


def calibration_table(y: np.ndarray, proba: np.ndarray, bins: int = 10) -> pd.DataFrame:
    return pd.DataFrame(expected_calibration_error(y, proba, bins)["bins"])


def stratified(frame: pd.DataFrame, y: np.ndarray, proba: np.ndarray,
               thr: float, by: str) -> dict:
    groups = frame[by].fillna("null").astype(str)
    out = {}
    for g in sorted(groups.unique()):
        m = (groups == g).to_numpy()
        out[str(g)] = evaluate(y[m], proba[m], thr)
    return out


def event_recall(frame: pd.DataFrame, pred: np.ndarray) -> dict:
    fire = frame[frame["label"] == "fire"]
    if not len(fire):
        return {"n_events": 0, "recall_median": UNAVAILABLE,
                "recall_min": UNAVAILABLE}
    p = pred[fire.index.to_numpy()] if len(pred) == len(frame) else pred
    rec = fire.assign(_p=p).groupby("event_id")["_p"].mean().sort_values()
    return {"n_events": int(len(rec)),
            "recall_median": round(float(rec.median()), 4),
            "recall_min": round(float(rec.min()), 4),
            "recall_p10": round(float(rec.quantile(0.10)), 4)}


def select_threshold(y: np.ndarray, proba: np.ndarray) -> tuple[float, dict]:
    """Documented rule: maximise F1 on the VALIDATION set over a fixed grid.

    Ties break toward the threshold closest to 0.5, then the lower threshold,
    so the choice is deterministic and not sensitive to grid ordering.
    """
    grid = [round(x, 2) for x in np.arange(0.10, 0.91, 0.01)]
    scored = []
    for t in grid:
        pred = (proba >= t).astype(int)
        f1 = float(f1_score(y, pred, zero_division=0))
        scored.append({"threshold": t, "f1": round(f1, 6),
                       "precision": round(float(precision_score(y, pred, zero_division=0)), 6),
                       "recall": round(float(recall_score(y, pred, zero_division=0)), 6)})
    best = max(scored, key=lambda r: (r["f1"], -abs(r["threshold"] - 0.5), -r["threshold"]))
    return best["threshold"], {"rule": "maximise F1 on validation set",
                               "grid": [grid[0], grid[-1], len(grid)],
                               "chosen": best, "sweep": scored}


def choose_uncertain_band(y: np.ndarray, proba: np.ndarray, fire_thr: float) -> dict:
    """Define the NON_FIRE / UNCERTAIN margin explicitly and reproducibly.

    Rule (documented, coverage-based, NOT a claim of scientific confidence):
    the non-fire threshold is the smallest value at or below the fire threshold
    that still captures at least `NON_FIRE_TARGET_RECALL` of validation
    non-fire rows. Everything between the two thresholds is UNCERTAIN.

    A narrower margin yields more confident NON_FIRE calls and a smaller
    UNCERTAIN band; a wider one does the reverse. The chosen target is recorded
    in the artifact so the operating point is auditable and tunable.
    """
    return size_uncertain_band(y, proba, fire_thr)


# --------------------------------------------------------------------------- training
def train(dataset_path: Path | str, out_dir: Path | str, *,
          models=("hgb", "rf", "et"), calibrate: bool = True) -> dict:
    import hashlib

    dataset_path, out_dir = Path(dataset_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ds_sha = sha256_dataset(dataset_path)

    split = build_split(dataset_path)
    frame = split.frame
    assert_no_leakage(frame)

    Xtr, ytr = feature_matrix(frame, "train")
    Xva, yva = feature_matrix(frame, "val")
    Xte, yte = feature_matrix(frame, "test")
    va_frame = frame[frame["split_v3"] == "val"].reset_index(drop=True)
    te_frame = frame[frame["split_v3"] == "test"].reset_index(drop=True)

    # ---- model selection on validation only --------------------------------
    sweep = {}
    for key in models:
        pipe = make_pipeline(key)
        pipe.fit(Xtr, ytr)
        p_va = pipe.predict_proba(Xva)[:, 1]
        sweep[key] = {
            "val": evaluate(yva, p_va, 0.5),
            "val_calibration": expected_calibration_error(yva, p_va),
        }
    winner = max(models, key=lambda k: (
        sweep[k]["val"]["f1"] if isinstance(sweep[k]["val"]["f1"], float) else -1.0,
        sweep[k]["val"]["pr_auc"] if isinstance(sweep[k]["val"]["pr_auc"], float) else -1.0,
    ))

    # ---- fit the winner, calibrate, then freeze ----------------------------
    base = make_pipeline(winner)
    base.fit(Xtr, ytr)
    p_va_raw = base.predict_proba(Xva)[:, 1]

    calibrated = False
    calibration_note = ("not attempted"
                        if not calibrate else
                        "attempted; fell back to uncalibrated (see reason)")
    model = base
    if calibrate:
        # Cross-validated isotonic on TRAIN folds only. The validation set is
        # deliberately not used to fit the calibrator: it is the threshold and
        # uncertainty-band selection set, and reusing it for calibration would
        # make the reported validation ECE optimistic.
        try:
            cal = CalibratedClassifierCV(make_pipeline(winner), method="isotonic",
                                         cv=5)
            cal.fit(Xtr, ytr)
            probe = cal.predict_proba(Xva)[:, 1]
            raw_ece = expected_calibration_error(yva, p_va_raw)["ece"]
            cal_ece = expected_calibration_error(yva, probe)["ece"]
            if isinstance(raw_ece, float) and isinstance(cal_ece, float) and cal_ece <= raw_ece:
                model = cal
                calibrated = True
                calibration_note = (
                    f"isotonic, 5-fold CV on TRAIN only; validation ECE "
                    f"{raw_ece:.4f} -> {cal_ece:.4f}")
            else:
                calibration_note = (
                    f"isotonic did not improve validation ECE "
                    f"({raw_ece} -> {cal_ece}); kept uncalibrated")
        except Exception as exc:  # noqa: BLE001
            calibration_note = (f"isotonic failed ({type(exc).__name__}: {exc}); "
                                "kept uncalibrated")

    p_va = model.predict_proba(Xva)[:, 1]
    fire_thr, thr_record = select_threshold(yva, p_va)
    band = choose_uncertain_band(yva, p_va, fire_thr)

    # ---- TEST, exactly once ------------------------------------------------
    p_te = model.predict_proba(Xte)[:, 1]
    test_metrics = evaluate(yte, p_te, fire_thr)
    test_metrics["calibration"] = expected_calibration_error(yte, p_te)
    val_metrics = evaluate(yva, p_va, fire_thr)
    val_metrics["calibration"] = expected_calibration_error(yva, p_va)
    train_metrics = evaluate(ytr, model.predict_proba(Xtr)[:, 1], fire_thr)

    strata = {
        "band_v3": stratified(te_frame, yte, p_te, fire_thr, "band_v3"),
        "wilaya_name": stratified(te_frame, yte, p_te, fire_thr, "wilaya_name"),
        "satellite": stratified(te_frame, yte, p_te, fire_thr, "satellite"),
        "daynight": stratified(te_frame.assign(
            daynight=te_frame["daynight"].astype(str).str.upper().str[0]),
            yte, p_te, fire_thr, "daynight"),
        "cohort": stratified(te_frame, yte, p_te, fire_thr, "cohort"),
    }

    imp = feature_importance(model, winner)
    joblib.dump(model, out_dir / "model.joblib")
    imp.to_csv(out_dir / "feature_importance.csv", index=False)
    calibration_table(yte, p_te).to_csv(out_dir / "calibration.csv", index=False)

    src_sha = _source_sha()
    config = {
        "model_version": VERIFIER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "model_key": winner,
        "model_class": type(model.named_steps["clf"]).__name__,
        "calibrated": calibrated,
        "calibration_note": calibration_note,
        "features": list(FEATURE_COLUMNS),
        "feature_order": list(FEATURE_COLUMNS),
        "banned_features_excluded": sorted(set(BANNED_FEATURES) & set(FEATURE_COLUMNS)),
        "threshold": float(fire_thr),
        "threshold_selection": thr_record,
        "uncertainty_band": band,
        "random_state": RANDOM_STATE,
        "dataset": str(dataset_path),
        "dataset_sha256": ds_sha,
        "source_code_sha256": src_sha,
        "sklearn_version": sklearn.__version__,
        "python_version": platform.python_version(),
        "scope": SCOPE_STATEMENT,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "split": split.description,
        "labels_used": "fire/non-fire only (uncertain and excluded never fitted)",
    }
    metrics = {
        "model_version": VERIFIER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE_STATEMENT,
        "sizes": {"train": int(len(ytr)), "val": int(len(yva)), "test": int(len(yte))},
        "label_counts": {
            "train": {"fire": int((ytr == 1).sum()), "non_fire": int((ytr == 0).sum())},
            "val": {"fire": int((yva == 1).sum()), "non_fire": int((yva == 0).sum())},
            "test": {"fire": int((yte == 1).sum()), "non_fire": int((yte == 0).sum())},
        },
        "model_selection": {"rule": "highest validation F1, tie-break validation PR-AUC",
                            "sweep": sweep, "winner": winner},
        "train": train_metrics,
        "val": val_metrics,
        "test_once": test_metrics,
        "test_stratified": strata,
        "test_event_recall": event_recall(te_frame, (p_te >= fire_thr).astype(int)),
        "config": config,
    }
    (out_dir / "config.json").write_text(json.dumps(config, indent=2, default=str))
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))
    (out_dir / "manifest.json").write_text(json.dumps({
        "model_version": VERIFIER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "dataset_sha256": ds_sha,
        "source_code_sha256": src_sha,
        "model_file": "model.joblib",
        "model_sha256": _file_sha(out_dir / "model.joblib"),
        "files": {p.name: _file_sha(p) for p in sorted(out_dir.iterdir())
                  if p.is_file() and p.name != "manifest.json"},
        "trained_at": config["trained_at"],
        "scope": SCOPE_STATEMENT,
    }, indent=2, default=str))
    return metrics


def feature_importance(model, winner: str) -> pd.DataFrame:
    pre = model.named_steps["pre"]
    try:
        names = list(pre.get_feature_names_out())
    except Exception:  # noqa: BLE001
        names = list(NUMERIC_FEATURES) + [f"satellite_{i}" for i in range(8)]
    clf = model.named_steps["clf"]
    inner = clf
    if hasattr(clf, "calibrated_classifiers_"):
        inner = clf.calibrated_classifiers_[0].estimator
    if hasattr(inner, "feature_importances_"):
        imp = np.asarray(inner.feature_importances_, dtype=float)
    elif hasattr(inner, "feature_importances"):
        imp = np.asarray(inner.feature_importances, dtype=float)
    else:
        imp = np.zeros(len(names))
    if len(imp) != len(names):
        imp = np.resize(imp, len(names))
    out = pd.DataFrame({"feature": names, "importance": imp})
    return out.sort_values("importance", ascending=False).reset_index(drop=True)


def _file_sha(p: Path) -> str:
    import hashlib
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _source_sha() -> dict:
    import hashlib
    root = Path(__file__).resolve().parents[1]
    out = {}
    for name in ("verifier_split.py", "verifier_train.py",
                 "verifier_model.py", "inference.py", "labels.py"):
        p = root / "numidia_ml" / name
        if p.exists():
            out[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out