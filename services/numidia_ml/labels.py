"""Labeling engine: spatiotemporal joins of real FIRMS detections against
independent ground truth. Rules versioned; every decision recorded.

Classes: fire / non-fire / uncertain / excluded (excluded rows are saved
separately with a reason - never silently dropped, never forced into a class).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from shapely.strtree import STRtree

RULES_VERSION = "v1"

FLARE_RADIUS_M = 1000.0        # <=1 km, night, persistent site -> non-fire
FLARE_RING_M = 5000.0          # 1-5 km ring (or daytime <=1 km) -> uncertain
SITE_PERSIST_M = 500.0         # cross-year catalog match distance
U3_DAYS = 30                   # polygon hit outside window, within 30d -> uncertain
# Dedup grid: 3 decimals (~110 m) + same UTC date + same label keeps max FRP.
# Removes exact repeats (re-ingest, same-overpass multi-sensor pairs) while
# preserving distinct nearby fires; residual near-dups are contained by
# event/time-based splits at training time (never random splits).
DEDUP_DECIMALS = 3


def haversine_m(lat: np.ndarray, lon: np.ndarray,
                slat: float, slon: float) -> np.ndarray:
    """Great-circle distance in meters (vectorized over detections)."""
    r = 6371000.0
    p1, p2 = np.radians(lat.astype(float)), np.radians(lon.astype(float))
    sp1, sp2 = np.radians(float(slat)), np.radians(float(slon))
    a = np.sin((sp1 - p1) / 2.0) ** 2 + np.cos(p1) * np.cos(sp1) * np.sin((sp2 - p2) / 2.0) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def polygon_hit(df: pd.DataFrame, geoms: list) -> np.ndarray:
    """Index of first containing polygon per row, -1 when none. Exact match."""
    if not geoms:
        return np.full(len(df), -1, dtype=int)
    tree = STRtree(geoms)
    out = np.full(len(df), -1, dtype=int)
    for i, (lat, lon) in enumerate(zip(df["lat"].to_numpy(dtype=float),
                                       df["lon"].to_numpy(dtype=float))):
        try:
            from shapely.geometry import Point
            hits = tree.query(Point(float(lon), float(lat)), predicate="intersects")
        except (TypeError, ValueError):
            continue
        if len(hits):
            out[i] = int(hits[0])
    return out


def mark_persistent(sites_by_year: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """Flag flare sites seen in >=2 catalog years (<=500 m apart).

    Returns one row per site of the newest catalog year available, with
    persistent=True/False and years_seen. Persistence is the N2 evidence that
    a detection at the site is industrial heat, not wildfire.
    """
    years = sorted(sites_by_year)
    if not years:
        return pd.DataFrame()
    base = sites_by_year[years[-1]].copy().reset_index(drop=True)
    base["years_seen"] = 1
    for older in years[-2::-1]:
        prev = sites_by_year[older]
        plat = prev["lat"].to_numpy(dtype=float)
        plon = prev["lon"].to_numpy(dtype=float)
        for i, row in base.iterrows():
            d = haversine_m(plat, plon, row["lat"], row["lon"])
            if len(d) and float(np.min(d)) <= SITE_PERSIST_M:
                base.at[i, "years_seen"] += 1
    base["persistent"] = base["years_seen"] >= 2
    return base


def _in_window(dates: pd.Series, start: str, end: str) -> np.ndarray:
    ts = pd.to_datetime(dates, utc=True)
    return ((ts >= pd.Timestamp(start, tz="UTC"))
            & (ts <= pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1))).to_numpy()


def build_dataset(detections: pd.DataFrame, *, burnt: list[dict],
                  aois: list[dict], flare_sites: pd.DataFrame,
                  flare_catalog_year: int) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Apply the v1 rules. Returns (labeled, excluded, counts).

    burnt: [{geometry, start, end, gt_id, source}] with source P1-EMSR533/P2-EFFIS.
    aois: [{geometry, aoi, start, end}] for the U1 uncertain rule.
    flare_sites: persistent-flagged sites (mark_persistent output).
    """
    df = detections.copy().reset_index(drop=True)
    n = len(df)
    counts: dict = {"input": n, "conflicts": 0, "duplicates": 0}
    label = np.full(n, "excluded", dtype=object)
    source = np.full(n, "", dtype=object)
    gt_id = np.full(n, "", dtype=object)
    dist = np.full(n, np.nan)
    reason = np.full(n, "no_ground_truth", dtype=object)

    acq = pd.to_datetime(df["acq_datetime"], utc=True)
    daynight = df.get("daynight", pd.Series([""] * n)).astype(str).str.upper().str[0].to_numpy()

    # ---- fire: inside a confirmed burnt polygon within its window ---------
    bgeoms = [b["geometry"] for b in burnt]
    hit = polygon_hit(df, bgeoms)
    fire_mask = np.zeros(n, dtype=bool)
    for i in np.unique(hit[hit >= 0]):
        b = burnt[int(i)]
        m = (hit == i) & _in_window(acq, b["start"], b["end"])
        fire_mask |= m
        idx = np.where(m)[0]
        source[idx] = b["source"]
        gt_id[idx] = b["gt_id"]
    label[fire_mask] = "fire"
    reason[fire_mask] = ""

    # U3: polygon hit but outside the window (within U3_DAYS) -> uncertain
    outside = (hit >= 0) & ~fire_mask
    if outside.any():
        starts = {i: burnt[int(i)]["start"] for i in np.unique(hit[outside])}
        ends = {i: burnt[int(i)]["end"] for i in np.unique(hit[outside])}
        for i in np.unique(hit[outside]):
            b = burnt[int(i)]
            m = (hit == i) & ~fire_mask
            ts = acq[m]
            lo = pd.Timestamp(b["start"], tz="UTC") - pd.Timedelta(days=U3_DAYS)
            hi = pd.Timestamp(b["end"], tz="UTC") + pd.Timedelta(days=1 + U3_DAYS)
            near = ((ts >= lo) & (ts <= hi)).to_numpy()
            idx = np.where(m)[0][near]
            label[idx] = "uncertain"
            source[idx] = b["source"] + ":U3-off-window"
            gt_id[idx] = b["gt_id"]
            reason[idx] = ""

    # ---- non-fire: night, <=1 km of a PERSISTENT flare site ---------------
    sites = flare_sites[flare_sites.get("persistent", False) == True]  # noqa: E712
    near_site = np.full(n, -1, dtype=int)
    near_dist = np.full(n, np.nan)
    if len(sites):
        slat = sites["lat"].to_numpy(dtype=float)
        slon = sites["lon"].to_numpy(dtype=float)
        dlat = df["lat"].to_numpy(dtype=float)[:, None]
        dlon = df["lon"].to_numpy(dtype=float)[:, None]
        # chunked haversine to bound memory
        best_j = np.full(n, -1, dtype=int)
        best_d = np.full(n, np.inf)
        for a in range(0, len(sites), 256):
            b = min(a + 256, len(sites))
            r = 6371000.0
            p1 = np.radians(dlat)
            p2 = np.radians(dlon)
            sp1 = np.radians(slat[a:b])[None, :]
            sp2 = np.radians(slon[a:b])[None, :]
            h = np.sin((sp1 - p1) / 2.0) ** 2 + np.cos(p1) * np.cos(sp1) * np.sin((sp2 - p2) / 2.0) ** 2
            dd = 2 * r * np.arcsin(np.sqrt(np.clip(h, 0, 1)))
            j = np.argmin(dd, axis=1)
            v = dd[np.arange(n), j]
            upd = v < best_d
            best_d[upd] = v[upd]
            best_j[upd] = (j[upd] + a)
        near_site = best_j
        near_dist = best_d

    is_night = (daynight == "N").astype(bool)
    neg_mask = is_night & (near_dist <= FLARE_RADIUS_M) & (near_site >= 0)
    # conflict: both fire and non-fire evidence -> uncertain, counted
    conflict = neg_mask & (label == "fire")
    counts["conflicts"] = int(conflict.sum())
    label[conflict] = "uncertain"
    source[conflict] = source[conflict] + "+N1-flare:CONFLICT"
    reason[conflict] = ""
    fresh_neg = neg_mask & (label == "excluded")
    label[fresh_neg] = "non-fire"
    idx = np.where(fresh_neg)[0]
    sids = sites["site_id"].tolist()
    source[idx] = "N1-flare"
    gt_id[idx] = [sids[near_site[k]] for k in idx]
    dist[idx] = near_dist[idx]
    reason[idx] = ""

    # U2: night ring 1-5 km, or daytime <=1 km of a persistent site
    ring = (is_night & (near_dist > FLARE_RADIUS_M) & (near_dist <= FLARE_RING_M)
            & (near_site >= 0) & (label == "excluded"))
    day_close = (~is_night & (near_dist <= FLARE_RADIUS_M)
                 & (near_site >= 0) & (label == "excluded"))
    u2 = ring | day_close
    label[u2] = "uncertain"
    idx = np.where(u2)[0]
    source[idx] = "N1-flare:U2-ring-or-daytime"
    gt_id[idx] = [sids[near_site[k]] for k in idx]
    dist[idx] = near_dist[idx]
    reason[idx] = ""

    # U1: inside an event AOI + window, outside every burnt polygon
    ageoms = [a["geometry"] for a in aois]
    ahit = polygon_hit(df, ageoms)
    for i in np.unique(ahit[ahit >= 0]):
        a = aois[int(i)]
        m = (ahit == i) & (label == "excluded") & _in_window(acq, a["start"], a["end"])
        idx = np.where(m)[0]
        label[idx] = "uncertain"
        source[idx] = "U1-in-AOI-outside-polygon"
        gt_id[idx] = f"AOI:{a['aoi']}"
        reason[idx] = ""

    out = df.copy()
    out["label"] = label
    out["label_source"] = source
    out["ground_truth_id"] = gt_id
    out["match_distance_m"] = np.round(dist, 1)
    out["rules_version"] = RULES_VERSION
    out["flare_catalog_year"] = flare_catalog_year

    labeled = out[out["label"] != "excluded"].copy()
    excluded = out[out["label"] == "excluded"].copy()
    excluded["exclude_reason"] = reason[out["label"] == "excluded"]

    counts["fire_pre_dedup"] = int((labeled["label"] == "fire").sum())
    counts["nonfire_pre_dedup"] = int((labeled["label"] == "non-fire").sum())
    counts["uncertain_pre_dedup"] = int((labeled["label"] == "uncertain").sum())

    # ---- dedup within (rounded cell, UTC date, label): keep max FRP --------
    labeled["acq_day"] = pd.to_datetime(labeled["acq_datetime"], utc=True).dt.date.astype(str)
    labeled["_cell_lat"] = labeled["lat"].round(DEDUP_DECIMALS)
    labeled["_cell_lon"] = labeled["lon"].round(DEDUP_DECIMALS)
    before = len(labeled)
    labeled = (labeled.sort_values("frp", ascending=False)
               .drop_duplicates(subset=["_cell_lat", "_cell_lon", "acq_day", "label"],
                                keep="first")
               .drop(columns=["_cell_lat", "_cell_lon", "acq_day"])
               .reset_index(drop=True))
    counts["duplicates"] = int(before - len(labeled))

    counts.update({
        "positive": int((labeled["label"] == "fire").sum()),
        "negative": int((labeled["label"] == "non-fire").sum()),
        "uncertain": int((labeled["label"] == "uncertain").sum()),
        "excluded": int(len(excluded)),
        "labeled": int(len(labeled)),
    })
    return labeled, excluded, counts
ALLOWED_SOURCES = {"P1-EMSR533", "P2-EFFIS", "P2-EFFIS:U3-off-window",
                   "N1-flare", "N1-flare:U2-ring-or-daytime",
                   "U1-in-AOI-outside-polygon"}


def add_event_id(df: pd.DataFrame) -> pd.DataFrame:
    """Derive a stable event key from each row ground-truth reference.

    EMSR533 rows group by AOI; EFFIS rows group by polygon; flare rows group
    by site; AOI-only (U1) rows group by AOI. Anything without a reference
    gets event unknown (must not happen for labeled rows - verified).
    """
    out = df.copy()
    events = []
    for gt in out["ground_truth_id"].astype(str).tolist():
        parts = gt.split(":")
        if parts[0] == "EMSR533" and len(parts) >= 2:
            events.append(f"EMSR533:{parts[1]}")
        elif parts[0] == "EFFIS" and len(parts) >= 3:
            events.append(f"EFFIS:{parts[1]}:{parts[2]}")
        elif parts[0] == "VNF" and len(parts) >= 3:
            events.append(f"FLARE:{parts[1]}:{parts[2]}")
        elif parts[0] == "AOI" and len(parts) >= 2:
            events.append(f"AOI:{parts[1]}")
        else:
            events.append("unknown")
    out["event_id"] = events
    return out


# Split rule v1: forward-time holdout (2026 -> test) + leave-one-event-out
# within 2021 (EMSR533 AOI02-Aokas -> validation, everything else -> train).
# Geographic + temporal separation by construction; verified disjoint below.
VAL_EVENT = "EMSR533:AOI02-Aokas"


def assign_split(df: pd.DataFrame) -> pd.DataFrame:
    """Assign train/val/test from (cohort, event_id). Excluded rows: no split."""
    out = df.copy()
    out["split"] = None
    lab = out["label"] != "excluded"
    out.loc[lab & (out["cohort"].astype(str) == "2026"), "split"] = "test"
    out.loc[lab & (out["cohort"].astype(str) == "2021")
            & (out["event_id"] == VAL_EVENT), "split"] = "val"
    out.loc[lab & out["split"].isna(), "split"] = "train"
    return out


def verify_dataset(labeled: pd.DataFrame, input_ids: set,
                   persistent_site_ids: set) -> list:
    """Run the publication checks. Each returns {check, ok, detail}."""
    checks = []
    lab = labeled

    neg = lab[lab["label"] == "non-fire"]
    if len(neg):
        ok_neg = ((neg["label_source"] == "N1-flare")
                  & (neg["match_distance_m"] <= FLARE_RADIUS_M)
                  & (neg["daynight"].astype(str).str.upper().str[0] == "N")).all()
    else:
        ok_neg = True
    checks.append({"check": "V1: every non-fire row is a night detection "
                            "<=1000 m of a persistent flare site (N1-flare)",
                   "ok": bool(ok_neg),
                   "detail": f"non-fire rows: {len(neg)}"})

    fire = lab[lab["label"] == "fire"]
    if len(fire):
        ok_fire_src = fire["label_source"].isin({"P1-EMSR533", "P2-EFFIS"}).all()
    else:
        ok_fire_src = True
    checks.append({"check": "V4: every fire row traces to a burnt polygon "
                            "(P1-EMSR533 or P2-EFFIS only)",
                   "ok": bool(ok_fire_src),
                   "detail": f"fire rows: {len(fire)}"})

    bad = sorted(lab.loc[~lab["label_source"].isin(ALLOWED_SOURCES),
                         "label_source"].unique().tolist())
    checks.append({"check": "V6: label_source values come only from the "
                            "documented rule set (no threshold/LLM path exists)",
                   "ok": len(bad) == 0, "detail": f"offenders: {bad}"})

    untraced = int((~lab["detection_id"].isin(input_ids)).sum())
    checks.append({"check": "V5: every labeled row traces to a real FIRMS pull "
                            "(no synthetic rows)",
                   "ok": untraced == 0,
                   "detail": f"untraced: {untraced}"})

    matched_sites = set(lab.loc[lab["label"] == "non-fire",
                                "ground_truth_id"].unique()) | \
        set(lab.loc[lab["label_source"] == "N1-flare:U2-ring-or-daytime",
                    "ground_truth_id"].unique())
    outside = matched_sites - persistent_site_ids
    checks.append({"check": "V3: every flare-referenced row uses a persistent "
                            "(>=2 catalog years) site",
                   "ok": len(outside) == 0,
                   "detail": f"distinct flare sites referenced: {len(matched_sites)}, "
                             f"outside persistent set: {len(outside)}"})

    fire_events = {s: set(fire[fire["split"] == s]["event_id"].unique())
                   for s in ("train", "val", "test")}
    leak = ((fire_events["train"] & fire_events["val"]) |
            (fire_events["train"] & fire_events["test"]) |
            (fire_events["val"] & fire_events["test"]))
    checks.append({"check": "V2: fire-class event_ids are disjoint across "
                            "train/val/test (no event leakage)",
                   "ok": len(leak) == 0,
                   "detail": f"shared fire events across splits: {sorted(leak)}; "
                             f"train {len(fire_events['train'])} / val "
                             f"{len(fire_events['val'])} / test {len(fire_events['test'])} events"})

    unl = lab[lab["split"].isna()]
    checks.append({"check": "labeled rows all carry a split; excluded rows carry none",
                   "ok": len(unl) == 0,
                   "detail": f"labeled without split: {len(unl)}"})
    return checks


# ---- v2 additions: folds, feature contract ---------------------------------
# Proposed model inputs: thermal/radiometric/sensor-context ONLY.
MODEL_FEATURES_V1 = [
    "bright_ti4", "bright_ti5", "f_bt_diff",      # band temperatures + contrast
    "frp", "f_frp",                               # fire radiative power
    "confidence", "f_confidence",                 # FIRMS confidence (feature, never label)
    "scan", "track",                              # pixel geometry
    "satellite", "type",                          # sensor context (one-hot at train time)
]
# Banned from model inputs (stratification/grouping/reporting only).
BANNED_FEATURES = [
    "lat", "lon", "wilaya_code", "wilaya_name", "strat_lat_band",
    "acq_datetime", "acq_date", "acq_time", "fetched_at",
    "detection_id", "source", "source_url",
    "daynight", "f_daynight", "f_hour_utc", "f_month", "f_doy",
]
NORTH_LAT = 34.0  # stratification band cut (mirrors audit)


def add_strat_band(df: pd.DataFrame) -> pd.DataFrame:
    """Add strat_lat_band (north/south). Stratification-only, never a feature."""
    out = df.copy()
    out["strat_lat_band"] = np.where(
        pd.to_numeric(out["lat"], errors="coerce") >= NORTH_LAT, "north", "south")
    return out


def assign_folds(df: pd.DataFrame, k: int = 5) -> pd.DataFrame:
    """Geo-grouped folds for model selection (train rows only).

    Whole wilayas stay together; wilayas sharing an event_id are merged first
    (union-find), then groups go to folds greedily by size. val/test/excluded
    rows get no fold. Returns the frame with a fold column.
    """
    out = df.copy()
    out["fold"] = None
    tr = out[out["split"] == "train"].copy()
    if tr.empty:
        return out
    wilayas = sorted(tr["wilaya_name"].dropna().unique().tolist())
    parent = {w: w for w in wilayas}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for _, grp in tr.groupby("event_id"):
        ws = sorted(grp["wilaya_name"].dropna().unique().tolist())
        for w in ws[1:]:
            ra, rb = find(ws[0]), find(w)
            if ra != rb:
                parent[rb] = ra
    groups: dict[str, list] = {}
    for w in wilayas:
        groups.setdefault(find(w), []).append(w)
    counts = {g: int(tr["wilaya_name"].isin(ws).sum()) for g, ws in groups.items()}
    # Class-balanced greedy: keep wilaya/event purity, but spread fire,
    # non-fire and uncertain loads across folds so every fold can score
    # every class. Score = summed filled-fraction across classes.
    class_counts = {
        g: {c: int(((tr["wilaya_name"].isin(ws)) & (tr["label"] == c)).sum())
            for c in ("fire", "non-fire", "uncertain")}
        for g, ws in groups.items()
    }
    totals = {c: int((tr["label"] == c).sum()) for c in ("fire", "non-fire", "uncertain")}
    loads = {i: {"fire": 0, "non-fire": 0, "uncertain": 0} for i in range(k)}
    group_fold: dict[str, int] = {}

    def _score(i: int, g: str) -> float:
        s = 0.0
        for c in totals:
            if totals[c]:
                s += (loads[i][c] + class_counts[g][c]) / totals[c]
        return s

    for g in sorted(counts, key=counts.get, reverse=True):  # noqa: E203
        i = min(range(k), key=lambda j: _score(j, g))
        group_fold[g] = i
        for c in loads[i]:
            loads[i][c] += class_counts[g][c]
    w2f = {w: group_fold[find(w)] for w in wilayas}
    mapped = tr["wilaya_name"].map(w2f)
    if mapped.isna().any():
        raise ValueError("fold assignment left train rows unassigned")
    out.loc[out["split"] == "train", "fold"] = mapped.astype(int).astype(str)
    return out


def verify_v2(labeled: pd.DataFrame) -> list:
    """V2 structural checks: folds, feature contract, stratification fields."""
    checks = []
    lab = labeled
    tr = lab[lab["split"] == "train"]

    wxf = tr.groupby("wilaya_name")["fold"].nunique()
    bad_w = wxf[wxf > 1].index.tolist()
    checks.append({"check": "V8a: no wilaya spans two folds (geographic blocking)",
                   "ok": len(bad_w) == 0, "detail": f"offenders: {bad_w}"})

    exf = tr.groupby("event_id")["fold"].nunique()
    bad_e = exf[exf > 1].index.tolist()
    checks.append({"check": "V8b: no train event spans two folds",
                   "ok": len(bad_e) == 0,
                   "detail": f"offenders: {bad_e[:5]} (total {len(bad_e)})"})

    banned_hit = sorted(set(MODEL_FEATURES_V1) & set(BANNED_FEATURES))
    missing = sorted(set(MODEL_FEATURES_V1) - set(lab.columns))
    checks.append({"check": "V9: proposed features exclude all banned fields "
                            "and exist in the dataset",
                   "ok": len(banned_hit) == 0 and len(missing) == 0,
                   "detail": f"banned-in-features: {banned_hit}; missing: {missing}"})

    no_fold = tr[tr["fold"].isna()]
    fold_elsewhere = lab[(lab["split"] != "train") & lab["fold"].notna()]
    noband = lab[lab["strat_lat_band"].isna()]
    checks.append({"check": "V10: folds cover exactly the train rows; "
                            "strat band present everywhere",
                   "ok": len(no_fold) == 0 and len(fold_elsewhere) == 0 and len(noband) == 0,
                   "detail": f"train w/o fold: {len(no_fold)}, non-train w/ fold: "
                             f"{len(fold_elsewhere)}, w/o band: {len(noband)}"})

    # Informational (not a failure): the same PHYSICAL flare field can appear
    # in two cohorts under different catalog-year site ids (e.g. VNF:2021:x
    # vs VNF:2024:y). Coordinates are banned from model inputs, so this cannot
    # become location memorization; it is quantified here, not hidden.
    nf = lab[lab["label"] == "non-fire"]
    shared = set()
    if len(nf):
        cells = (nf["lat"].round(2).astype(str) + "|" + nf["lon"].round(2).astype(str))
        by_split = {s: set(cells[nf["split"] == s].unique()) for s in ("train", "val", "test")}
        keys = [k for k in by_split if by_split[k]]
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                shared |= by_split[keys[i]] & by_split[keys[j]]
    checks.append({"check": "INFO: physical non-fire site cells shared across splits "
                            "(same flare field, different catalog years; "
                            "coordinates banned from features)",
                   "ok": True,
                   "detail": f"shared ~1 km non-fire cells across splits: {len(shared)}"})
    return checks
