"""Audit-helper tests - synthetic frames only (no network, no real data)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from numidia_ml import audit as A


def _frame() -> pd.DataFrame:
    return pd.DataFrame({
        "label": ["fire", "fire", "fire", "non-fire", "non-fire"],
        "lat": [36.0, 36.5, 37.0, 28.0, 29.0],
        "lon": [4.0, 5.0, 6.0, 9.0, 8.0],
        "wilaya_name": ["A", "A", "B", "C", "C"],
        "split": ["train", "train", "val", "train", "test"],
    })


def test_distribution_summary_medians():
    s = A.distribution_summary(_frame(), "lat")
    assert s["fire"]["median"] == 36.5
    assert s["non-fire"]["median"] == 28.5
    assert s["fire"]["n"] == 3


def test_histogram_overlap_extremes():
    df = _frame()
    assert A.histogram_overlap(df, "lat") < 0.5  # separated
    same = df.copy()
    same["lat"] = 35.0
    assert A.histogram_overlap(same, "lat") == 1.0  # identical


def test_best_threshold_finds_separation():
    df = _frame()
    y = (df["label"] == "fire").astype(int).to_numpy()
    best = A.best_single_threshold(df["lat"].to_numpy(), y)
    assert best["accuracy"] == 1.0
    assert best["direction"] == "ge"


def test_wilaya_lookup_memorizes():
    acc = A.wilaya_lookup_accuracy(_frame())
    assert acc["accuracy"] == 1.0
    assert acc["wilayas_mixed"] == 0


def test_auc_ranks_correctly():
    y = np.array([0, 0, 1, 1])
    assert A._auc(y, np.array([0.1, 0.2, 0.8, 0.9])) == 1.0
    assert A._auc(y, np.array([0.5, 0.5, 0.5, 0.5])) == 0.5


def test_northern_flare_analysis_counts():
    sites = {2023: pd.DataFrame([
        {"site_id": "VNF:2023:1", "lat": 36.8, "lon": 6.9, "sector": "s",
         "catalog_year": 2023},
        {"site_id": "VNF:2023:2", "lat": 31.0, "lon": 6.0, "sector": "s",
         "catalog_year": 2023},
    ]), 2024: pd.DataFrame([
        {"site_id": "VNF:2024:1", "lat": 36.8, "lon": 6.9, "sector": "s",
         "catalog_year": 2024},
        {"site_id": "VNF:2024:2", "lat": 31.0, "lon": 6.0, "sector": "s",
         "catalog_year": 2024},
    ])}
    lab = pd.DataFrame({"ground_truth_id": ["VNF:2024:1", "other"]})
    out = A.northern_flare_analysis(sites, lab)
    assert out["persistent_north_sites"] == 1
    assert out["north_matched_sites"] == 1
