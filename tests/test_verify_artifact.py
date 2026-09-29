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


def _recorded_metrics(df, pipe, thr=0.5, dataset_sha=None) -> dict:
    from numidia_ml.experiment import metrics_at_threshold, ranking_metrics, split_frame

    X_test, y_test = split_frame(df, "test")
    proba = np.asarray(pipe.predict_proba(X_test)[:, 1])
    return {"test_once": {**metrics_at_threshold(y_test, proba, thr),
                          **ranking_metrics(y_test, proba)},
            "config": {} if dataset_sha is None else {"dataset_sha256": dataset_sha}}


def test_verify_passes_on_matching_bundle(tmp_path):
    df = _frame()
    ds = tmp_path / "mini.csv"
    df.to_csv(ds, index=False)
    art = tmp_path / "pipe.joblib"
    pipe = _fit_small(df, art)
    met = tmp_path / "metrics.json"
    met.write_text(json.dumps(_recorded_metrics(df, pipe, dataset_sha=V.sha256_dataset(ds))))
    result = V.verify_artifact(art, ds, met)
    assert result["pass"] is True, result["checks"]
    assert result["dataset_sha256"] == V.sha256_dataset(ds)


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


# --- dataset-SHA provenance gate -------------------------------------------------
# Regression cover for an inert gate: the SHA check used to be wrapped in
# `if "dataset_sha256" in ...`, so a bundle without one skipped the check
# entirely and still reported pass. Absence must now FAIL.


def test_verify_fails_when_metrics_bundle_omits_dataset_sha(tmp_path):
    """The exact regression: no recorded SHA must fail, not silently skip."""
    df = _frame()
    ds = tmp_path / "mini.csv"
    df.to_csv(ds, index=False)
    art = tmp_path / "pipe.joblib"
    pipe = _fit_small(df, art)
    met = tmp_path / "metrics.json"
    met.write_text(json.dumps(_recorded_metrics(df, pipe, dataset_sha=None)))

    result = V.verify_artifact(art, ds, met)
    assert result["pass"] is False
    assert any(c["check"] == "dataset sha recorded in metrics bundle" and not c["ok"]
               for c in result["checks"])


def test_verify_fails_on_dataset_sha_mismatch(tmp_path):
    df = _frame()
    ds = tmp_path / "mini.csv"
    df.to_csv(ds, index=False)
    art = tmp_path / "pipe.joblib"
    pipe = _fit_small(df, art)
    met = tmp_path / "metrics.json"
    met.write_text(json.dumps(_recorded_metrics(df, pipe, dataset_sha="0" * 64)))

    result = V.verify_artifact(art, ds, met)
    assert result["pass"] is False
    assert any(c["check"] == "dataset sha matches recorded sha" and not c["ok"]
               for c in result["checks"])


def test_verify_enforces_manifest_expected_sha(tmp_path):
    """An out-of-band authority (manifest) overrides a self-consistent bundle."""
    df = _frame()
    ds = tmp_path / "mini.csv"
    df.to_csv(ds, index=False)
    art = tmp_path / "pipe.joblib"
    pipe = _fit_small(df, art)
    met = tmp_path / "metrics.json"
    real = V.sha256_dataset(ds)
    met.write_text(json.dumps(_recorded_metrics(df, pipe, dataset_sha=real)))

    # Self-consistent artifact, but the manifest disagrees -> must fail.
    bad = V.verify_artifact(art, ds, met, expected_sha="1" * 64)
    assert bad["pass"] is False
    assert any(c["check"] == "dataset sha matches manifest" and not c["ok"]
               for c in bad["checks"])

    good = V.verify_artifact(art, ds, met, expected_sha=real)
    assert good["pass"] is True, good["checks"]


def test_sha256_dataset_is_line_ending_independent(tmp_path):
    """Platform stability: CRLF and LF copies of the same rows hash equally."""
    crlf = tmp_path / "crlf.csv"
    lf = tmp_path / "lf.csv"
    lf.write_bytes(b"a,b\n1,2\n3,4\n")
    crlf.write_bytes(b"a,b\r\n1,2\r\n3,4\r\n")
    assert V.sha256_dataset(crlf) == V.sha256_dataset(lf)
    # ...and deliberately differs from the raw-bytes hash, which is what
    # made the exp-v1 provenance platform-dependent.
    assert V.sha256_file(crlf) != V.sha256_file(lf)


def test_verify_dataset_passes_against_matching_manifest(tmp_path):
    ds = tmp_path / "ds.csv"
    ds.write_bytes(b"a,b\n1,2\n")
    man = tmp_path / "manifest.json"
    man.write_text(json.dumps({"dataset_version": "v9",
                               "dataset_sha256": V.sha256_dataset(ds)}))
    result = V.verify_dataset(ds, man)
    assert result["pass"] is True, result["checks"]
    assert result["dataset_version"] == "v9"


def test_verify_dataset_fails_on_tampered_dataset(tmp_path):
    ds = tmp_path / "ds.csv"
    ds.write_bytes(b"a,b\n1,2\n")
    man = tmp_path / "manifest.json"
    man.write_text(json.dumps({"dataset_version": "v9",
                               "dataset_sha256": V.sha256_dataset(ds)}))
    ds.write_bytes(b"a,b\n1,2\n3,4\n")  # one row injected
    result = V.verify_dataset(ds, man)
    assert result["pass"] is False
    assert any(c["check"] == "dataset sha matches manifest" and not c["ok"]
               for c in result["checks"])


def test_verify_dataset_fails_when_manifest_has_no_sha(tmp_path):
    ds = tmp_path / "ds.csv"
    ds.write_bytes(b"a,b\n1,2\n")
    man = tmp_path / "manifest.json"
    man.write_text(json.dumps({"dataset_version": "v9"}))
    result = V.verify_dataset(ds, man)
    assert result["pass"] is False
    assert any(c["check"] == "manifest records a dataset_sha256" and not c["ok"]
               for c in result["checks"])


def test_committed_dataset_matches_committed_manifest():
    """The real gate CI runs: committed dataset vs committed manifest."""
    from numidia_ml.cli import DEFAULT_OUT

    result = V.verify_dataset(DEFAULT_OUT / "firms_labels_v2.csv",
                              DEFAULT_OUT / "manifest_v2.json")
    assert result["pass"] is True, result["checks"]


# --- fail-closed provenance (R2 bypass) -----------------------------------------
# verify_artifact(artifact, dataset) with no metrics bundle used to run NO
# dataset SHA check at all and still returned pass=True. A missing input is
# unverifiable, not "all checks passed".

def test_verify_refuses_to_pass_without_any_provenance_authority(tmp_path):
    """The exact R2 bypass: no metrics bundle, no expected_sha."""
    df = _frame()
    ds = tmp_path / "mini.csv"
    df.to_csv(ds, index=False)
    art = tmp_path / "pipe.joblib"
    _fit_small(df, art)

    result = V.verify_artifact(art, ds)  # metrics_path omitted entirely
    assert result["pass"] is False, result["checks"]
    assert not any(c["check"] == "dataset sha matches recorded sha" and c["ok"]
                   for c in result["checks"]), "no bundle means no comparison happened"
    assert any(c["check"] == "dataset sha verified against an authority" and not c["ok"]
               for c in result["checks"])


def test_verify_fails_when_metrics_path_does_not_exist(tmp_path):
    """A missing metrics file must not be read as 'all artifact checks passed'."""
    df = _frame()
    ds = tmp_path / "mini.csv"
    df.to_csv(ds, index=False)
    art = tmp_path / "pipe.joblib"
    _fit_small(df, art)

    result = V.verify_artifact(art, ds, tmp_path / "no-such-metrics.json")
    assert result["pass"] is False
    assert any(c["check"] == "metrics.json present" and not c["ok"] for c in result["checks"])
    assert any(c["check"] == "dataset sha verified against an authority" and not c["ok"]
               for c in result["checks"])


def test_expected_sha_alone_satisfies_the_provenance_gate(tmp_path):
    """expected_sha is a sufficient authority on its own."""
    df = _frame()
    ds = tmp_path / "mini.csv"
    df.to_csv(ds, index=False)
    art = tmp_path / "pipe.joblib"
    _fit_small(df, art)

    result = V.verify_artifact(art, ds, expected_sha=V.sha256_dataset(ds))
    assert result["pass"] is True, result["checks"]
    assert any(c["check"] == "dataset sha verified against an authority" and c["ok"]
               for c in result["checks"])


def test_matching_bundle_satisfies_the_provenance_gate(tmp_path):
    """A bundle carrying the right SHA is also a sufficient authority."""
    df = _frame()
    ds = tmp_path / "mini.csv"
    df.to_csv(ds, index=False)
    art = tmp_path / "pipe.joblib"
    pipe = _fit_small(df, art)
    met = tmp_path / "metrics.json"
    met.write_text(json.dumps(_recorded_metrics(df, pipe, dataset_sha=V.sha256_dataset(ds))))

    result = V.verify_artifact(art, ds, met)
    assert result["pass"] is True, result["checks"]
    assert any(c["check"] == "dataset sha verified against an authority" and c["ok"]
               for c in result["checks"])
