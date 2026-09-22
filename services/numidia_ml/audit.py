"""Dataset-bias audit (analysis only - NOT a model, never registered).

Measures how separable fire/non-fire are by geography vs. by physics, so we
can tell whether a future verifier would learn wildfire characteristics or
just latitude. All outputs are diagnostics for docs/bias-audit-v1.md.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NORTH_LAT = 34.0  # North/Sahara split for the confound analysis


def _cls(df: pd.DataFrame) -> pd.Series:
    return (df["label"] == "fire").astype(int)


def distribution_summary(df: pd.DataFrame, col: str) -> dict:
    """Percentiles per class for a numeric column."""
    out = {}
    for label in ("fire", "non-fire"):
        v = pd.to_numeric(df.loc[df["label"] == label, col], errors="coerce").dropna()
        out[label] = {
            "n": int(len(v)),
            "p5": float(v.quantile(0.05)) if len(v) else None,
            "p25": float(v.quantile(0.25)) if len(v) else None,
            "median": float(v.median()) if len(v) else None,
            "p75": float(v.quantile(0.75)) if len(v) else None,
            "p95": float(v.quantile(0.95)) if len(v) else None,
        }
    return out


def histogram_overlap(df: pd.DataFrame, col: str, bins: int = 50) -> float:
    """Overlap coefficient of fire/non-fire histograms (1 = identical)."""
    f = pd.to_numeric(df.loc[df["label"] == "fire", col], errors="coerce").dropna()
    n = pd.to_numeric(df.loc[df["label"] == "non-fire", col], errors="coerce").dropna()
    if not len(f) or not len(n):
        return float("nan")
    lo, hi = min(f.min(), n.min()), max(f.max(), n.max())
    if lo == hi:
        return 1.0
    edges = np.linspace(lo, hi, bins + 1)
    hf, _ = np.histogram(f, bins=edges)
    hn, _ = np.histogram(n, bins=edges)
    return float(np.minimum(hf / hf.sum(), hn / hn.sum()).sum())


def crosstab(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Counts + fire-rate per category value."""
    ct = pd.crosstab(df[col].fillna("null"), df["label"])
    for c in ("fire", "non-fire"):
        if c not in ct.columns:
            ct[c] = 0
    ct["total"] = ct["fire"] + ct["non-fire"]
    ct["fire_rate"] = (ct["fire"] / ct["total"]).round(3)
    return ct.sort_values("total", ascending=False)


def best_single_threshold(values: np.ndarray, y: np.ndarray) -> dict:
    """Best accuracy of a one-sided threshold rule on one feature (in-sample).

    Diagnostic of linear separability along that axis - not a model.
    """
    v = np.asarray(values, dtype=float)
    mask = ~np.isnan(v)
    v, y = v[mask], np.asarray(y)[mask]
    if not len(v):
        return {"threshold": None, "direction": None, "accuracy": float("nan"), "n": 0}
    cands = np.unique(v)
    if len(cands) > 2000:
        cands = np.quantile(cands, np.linspace(0, 1, 2000))
    best = {"accuracy": -1.0}
    for t in cands:
        for direction in ("lt", "ge"):  # predict fire when (v < t) or (v >= t)
            pred = (v < t).astype(int) if direction == "lt" else (v >= t).astype(int)
            acc = float((pred == y).mean())
            if acc > best["accuracy"]:
                best = {"threshold": float(t), "direction": direction,
                        "accuracy": acc, "n": int(len(v))}
    return best


def wilaya_lookup_accuracy(df: pd.DataFrame) -> dict:
    """In-sample accuracy of predicting each row by its wilaya's majority class.

    An upper-bound separability diagnostic (it memorizes geography); reported
    as such, never used as a classifier.
    """
    sub = df[df["label"].isin(("fire", "non-fire"))].copy()
    maj = sub.groupby("wilaya_name")["label"].agg(
        lambda s: (s == "fire").mean() >= 0.5)
    pred_fire = sub["wilaya_name"].map(maj).fillna(False)
    actual_fire = sub["label"] == "fire"
    mixed = int(((sub.groupby("wilaya_name")["label"].nunique() > 1)).sum())
    return {"accuracy": float((pred_fire == actual_fire).mean()),
            "n": int(len(sub)),
            "wilayas_total": int(sub["wilaya_name"].nunique()),
            "wilayas_mixed": mixed}


def geo_baseline_test_performance(df: pd.DataFrame) -> dict:
    """Fit lat/lon-only logistic regression on train, evaluate on test/val.

    Diagnostic generalization measure of geography-as-classifier. The fitted
    object is discarded (not returned, not saved, not registered).
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    sub = df[df["label"].isin(("fire", "non-fire"))].copy()
    sub["y"] = (sub["label"] == "fire").astype(int)
    feats = ["lat", "lon"]
    out: dict = {}
    for split, fit_split in (("test", "train"), ("val", "train")):
        tr = sub[sub["split"] == fit_split].dropna(subset=feats)
        te = sub[sub["split"] == split].dropna(subset=feats)
        if not len(tr) or not len(te):
            out[split] = {"accuracy": None, "auc": None,
                          "n_train": len(tr), "n_eval": len(te)}
            continue
        scaler = StandardScaler().fit(tr[feats].to_numpy(dtype=float))
        clf = LogisticRegression(max_iter=2000)
        clf.fit(scaler.transform(tr[feats].to_numpy(dtype=float)), tr["y"].to_numpy())
        proba = clf.predict_proba(scaler.transform(te[feats].to_numpy(dtype=float)))[:, 1]
        pred = (proba >= 0.5).astype(int)
        y = te["y"].to_numpy()
        out[split] = {"accuracy": round(float((pred == y).mean()), 4),
                      "auc": round(float(_auc(y, proba)), 4),
                      "n_train": len(tr), "n_eval": len(te),
                      "eval_fire_rate": round(float(y.mean()), 4)}
    # difficulty note: how far test geography is from train geography
    tr_lat = sub.loc[sub["split"] == "train", "lat"].median()
    te_lat = sub.loc[sub["split"] == "test", "lat"].median()
    out["median_lat_train"] = round(float(tr_lat), 3)
    out["median_lat_test"] = round(float(te_lat), 3)
    return out


def _auc(y: np.ndarray, p: np.ndarray) -> float:
    """Mann-Whitney AUC with tie-averaged ranks."""
    import pandas as pd

    y = np.asarray(y)
    ranks = pd.Series(np.asarray(p, dtype=float)).rank(method="average").to_numpy()
    n1, n0 = int(y.sum()), int((1 - y).sum())
    if not n1 or not n0:
        return float("nan")
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def northern_flare_analysis(sites_by_year: dict[int, pd.DataFrame],
                            labeled: pd.DataFrame) -> dict:
    """Persistent VNF sites at/above NORTH_LAT: the northern hard-negative pool.

    Returns site counts + how many dataset rows already reference them.
    """
    from numidia_ml.labels import mark_persistent

    persistent = mark_persistent(sites_by_year)
    north = persistent[(persistent["persistent"])
                       & (persistent["lat"] >= NORTH_LAT)].copy()
    ref = labeled[labeled["ground_truth_id"].str.startswith("VNF", na=False)]
    matched_ids = set(ref["ground_truth_id"].unique())
    north_matched = north[north["site_id"].isin(matched_ids)]
    return {
        "north_lat_cut": NORTH_LAT,
        "persistent_north_sites": int(len(north)),
        "persistent_total": int(persistent["persistent"].sum()),
        "north_matched_sites": int(len(north_matched)),
        "north_sites": north[["site_id", "lat", "lon", "sector",
                              "catalog_year", "years_seen"]]
        .sort_values("lat", ascending=False).to_dict(orient="records"),
    }

def _pct_table(d: dict) -> str:
    rows = []
    for cls in ("fire", "non-fire"):
        s = d[cls]
        fmt = lambda v: "n/a" if v is None else f"{v:.2f}"
        rows.append(f"| {cls} | {s['n']} | {fmt(s['p5'])} | {fmt(s['p25'])} | "
                    f"{fmt(s['median'])} | {fmt(s['p75'])} | {fmt(s['p95'])} |")
    return chr(10).join(rows)


def write_audit_report(path, *, stats: dict, proposal: dict) -> str:
    """Render docs/bias-audit-v1.md. stats = measured; proposal = authored plan."""
    s = stats
    p = proposal
    wil_rows = chr(10).join(
        f"| {w} | {r['fire']} | {r['non-fire']} | {r['total']} | {r['fire_rate']} |"
        for w, r in s["wilaya_table"].items())
    th_rows = chr(10).join(
        f"| {k} | {v['threshold']} | {v['direction']} | {v['accuracy']} |"
        for k, v in s["thresholds"].items())
    north_rows = chr(10).join(
        f"| {x['site_id']} | {x['lat']:.3f} | {x['lon']:.3f} | {x['sector']} | "
        f"{x['catalog_year']} | {x['years_seen']} |"
        for x in s["north_sites"])
    text = f"""# NUMIDIA verifier â€” dataset bias audit v1

Generated: {s['generated_at']} Â· dataset `{s['dataset']}` (sha256 `{s['dataset_sha'][:12]}â€¦`, read-only â€” v1 immutable) Â· rules `{s['rules_version']}`
Status: **audit only â€” no model trained, none registered, no v2 dataset created.**

## 1â€“2. Latitude / longitude / wilaya by class

| class | n | p5 | p25 | median | p75 | p95 |
|---|---|---|---|---|---|---|
{_pct_table(s['lat'])}
(latitude, degrees North)

| class | n | p5 | p25 | median | p75 | p95 |
|---|---|---|---|---|---|---|
{_pct_table(s['lon'])}
(longitude, degrees East)

Histogram overlap (1 = identical distributions): latitude **{s['overlap_lat']}**,
longitude **{s['overlap_lon']}**, FRP **{s['overlap_frp']}**,
band-difference **{s['overlap_btdiff']}**.

| wilaya | fire | non-fire | total | fire_rate |
|---|---|---|---|---|
{wil_rows}

Wilaya-lookup accuracy (in-sample majority class per wilaya â€” separability
ceiling, not a classifier): **{s['wilaya_lookup']['accuracy']}**
(n={s['wilaya_lookup']['n']}, wilayas {s['wilaya_lookup']['wilayas_total']},
mixed-class wilayas {s['wilaya_lookup']['wilayas_mixed']}).

## 3â€“4. FRP / brightness-temperature by class

| class | n | p5 | p25 | median | p75 | p95 |
|---|---|---|---|---|---|---|
{_pct_table(s['frp'])}
(FRP, MW)

| class | n | p5 | p25 | median | p75 | p95 |
|---|---|---|---|---|---|---|
{_pct_table(s['bt4'])}
(I4 brightness temperature, K)

| class | n | p5 | p25 | median | p75 | p95 |
|---|---|---|---|---|---|---|
{_pct_table(s['bt5'])}
(I5 brightness temperature, K)

| class | n | p5 | p25 | median | p75 | p95 |
|---|---|---|---|---|---|---|
{_pct_table(s['btdiff'])}
(I4 âˆ’ I5 band difference, K)

## 5â€“7. Day/night, satellite, date by class

Day/night Ã— class: {s['daynight_ct']}

Satellite Ã— class: {s['sat_ct']}

Acquisition dates â€” fire: {s['fire_dates']} Â· non-fire: {s['nonfire_dates']}.

## 8. Single-threshold separability (in-sample diagnostic)

| feature | best threshold | direction | accuracy |
|---|---|---|---|
{th_rows}
(direction `lt` = predict fire when value < threshold.)

## 9. Geography-only baseline (diagnostic â€” fitted object discarded)

Logistic regression on [lat, lon] only, fit on train split:

- test: accuracy **{s['geo_baseline']['test']['accuracy']}**,
  AUC **{s['geo_baseline']['test']['auc']}**
  (n_train={s['geo_baseline']['test']['n_train']},
  n_eval={s['geo_baseline']['test']['n_eval']},
  eval fire_rate={s['geo_baseline']['test']['eval_fire_rate']})
- val: accuracy **{s['geo_baseline']['val']['accuracy']}**,
  AUC **{s['geo_baseline']['val']['auc']}**
  (n_eval={s['geo_baseline']['val']['n_eval']})
- median latitude train {s['geo_baseline']['median_lat_train']} vs test
  {s['geo_baseline']['median_lat_test']}.

Reading guide: accuracy/AUC near 1.0 on the forward-time test means coordinates
alone predict the label â€” the confound is decisive and v1 must not train a
model that sees raw coordinates.

## 10. Northern persistent-flare pool (lat â‰¥ {s['north_cut']})

Persistent northern sites: **{s['north_persistent']}** of
{s['north_total']}; already referenced by dataset rows:
**{s['north_matched']}**.

| site_id | lat | lon | sector | catalog | years_seen |
|---|---|---|---|---|---|
{north_rows if north_rows else "(none)"}

## 11. Proposed hard-negative sources (PROPOSAL â€” not implemented)

{p['hard_negatives']}

## 12. Proposed revised split (PROPOSAL â€” not implemented)

{p['split']}

## 13. Suitability verdict (PROPOSAL â€” awaiting your approval)

{p['verdict']}

## 14. Additional data needed before training (PROPOSAL)

{p['data_needs']}
"""
    from pathlib import Path as _P
    path = _P(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)
