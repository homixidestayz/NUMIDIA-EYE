"""Experiment-pipeline tests - synthetic frames only (fast, offline)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from numidia_ml import experiment as E
from numidia_ml.labels import BANNED_FEATURES, MODEL_FEATURES_V1


def _frame(n_per: int = 30, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    fire, non = [], []
    for i in range(n_per):
        fire.append({"bright_ti4": 340 + rng.normal(0, 8),
                     "bright_ti5": 305 + rng.normal(0, 5),
                     "f_bt_diff": 35 + rng.normal(0, 5),
                     "frp": 12 + abs(rng.normal(0, 6)),
                     "f_frp": 12 + abs(rng.normal(0, 6)),
                     "confidence": 0.8, "f_confidence": 0.8,
                     "scan": 0.4, "track": 0.4,
                     "satellite": "N21", "type": "0",
                     "label": "fire",
                     "split": ["train", "train", "val", "test"][i % 4],
                     "event_id": f"EV-F{i % 3}", "strat_lat_band": "north",
                     "daynight": "D", "cohort": "2026",
                     "acq_datetime": "2026-09-01T01:00:00Z"})
        non.append({"bright_ti4": 315 + rng.normal(0, 8),
                    "bright_ti5": 296 + rng.normal(0, 3),
                    "f_bt_diff": 19 + rng.normal(0, 4),
                    "frp": 2 + abs(rng.normal(0, 1.5)),
                    "f_frp": 2 + abs(rng.normal(0, 1.5)),
                    "confidence": 0.6, "f_confidence": 0.6,
                    "scan": 0.4, "track": 0.4,
                    "satellite": "N", "type": "0",
                    "label": "non-fire",
                    "split": ["train", "train", "val", "test"][i % 4],
                    "event_id": f"FLARE-{i % 3}", "strat_lat_band": "south",
                    "daynight": "N", "cohort": "2026",
                    "acq_datetime": "2026-09-01T01:00:00Z"})
    return pd.DataFrame(fire + non)


def test_contract_rejects_banned_column():
    df = _frame(4)
    df["lat"] = 36.0
    with pytest.raises(AssertionError):
        E.assert_feature_contract(df[MODEL_FEATURES_V1 + ["lat"]])


def test_contract_accepts_exact_list():
    E.assert_feature_contract(_frame(4)[MODEL_FEATURES_V1])


def test_split_frame_rejects_uncertain():
    df = _frame(4)
    df.loc[0, "label"] = "uncertain"
    with pytest.raises(AssertionError):
        E.split_frame(df, "train")


def test_full_experiment_runs_and_reports(tmp_path, monkeypatch):
    monkeypatch.setitem(E.MODEL_CONFIGS, "rf",
                        {"cls": E.MODEL_CONFIGS["rf"]["cls"],
                         "params": {"n_estimators": 10, "random_state": 42}})
    monkeypatch.setitem(E.MODEL_CONFIGS, "hgb",
                        {"cls": E.MODEL_CONFIGS["hgb"]["cls"],
                         "params": {"max_iter": 10, "random_state": 42}})
    ds = tmp_path / "mini.csv"
    _frame(40).to_csv(ds, index=False)
    out = tmp_path / "artifacts"
    record = E.run_experiment(ds, out, "deadbeef")
    assert record["model"] in ("rf", "hgb")
    assert record["test_once"]["threshold"] in E.THRESHOLD_GRID
    for key in ("roc_auc", "pr_auc", "accuracy", "precision", "recall",
                "f1", "brier", "ece"):
        assert isinstance(record["test_once"][key], float)
    assert record["post_fit_check"]["matches_contract"] is True
    assert (out / "metrics.json").exists()
    assert (out / "calibration.csv").exists()
    assert (out / "feature_importance.csv").exists()
    assert (out / "config.json").exists()
    assert len(list(out.glob("*.joblib"))) == 1
    rep = E.write_experiment_report(tmp_path / "rep.md", record)
    text = rep.read_text(encoding="utf-8")
    assert "NOT YET REGISTERED FOR PRODUCTION" in text
    assert "uncertain/excluded" in text
    assert "banned columns in X: NONE" in text
    assert "VIOLATION" not in text
