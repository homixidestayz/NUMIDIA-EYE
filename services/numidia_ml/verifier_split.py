"""Leakage-safe experiment split for the live-v1 verifier (v3 split, labels untouched).

Why this exists
---------------
The committed `split` column in `firms_labels_v2.csv` cannot support model
selection:

  * `val` holds 201 rows, ALL fire and ALL from cohort 2021 -> zero negatives,
    so precision/F1/threshold cannot be chosen on it;
  * cohort 2021 spans train+val, so the split is not temporally disjoint;
  * `test` is entirely cohort 2026, so train and test differ in year AND the
    negative mechanism is the same (N1-flare) throughout.

This module derives a corrected split **from the same labels, read-only**. The
source CSV is never modified and never rewritten.

Split construction (deterministic, seed fixed)
----------------------------------------------
1. Unit of assignment is the **event** (`event_id`). Events are already pure
   (verified: 0 mixed-label events) so an event cannot straddle classes.
2. Events are keyed by (cohort, label, lat_band) and assigned to
   train/val/test round-robin within each stratum, so every split receives BOTH
   classes and both lat bands, and events stay whole.
3. Exact duplicate feature vectors are collapsed onto their first event and
   carry a shared `row_group`, so identical rows cannot appear in two splits.
4. Temporal holdout: the newest cohort (2026) is reserved for `test`, so test
   measures forward-in-time generalisation rather than interpolation.
5. The resulting counts are asserted; an assignment that cannot satisfy
   "both classes in every split" raises instead of silently degrading.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from numidia_ml.labels import BANNED_FEATURES, MODEL_FEATURES_V1

RANDOM_STATE = 20260101
TEST_COHORT = 2026
SPLITS = ("train", "val", "test")

#: Columns the model may see. Identical to the live inference contract.
FEATURE_COLUMNS: tuple[str, ...] = tuple(MODEL_FEATURES_V1)


class SplitError(RuntimeError):
    """The requested split cannot be built. Fail closed, never degrade."""


@dataclass(frozen=True)
class SplitResult:
    frame: pd.DataFrame
    description: dict


def _feature_signature(df: pd.DataFrame) -> pd.Series:
    """Stable hash of the exact model feature tuple, for duplicate collapsing."""
    cols = list(FEATURE_COLUMNS)
    parts = []
    for c in cols:
        s = df[c]
        if c == "satellite":
            parts.append(s.astype(str).str.strip())
        else:
            parts.append(pd.to_numeric(s, errors="coerce").round(6).astype(str))
    joined = parts[0]
    for p in parts[1:]:
        joined = joined + "|" + p
    return joined.map(
        lambda v: hashlib.sha1(v.encode("utf-8")).hexdigest()[:16])


def _lat_band(lat: pd.Series) -> pd.Series:
    """Same banding as the dataset: south of 34N vs north. Grouping only.

    This NEVER enters X - it is a stratification and reporting variable only.
    """
    return pd.Series(np.where(pd.to_numeric(lat, errors="coerce") < 34.0,
                              "south", "north"), index=lat.index)


def build_split(dataset_path: Path | str, *,
                random_state: int = RANDOM_STATE) -> SplitResult:
    """Build the corrected train/val/test split. Read-only on the source CSV."""
    dataset_path = Path(dataset_path)
    df = pd.read_csv(dataset_path, low_memory=False)
    df = df[df["label"].isin(("fire", "non-fire"))].copy().reset_index(drop=True)

    if df.empty:
        raise SplitError("no supervised rows (fire/non-fire) in the dataset")

    missing = [c for c in (*FEATURE_COLUMNS, "event_id", "cohort", "wilaya_name")
               if c not in df.columns]
    if missing:
        raise SplitError(f"dataset is missing required columns: {missing}")
    banned_hit = sorted(set(FEATURE_COLUMNS) & set(BANNED_FEATURES))
    if banned_hit:
        raise SplitError(f"banned columns requested as features: {banned_hit}")

    df["_y"] = (df["label"] == "fire").astype(int)
    df["_band"] = _lat_band(df["lat"])
    df["_sig"] = _feature_signature(df)

    # 1. collapse exact duplicate feature vectors onto one representative row.
    #    The whole group keeps the event of that representative, so no identical
    #    feature tuple can appear in more than one split.
    sig_first = df.drop_duplicates(subset=["_sig"], keep="first").index
    df["_group"] = df["_sig"]
    n_dupes = len(df) - len(sig_first)

    # 2. Union events that share an identical feature-vector group, so the
    #    assignment unit is simultaneously event-complete and duplicate-free.
    #    (Without this, a feature tuple seen in two events would force those
    #    events onto the same split anyway, which the shard walk must know about.)
    rep = df.loc[sig_first]
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for ev_id, grp in rep.groupby("event_id"):
        root = f"ev:{ev_id}"
        find(root)
        for g in grp["_group"].unique():
            union(root, f"g:{g}")
    # every event shares the union-find namespace, so link events via shared groups
    ev_groups = rep.groupby("event_id")["_group"].unique().to_dict()
    group_events: dict[str, list[str]] = {}
    for ev_id, gs in ev_groups.items():
        for g in gs:
            group_events.setdefault(g, []).append(ev_id)
    for evs in group_events.values():
        for other in evs[1:]:
            union(f"ev:{evs[0]}", f"ev:{other}")

    clusters: dict[str, dict] = {}
    for ev_id, grp in rep.groupby("event_id"):
        root = find(f"ev:{ev_id}")
        c = clusters.setdefault(root, {
            "events": set(), "groups": set(),
            "_y": int(grp["_y"].iloc[0]), "_band": grp["_band"].iloc[0],
            "_cohort": grp["cohort"].iloc[0]})
        c["events"].add(ev_id)
        c["groups"].update(grp["_group"].unique())

    mixed = [r for r, c in clusters.items() if len({int(v) for v in rep[rep["_group"].isin(c["groups"])]["_y"]}) > 1]
    if mixed:
        raise SplitError(
            f"{len(mixed)} duplicate-vector clusters mix fire and non-fire "
            "labels; refusing to build a split that would leak a label")

    ev = pd.DataFrame([{
        "_root": r, "n_events": len(c["events"]),
        "n_groups": len(c["groups"]),
        "_y": c["_y"], "_band": c["_band"], "_cohort": c["_cohort"],
    } for r, c in clusters.items()]).reset_index(drop=True)
    ev["_stratum"] = (ev["_cohort"].astype(str) + "|" + ev["_y"].astype(str)
                      + "|" + ev["_band"].astype(str))

    # 3. temporal holdout: newest cohort is test-only.
    ev["_split"] = np.where(ev["_cohort"] == TEST_COHORT, "test", None)

    # 4. round-robin the remaining strata across train/val so both receive both
    #    classes and both bands. Seeded shuffle inside each stratum.
    rng = np.random.default_rng(random_state)
    assign_order = ["train", "val"]
    for stratum, grp in ev[ev["_split"].isna()].groupby("_stratum", sort=True):
        idx = np.array(grp.index.to_numpy(), copy=True)
        rng.shuffle(idx)
        for n, i in enumerate(idx):
            ev.at[i, "_split"] = assign_order[n % len(assign_order)]

    if ev["_split"].isna().any():
        raise SplitError("internal error: some clusters were left unassigned")

    root_split = dict(zip(ev["_root"], ev["_split"]))
    group_to_root = {}
    for r, c in clusters.items():
        for g in c["groups"]:
            group_to_root[g] = r
    df["split_v3"] = df["_group"].map(lambda g: root_split[group_to_root[g]])
    if df["split_v3"].isna().any():
        raise SplitError("internal error: some rows were left unassigned")

    # ---- assertions: the split must be usable, not merely produced ----------
    counts = {s: df.loc[df["split_v3"] == s] for s in SPLITS}
    for s, sub in counts.items():
        if sub.empty:
            raise SplitError(f"split {s!r} is empty")
        if sub["_y"].nunique() < 2:
            raise SplitError(
                f"split {s!r} is single-class ("
                f"{sub['label'].value_counts().to_dict()}); validation and test "
                "must both contain fire and non-fire for threshold selection "
                "and honest precision/recall")

    df = df.drop(columns=["_y", "_sig"]).rename(columns={"_band": "band_v3",
                                                        "_group": "row_group"})

    ev_split = df.groupby("event_id")["split_v3"].nunique()
    if (ev_split > 1).any():
        raise SplitError("an event straddles two splits - event leakage")

    grp_split = df.groupby("row_group")["split_v3"].nunique()
    if (grp_split > 1).any():
        raise SplitError("identical feature vectors appear in two splits")
    description = {
        "strategy": "event-disjoint, feature-duplicate-collapsed, newest-cohort test",
        "random_state": random_state,
        "test_cohort_reserved": TEST_COHORT,
        "unit": "event_id",
        "duplicate_feature_vectors_collapsed": int(n_dupes),
        "events": int(rep["event_id"].nunique()),
        "assignment_clusters": int(len(ev)),
        "sizes": {s: int(len(counts[s])) for s in SPLITS},
        "label_counts": {s: counts[s]["label"].value_counts().to_dict() for s in SPLITS},
        "band_counts": {s: counts[s]["_band"].value_counts().to_dict() for s in SPLITS},
        "cohort_counts": {s: {str(k): int(v) for k, v in
                              counts[s]["cohort"].value_counts().items()} for s in SPLITS},
        "events_per_split": {s: int(counts[s]["event_id"].nunique()) for s in SPLITS},
        "event_leakage": 0,
        "duplicate_vector_leakage": 0,
        "both_classes_everywhere": True,
        "features_used": list(FEATURE_COLUMNS),
        "source_labels_modified": False,
    }
    return SplitResult(frame=df, description=description)


def assert_no_leakage(frame: pd.DataFrame) -> dict:
    """Re-verify a built split. Cheap, and called by the trainer as a gate."""
    ev = frame.groupby("event_id")["split_v3"].nunique()
    grp = frame.groupby("row_group")["split_v3"].nunique()
    rep = {
        "events_in_multiple_splits": int((ev > 1).sum()),
        "duplicate_vectors_in_multiple_splits": int((grp > 1).sum()),
        "detection_ids_in_multiple_splits": int(
            (frame.groupby("detection_id")["split_v3"].nunique() > 1).sum()),
    }
    if any(rep.values()):
        raise SplitError(f"leakage detected: {rep}")
    return rep


def feature_matrix(frame: pd.DataFrame, split: str) -> tuple[pd.DataFrame, np.ndarray]:
    """Exact contract-ordered X and binary y for one split."""
    sub = frame[frame["split_v3"] == split]
    if sub.empty:
        raise SplitError(f"split {split!r} is empty")
    if sub["label"].isin(("uncertain", "excluded")).any():
        raise SplitError("non-supervised labels reached the model input")
    X = sub[list(FEATURE_COLUMNS)].copy()
    banned_hit = sorted(set(X.columns) & set(BANNED_FEATURES))
    if banned_hit:
        raise SplitError(f"banned columns in X: {banned_hit}")
    if list(X.columns) != list(FEATURE_COLUMNS):
        raise SplitError(f"feature order drift: {list(X.columns)}")
    y = (sub["label"] == "fire").astype(int).to_numpy()
    return X, y