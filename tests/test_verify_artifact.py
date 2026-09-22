"""verify-artifact tests - synthetic pipelines only (fast, offline)."""
from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd

from numidia_ml import verify_artifact as V


def _frame(n_per_class: int = 24, seed: int = 3) -> pd.DataFrame:
    """Balanced synthetic frame: every split holds both classes.

    (An earlier revision cycled splits per-row, leaving some splits
    single-class and the ranking metrics undefined. This version pairs
    fire/non-fire rows onto the same split cycle.)
    """
    from numidia_ml.labels import MODEL_FEATURES_V1

    rng = np.random.default_rng(seed)
    splits = ["train", "train", "train", "train", "val", "test"]
    rows = []
    for i in range(n_per_class):
        split = splits[i % len(splits)]
        rows.append({
            "bright_ti4": 345.0 + rng.normal(0, 3),
            "bright_ti5": 306.0 + rng.normal(0, 2),
            "f_bt_diff": 39.0 + rng.normal(0, 2),
            "frp": 12.0 + abs(rng.normal(0, 2)),
            "f_frp": 12.0 + abs(rng.normal(0, 2)),
            "confidence": 0.8, "f_confidence": 0.8,
            "scan": 0.4, "track": 0.4,
            "satellite": "N21", "type": "0",
            "label": "fire", "split": split,
        })
        rows.append({
            "bright_ti4": 315.0 + rng.normal(0, 3),
            "bright_ti5": 296.0 + rng.normal(0, 2),
            "f_bt_diff": 19.0 + rng.normal(0, 2),
            "frp": 2.0 + abs(rng.normal(0, 1)),
            "f_frp": 2.0 + abs(rng.normal(0, 1)),
            "confidence": 0.6, "f_confidence": 0.6,
            "scan": 0.4, "track": 0.4,
            "satellite": "N", "type": "0",
            "label": "non-fire", "split": split,
        })
    df = pd.DataFrame(rows)
    assert set(MODEL_FEATURES_V1) <= set(df.columns)
    for s in ("train", "val", "test"):
        assert set(df.loc[df["split"] == s, "label"].unique()) == {"fire", "non-fire"}, s
    return df


def _fit_small(df: pd.DataFrame, out, monkeypatch=None):
    """Fit via the REAL make_pipeline (same preprocessing as production).

    Small-model override must be applied by the caller with monkeypatch on
    E.MODEL_CONFIGS before calling (keeps the artifact shape faithful).
    """
    from numidia_ml.experiment import CATEGORICAL_FEATURES, NUMERIC_FEATURES, make_pipeline

    tr = df[df["split"] == "train"]
    X = tr[[c for c in NUMERIC_FEATURES + CATEGORICAL_FEATURES]]
    y = (tr["label"] == "fire").astype(int).to_numpy()
    pipe = make_pipeline("rf")
    pipe.fit(X, y)
    joblib.dump(pipe, out)
    return pipe


def _recorded_metrics(df, pipe, thr=0.5) -> dict:
    from numidia_ml.experiment import metrics_at_threshold, ranking_metrics, split_frame

    X_test, y_test = split_frame(df, "test")
    proba = np.asarray(pipe.predict_proba(X_test)[:, 1])
    return {"test_once": {**metrics_at_threshold(y_test, proba, thr),
                          **ranking_metrics(y_test, proba)},
            "config": {}}


def test_verify_passes_on_matching_bundle(tmp_path):
    df = _frame()
    ds = tmp_path / "mini.csv"
    df.to_csv(ds, index=False)
    art = tmp_path / "pipe.joblib"
    pipe = _fit_small(df, art)
    met = tmp_path / "metrics.json"
    met.write_text(json.dumps(_recorded_metrics(df, pipe)))
    result = V.verify_artifact(art, ds, met)
    assert result["pass"] is True, result["checks"]
    assert result["dataset_sha256"] == V.sha256_file(ds)


def test_verify_fails_on_tampered_metrics(tmp_path):
    df = _frame()
    ds = tmp_path / "mini.csv"
    df.to_csv(ds, index=False)
    art = tmp_path / "pipe.joblib"
    pipe = _fit_small(df, art)
    rec = _recorded_metrics(df, pipe)
    rec["test_once"]["roc_auc"] = 0.1234  # tampered
    met = tmp_path / "metrics.json"
    met.write_text(json.dumps(rec))
    result = V.verify_artifact(art, ds, met)
    assert result["pass"] is False
    assert any("match" in c["check"] and not c["ok"] for c in result["checks"])


def test_verify_fails_without_artifact_or_dataset(tmp_path):
    df = _frame()
    ds = tmp_path / "mini.csv"
    df.to_csv(ds, index=False)
    assert V.verify_artifact(tmp_path / "nope.joblib", ds)["pass"] is False
    assert V.verify_artifact(tmp_path / "nope.joblib", tmp_path / "nope.csv")["pass"] is False
