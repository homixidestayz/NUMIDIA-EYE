"""Candidate-artifact verification (read-only check, NOT registration).

Replays the recorded test split through a saved pipeline and compares the
recomputed metrics with the artifact's own metrics.json. Used when bringing
a cloud-trained artifact back into the project: a candidate is only *eligible*
for review after this passes, and registration additionally requires explicit
approval (the live API stays 503 until then).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import numpy as np

from numidia_ml.experiment import (
    metrics_at_threshold,
    ranking_metrics,
    split_frame,
)
from numidia_ml.labels import BANNED_FEATURES, MODEL_FEATURES_V1

COMPARE_METRICS = ("roc_auc", "pr_auc", "accuracy", "precision", "recall", "f1", "brier")


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_artifact(artifact_path: Path | str, dataset_path: Path | str,
                    metrics_path: Path | str | None = None,
                    tol: float = 1e-4) -> dict:
    """Return {'pass': bool, 'checks': [...]}. Never writes, never registers."""
    checks: list[dict] = []

    def _check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    artifact_path, dataset_path = Path(artifact_path), Path(dataset_path)
    if not artifact_path.exists():
        return {"pass": False, "checks": [{"check": "artifact exists", "ok": False,
                                           "detail": str(artifact_path)}]}
    if not dataset_path.exists():
        return {"pass": False, "checks": [{"check": "dataset exists", "ok": False,
                                           "detail": str(dataset_path)}]}

    ds_sha = sha256_file(dataset_path)
    pipe = joblib.load(artifact_path)

    names_in = getattr(pipe, "feature_names_in_", None)
    if names_in is None:
        _check("pipeline exposes feature_names_in_", False, "cannot audit nameless pipeline")
        return {"pass": False, "checks": checks}
    names_in = list(names_in)
    _check("artifact features == approved contract", sorted(names_in) == sorted(MODEL_FEATURES_V1),
           f"got: {names_in}")
    _check("no banned columns in artifact", len(set(names_in) & set(BANNED_FEATURES)) == 0,
           f"overlap: {sorted(set(names_in) & set(BANNED_FEATURES))}")

    import pandas as pd

    df = pd.read_csv(dataset_path, low_memory=False)
    df = df[df["label"].isin(("fire", "non-fire"))].reset_index(drop=True)
    try:
        X_test, y_test = split_frame(df, "test")
    except AssertionError as exc:
        _check("test split passes feature contract", False, str(exc))
        return {"pass": False, "checks": checks}
    _check("test split passes feature contract", True, f"n_test={len(y_test)}")

    recorded: dict | None = None
    if metrics_path is not None:
        metrics_path = Path(metrics_path)
        if metrics_path.exists():
            recorded = json.loads(metrics_path.read_text(encoding="utf-8"))
            rec = recorded.get("test_once", recorded)
            _check("metrics.json present", True, str(metrics_path))
            thr = rec.get("threshold", 0.5)
            if "dataset_sha256" in recorded.get("config", recorded):
                want = recorded.get("config", recorded)["dataset_sha256"]
                _check("dataset sha matches recorded sha", want == ds_sha,
                       f"recorded {str(want)[:12]}… vs actual {ds_sha[:12]}…")
        else:
            _check("metrics.json present", False, str(metrics_path))
    thr = float(recorded.get("test_once", recorded or {}).get("threshold", 0.5)) if recorded else 0.5

    proba = np.asarray(pipe.predict_proba(X_test)[:, 1])
    recomputed = {**metrics_at_threshold(y_test, proba, thr), **ranking_metrics(y_test, proba)}
    if recorded is not None:
        rec = recorded.get("test_once", recorded)
        mismatches = []
        for m in COMPARE_METRICS:
            if m in rec and rec[m] is not None:
                if abs(float(recomputed[m]) - float(rec[m])) > tol:
                    mismatches.append(f"{m}: recorded {rec[m]} vs recomputed {recomputed[m]:.6f}")
        _check(f"recomputed test metrics match (tol={tol})", not mismatches,
               "; ".join(mismatches) if mismatches else f"threshold={thr}")
    else:
        _check("recomputed test metrics (no recorded baseline to compare)", True,
               f"roc_auc={recomputed['roc_auc']:.4f} f1={recomputed['f1']:.4f} threshold={thr}")

    ok = all(c["ok"] for c in checks)
    return {"pass": ok, "checks": checks, "dataset_sha256": ds_sha,
            "threshold": thr, "recomputed": {k: recomputed[k] for k in COMPARE_METRICS}}
