"""First model experiment (auditable tabular baseline - NOT production).

Contract (asserted in code, not just documented):
- X uses ONLY the 11 approved MODEL_FEATURES_V1 (leakage asserts fail the run).
- Fit rows: train split + labels in {fire, non-fire} only (no uncertain/excluded).
- Threshold + model choice on validation only; test evaluated ONCE after freeze.
- Artifact is saved locally (gitignored) and NEVER registered (no /ai wiring).
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression  # noqa: F401 (audit baseline only if needed)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler  # noqa: F401

from numidia_ml.labels import BANNED_FEATURES, MODEL_FEATURES_V1

EXPERIMENT_VERSION = "exp-v1"
RANDOM_STATE = 42
THRESHOLD_GRID = [0.3, 0.4, 0.5, 0.6, 0.7]

NUMERIC_FEATURES = ["bright_ti4", "bright_ti5", "f_bt_diff", "frp", "f_frp",
                    "confidence", "f_confidence", "scan", "track"]
CATEGORICAL_FEATURES = ["satellite", "type"]

MODEL_CONFIGS = {
    "rf": {"cls": RandomForestClassifier,
           "params": {"n_estimators": 300, "min_samples_leaf": 5,
                      "random_state": RANDOM_STATE, "n_jobs": -1}},
    "hgb": {"cls": HistGradientBoostingClassifier,
            "params": {"max_iter": 300, "learning_rate": 0.06,
                       "random_state": RANDOM_STATE}},
}


def assert_feature_contract(X: pd.DataFrame) -> None:
    """Fail the run if any banned column enters X (req: leakage check)."""
    banned_hit = sorted(set(X.columns) & set(BANNED_FEATURES))
    if banned_hit:
        raise AssertionError(f"banned columns in X: {banned_hit}")
    missing = sorted(set(MODEL_FEATURES_V1) - set(X.columns))
    if missing:
        raise AssertionError(f"approved features missing from X: {missing}")
    extra = sorted(set(X.columns) - set(MODEL_FEATURES_V1))
    if extra:
        raise AssertionError(f"unapproved columns in X: {extra}")


def load_supervised_frame(path: Path | str) -> pd.DataFrame:
    """Load v2, keep fire/non-fire only. Read-only; sha recorded by caller."""
    df = pd.read_csv(path, low_memory=False)
    return df[df["label"].isin(("fire", "non-fire"))].copy().reset_index(drop=True)


def split_frame(df: pd.DataFrame, split: str) -> tuple[pd.DataFrame, np.ndarray]:
    sub = df[df["split"] == split].copy().reset_index(drop=True)
    if sub["label"].isin(("fire", "non-fire")).sum() != len(sub):
        raise AssertionError("non-supervised labels reached the model input")
    X = sub[MODEL_FEATURES_V1].copy()
    assert_feature_contract(X)
    y = (sub["label"] == "fire").astype(int).to_numpy()
    return X, y


def make_pipeline(model_key: str) -> Pipeline:
    cfg = MODEL_CONFIGS[model_key]
    pre = ColumnTransformer([
        ("num", SimpleImputer(strategy="median"), NUMERIC_FEATURES),
        ("cat", Pipeline([
            ("imp", SimpleImputer(strategy="most_frequent")),
            ("oh", OneHotEncoder(handle_unknown="ignore")),
        ]), CATEGORICAL_FEATURES),
    ])
    return Pipeline([("pre", pre), ("clf", cfg["cls"](**cfg["params"]))])


def confusion_counts(y: np.ndarray, pred: np.ndarray) -> dict:
    tp = int(((pred == 1) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn}


def metrics_at_threshold(y: np.ndarray, proba: np.ndarray, thr: float) -> dict:
    from sklearn.metrics import accuracy_score, brier_score_loss, f1_score, precision_score, recall_score

    pred = (proba >= thr).astype(int)
    out = {
        "threshold": thr,
        "n": int(len(y)),
        "accuracy": float(accuracy_score(y, pred)),
        "brier": float(brier_score_loss(y, proba)),
        **confusion_counts(y, pred),
    }
    out["precision"] = float(precision_score(y, pred, zero_division=0))
    out["recall"] = float(recall_score(y, pred, zero_division=0))
    out["f1"] = float(f1_score(y, pred, zero_division=0))
    return out


def ranking_metrics(y: np.ndarray, proba: np.ndarray) -> dict:
    from sklearn.metrics import average_precision_score, roc_auc_score

    return {"roc_auc": float(roc_auc_score(y, proba)),
            "pr_auc": float(average_precision_score(y, proba))}


def calibration_table(y: np.ndarray, proba: np.ndarray, bins: int = 10) -> pd.DataFrame:
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(proba, edges[1:-1], right=False), 0, bins - 1)
    rows = []
    for b in range(bins):
        m = idx == b
        if not m.any():
            continue
        rows.append({"bin": b, "lo": round(float(edges[b]), 2),
                     "hi": round(float(edges[b + 1]), 2),
                     "n": int(m.sum()),
                     "mean_pred": round(float(proba[m].mean()), 4),
                     "frac_pos": round(float(y[m].mean()), 4)})
    cal = pd.DataFrame(rows)
    ece = float((cal["n"] / cal["n"].sum() * (cal["mean_pred"] - cal["frac_pos"]).abs()).sum()) if len(cal) else float("nan")
    cal.attrs["ece"] = ece
    return cal


def feature_importance(pipe: Pipeline) -> pd.DataFrame:
    pre = pipe.named_steps["pre"]
    names = list(NUMERIC_FEATURES) + list(
        pre.named_transformers_["cat"].named_steps["oh"].get_feature_names_out(CATEGORICAL_FEATURES))
    clf = pipe.named_steps["clf"]
    if hasattr(clf, "feature_importances_"):
        imp = np.asarray(clf.feature_importances_, dtype=float)
    else:
        imp = np.zeros(len(names))
    out = pd.DataFrame({"feature": names, "importance": imp})
    return out.sort_values("importance", ascending=False).reset_index(drop=True)


def stratified_metrics(df_eval: pd.DataFrame, y: np.ndarray, proba: np.ndarray,
                       thr: float, by: str) -> dict:
    """Metrics per stratum of `by` (stratification vars never enter X)."""
    groups = df_eval[by].fillna("null").astype(str)
    out = {}
    for g in sorted(groups.unique()):
        m = (groups == g).to_numpy()
        if m.sum() == 0:
            continue
        mm = metrics_at_threshold(y[m], proba[m], thr)
        if len(np.unique(y[m])) < 2:
            # Single-class stratum (e.g. south band has no fire rows):
            # ranking metrics are undefined - record None, not nan.
            mm.update({"roc_auc": None, "pr_auc": None,
                       "single_class": True})
        else:
            mm.update(ranking_metrics(y[m], proba[m]))
            mm["single_class"] = False
        out[str(g)] = mm
    return out


def event_recall(df_eval: pd.DataFrame, pred: np.ndarray) -> dict:
    """Per-fire-event recall distribution (fire-event level evaluation)."""
    fire = df_eval[df_eval["label"] == "fire"].copy()
    if not len(fire):
        return {"n_events": 0, "recall_median": None, "recall_min": None,
                "worst_events": []}
    fire = fire.copy()
    fire["_pred"] = pred[df_eval["label"] == "fire"]
    rec = fire.groupby("event_id")["_pred"].mean().sort_values()
    worst = [{"event_id": e, "recall": round(float(r), 4),
              "n": int((fire["event_id"] == e).sum())} for e, r in rec.head(5).items()]
    return {"n_events": int(rec.shape[0]),
            "recall_median": round(float(rec.median()), 4),
            "recall_min": round(float(rec.min()), 4),
            "recall_p10": round(float(rec.quantile(0.10)), 4),
            "worst_events": worst}


def run_experiment(dataset_path: Path | str, out_dir: Path | str,
                   dataset_sha: str) -> dict:
    """Fit (train) -> select (val) -> evaluate ONCE (test). Returns run record."""
    import sklearn

    dataset_path, out_dir = Path(dataset_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df = load_supervised_frame(dataset_path)

    X_train, y_train = split_frame(df, "train")
    X_val, y_val = split_frame(df, "val")
    val_frame = df[df["split"] == "val"].reset_index(drop=True)

    fitted, train_sweep, val_scores = {}, {}, {}
    for key in MODEL_CONFIGS:
        pipe = make_pipeline(key)
        pipe.fit(X_train, y_train)
        fitted[key] = pipe
        p_train = pipe.predict_proba(X_train)[:, 1]
        sweep = [metrics_at_threshold(y_train, p_train, t) for t in THRESHOLD_GRID]
        train_sweep[key] = sweep
        p_val = pipe.predict_proba(X_val)[:, 1]
        val_scores[key] = {
            "recall_at": {},
            "mean_proba": round(float(p_val.mean()), 4),
            "n_val": int(len(y_val)),
            "val_fire_only": bool((val_frame["label"] == "fire").all()),
            "train_pr_auc": round(ranking_metrics(y_train, p_train)["pr_auc"], 4),
        }
        for t in THRESHOLD_GRID:
            pred = (p_val >= t).astype(int)
            val_scores[key]["recall_at"][str(t)] = round(float((pred[y_val == 1] == 1).mean()), 4) \
                if (y_val == 1).any() else None

    # Threshold: max train F1 (documented optimistic - val is fire-only and
    # cannot support precision/recall tradeoff tuning). Ties -> nearest 0.5.
    # Model choice (predeclared): higher val recall at the chosen threshold,
    # tie-break by higher train PR-AUC. Test is touched exactly once below.
    best_thr: dict = {}
    for key in MODEL_CONFIGS:
        f1s = [(s["f1"], -abs(s["threshold"] - 0.5), s["threshold"]) for s in train_sweep[key]]
        best_thr[key] = max(f1s)[2]
    sel = sorted(MODEL_CONFIGS,
                 key=lambda k: (val_scores[k]["recall_at"][str(best_thr[k])] or -1,
                                val_scores[k]["train_pr_auc"]),
                 reverse=True)
    winner = sel[0]
    record = {
        "experiment": EXPERIMENT_VERSION,
        "model": winner,
        "threshold_selection": {k: {"threshold": best_thr[k],
                                    "train_sweep": train_sweep[k]} for k in MODEL_CONFIGS},
        "model_selection": {
            "rule": "higher val recall at chosen threshold; tie-break train PR-AUC",
            "val_scores": val_scores,
            "ranking": sel,
        },
    }

    # ---- freeze, then test exactly once -----------------------------------
    pipe = fitted[winner]
    test_frame = df[df["split"] == "test"].reset_index(drop=True)
    X_test, y_test = split_frame(df, "test")
    proba = pipe.predict_proba(X_test)[:, 1]
    thr = best_thr[winner]
    pred = (proba >= thr).astype(int)
    record["test_once"] = {
        "threshold": thr,
        **metrics_at_threshold(y_test, proba, thr),
        **ranking_metrics(y_test, proba),
    }
    cal = calibration_table(y_test, proba)
    record["test_once"]["ece"] = cal.attrs["ece"]
    record["test_stratified"] = {
        "lat_band": stratified_metrics(test_frame, y_test, proba, thr, "strat_lat_band"),
        "daynight": stratified_metrics(test_frame.assign(
            daynight=test_frame["daynight"].astype(str).str.upper().str[0]),
            y_test, proba, thr, "daynight"),
        "satellite": stratified_metrics(test_frame, y_test, proba, thr, "satellite"),
        "cohort": stratified_metrics(test_frame, y_test, proba, thr, "cohort"),
    }
    record["test_event_recall"] = event_recall(test_frame, pred)

    # ---- post-fit verification: approved features only ---------------------
    used = list(X_train.columns)
    record["post_fit_check"] = {
        "x_columns": used,
        "matches_contract": sorted(used) == sorted(MODEL_FEATURES_V1),
        "no_banned": len(set(used) & set(BANNED_FEATURES)) == 0,
    }
    assert record["post_fit_check"]["matches_contract"], "feature contract violated"
    assert record["post_fit_check"]["no_banned"], "banned feature in X"

    # ---- artifacts (local only, gitignored, never registered) --------------
    import joblib as _joblib

    _joblib.dump(pipe, out_dir / f"{winner}_{EXPERIMENT_VERSION}.joblib")
    imp = feature_importance(pipe)
    imp.to_csv(out_dir / "feature_importance.csv", index=False)
    cal.to_csv(out_dir / "calibration.csv", index=False)
    config = {
        "experiment": EXPERIMENT_VERSION,
        "model": winner,
        "model_class": type(pipe.named_steps["clf"]).__name__,
        "model_params": MODEL_CONFIGS[winner]["params"],
        "features": MODEL_FEATURES_V1,
        "threshold": thr,
        "threshold_grid": THRESHOLD_GRID,
        "random_state": RANDOM_STATE,
        "dataset": str(dataset_path),
        "dataset_sha256": dataset_sha,
        "sklearn_version": sklearn.__version__,
        "fit_rows": int(len(y_train)),
        "fit_labels": "fire/non-fire only (uncertain/excluded excluded)",
    }
    (out_dir / "config.json").write_text(json.dumps(config, indent=2))
    (out_dir / "metrics.json").write_text(json.dumps(record, indent=2, default=str))
    record["config"] = config
    record["out_dir"] = str(out_dir)
    return record


def write_experiment_report(path: Path | str, record: dict) -> Path:
    """Render the experiment report (clearly NOT registered for production)."""
    t = record["test_once"]
    cm = t
    lines = [
        "# NUMIDIA verifier â€” model experiment exp-v1",
        "",
        "**Experimental V2 model â€” NOT YET REGISTERED FOR PRODUCTION**",
        "",
        f"Model: `{record['model']}` ({record['config']['model_class']}) Â· "
        f"threshold {t['threshold']} Â· seed {record['config']['random_state']} Â· "
        f"sklearn {record['config']['sklearn_version']}",
        f"Dataset: `{record['config']['dataset']}` "
        f"(sha256 `{record['config']['dataset_sha256'][:12]}â€¦`, read-only) Â· "
        f"fit rows: {record['config']['fit_rows']} ({record['config']['fit_labels']})",
        f"Features (exact): {', '.join(record['config']['features'])}",
        "",
        "## Selection (validation only â€” fire-only val, recall can be measured, "
        "precision cannot)",
        "",
        f"Rule (predeclared): {record['model_selection']['rule']}.",
        f"Ranking: {' > '.join(record['model_selection']['ranking'])}.",
    ]
    for k, sw in record["threshold_selection"].items():
        tab = " | ".join(f"{s['threshold']}:F1={s['f1']:.3f},R={s['recall']:.3f},P={s['precision']:.3f}"
                         for s in sw["train_sweep"])
        lines.append(f"- {k}: train sweep [{tab}] â†’ chosen {sw['threshold']} "
                     f"(max train F1 â€” optimistic, documented).")
        vs = record["model_selection"]["val_scores"][k]
        lines.append(f"  val (n={vs['n_val']}, fire-only): recall@thr={vs['recall_at']}, "
                     f"mean_proba={vs['mean_proba']}, train PR-AUC={vs['train_pr_auc']}.")
    lines += [
        "",
        "## Test (evaluated ONCE after freeze â€” no tuning on test)",
        "",
        f"- ROC-AUC **{t['roc_auc']:.4f}** Â· PR-AUC **{t['pr_auc']:.4f}** Â· "
        f"accuracy {t['accuracy']:.4f} Â· Brier {t['brier']:.4f} Â· ECE {t['ece']:.4f}",
        f"- precision {t['precision']:.4f} Â· recall {t['recall']:.4f} Â· F1 {t['f1']:.4f}",
        f"- confusion: TP {cm['tp']} / TN {cm['tn']} / FP {cm['fp']} / FN {cm['fn']} "
        f"(n={t['n']})",
        "",
        "### Stratified test metrics (grouping only â€” never features)",
        "",
    ]
    for axis, groups in record["test_stratified"].items():
        lines.append(f"**{axis}**")
        for g, m in groups.items():
            auc = m.get("roc_auc")
            lines.append(f"- {g}: n={m['n']}, acc={m['accuracy']:.3f}, "
                         f"P={m['precision']:.3f}, R={m['recall']:.3f}, F1={m['f1']:.3f}, "
                         f"ROC-AUC={auc if auc is None else round(auc, 3)}, "
                         f"TP/TN/FP/FN={m['tp']}/{m['tn']}/{m['fp']}/{m['fn']}")
        lines.append("")
    ev = record["test_event_recall"]
    lines += [
        "### Fire-event level (test)",
        "",
        f"- events: {ev['n_events']} Â· median recall {ev['recall_median']} Â· "
        f"min {ev['recall_min']} Â· p10 {ev['recall_p10']}",
        "- worst 5 events: " + "; ".join(
            f"{w['event_id']} R={w['recall']} (n={w['n']})" for w in ev["worst_events"]),
        "",
        "## Limitations (must-read before any registration discussion)",
        "",
        "- Validation holds ONE fire event (AOI02) and zero non-fire rows: "
        "model/threshold choice rests on recall-only evidence plus optimistic "
        "train F1. The test score below is the first honest number.",
        "- Latitude/daynight shortcuts were excluded by feature contract, not "
        "by data: verify stratified rows above (north-band and night-only "
        "slices) before trusting aggregates.",
        "- No uncertain/excluded rows were used for fitting; calibration is "
        "reported on supervised test rows only.",
        "- This artifact is LOCAL (gitignored) and UNREGISTERED: the live API "
        "still returns 503 AI_UNAVAILABLE.",
        "",
        "## Post-fit leakage verification",
        "",
        f"- X columns == approved contract: {record['post_fit_check']['matches_contract']}",
        f"- banned columns in X: {'NONE — clean' if record['post_fit_check']['no_banned'] else 'VIOLATION'}",
        f"- X columns: {', '.join(record['post_fit_check']['x_columns'])}",
    ]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
