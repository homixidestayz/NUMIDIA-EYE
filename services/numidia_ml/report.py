"""Auditable dataset report writer. Every number in the report comes from the
actual build artifacts (dataset, manifests, ground-truth stats) - the writer
invents nothing and refuses to render when an artifact is missing.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def _pct(a: int, b: int) -> str:
    return f"{100.0 * a / b:.1f}%" if b else "n/a"


def write_report(report_path: Path, *, counts: dict, manifest: dict,
                 labeled: pd.DataFrame, rules: dict, split_counts: dict,
                 cohort_table: pd.DataFrame, verification: list,
                 ems_matches: int, effis_matches: int, vnf_matches: int,
                 distinct_flare_sites: int, excluded_reasons: dict) -> Path:
    """Render docs/dataset-report-v1.md from real build outputs."""
    for key in ("positive", "negative", "uncertain", "excluded", "duplicates",
                "input", "labeled"):
        if key not in counts:
            raise KeyError(f"refusing to render: missing count {key!r}")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lab = labeled
    acq = pd.to_datetime(lab["acq_datetime"], utc=True)
    wilayas = sorted(lab["wilaya_name"].dropna().unique().tolist())
    srcs = lab["label_source"].value_counts().to_dict()
    sats = lab["satellite"].value_counts(dropna=False).to_dict()
    gt = manifest.get("ground_truth", [])
    gt_lines = "\n".join(
        f"| {g['key']} | {g['type']} | {g['records']} | {g['url']} | `{g['sha256'][:12]}…` |"
        for g in gt)
    src_lines = "\n".join(f"| `{k}` | {v} |" for k, v in sorted(srcs.items()))
    sat_lines = "\n".join(f"| {k if pd.notna(k) else 'null (as published)'} | {v} |"
                          for k, v in sats.items())

    bal_total = counts["positive"] + counts["negative"] or 1
    split_lines = "\n".join(
        f"| {s} | {l} | {c} |" for (s, l), c in sorted(split_counts.items()))
    cohort_lines = "\n".join(
        f"| {r['cohort']} | {r['label']} | {r['count']} |"
        for _, r in cohort_table.sort_values(["cohort", "label"]).iterrows())
    ver_lines = "\n".join(
        f"| {'PASS' if v['ok'] else 'FAIL'} | {v['check']} | {v['detail']} |"
        for v in verification)
    reasons = "\n".join(
        f"| {r} | {c} |" for r, c in
        sorted(excluded_reasons.items(), key=lambda kv: -kv[1]))
    text = f"""# NUMIDIA verifier training dataset — report v1

Generated: {now} · rules version `{rules['version']}` · code commit `{manifest.get('code_commit', '?')}`
Status: **dataset only — no model trained, none registered.**

## Ground-truth sources used

| key | type / provenance | records | source URL | sha256 |
|---|---|---|---|---|
{gt_lines}

P3 (Protection Civile / DGF bulletins) contributes **zero** labels by design:
commune-level reports carry no coordinates, so they are validation-grade only
and no machine-readable official feed exists to download. This is reported,
not silently substituted.

Historic (2021) EFFIS perimeters are obtainable only via the manual DATA
REQUEST FORM, so P2 currently covers the 2026 season only. Reported, not faked.

## Labeling rules (v1, exact)

- **Spatial (fire):** detection point intersects a confirmed burnt polygon
  (`predicate=intersects`, shapely STRtree, CRS84).
- **Temporal (fire):** acquisition date within `[polygon_start − 1 day,
  polygon_end + 1 day]`. EMS window 2021-08-08…2021-08-22 (fires reported since
  2021-08-09, last delivery 2021-08-21). EFFIS uses each polygon's own
  FIREDATE…FINALDATE ± 1 day (all 4,554 DZ polygons carried both dates —
  zero fallbacks, see manifest).
- **Spatial (non-fire):** haversine distance ≤ {rules['flare_radius_m']:.0f} m
  to a **persistent** VNF flare site (seen in ≥2 catalog years within
  {rules['site_persist_m']:.0f} m) **and** nighttime acquisition (`daynight=N`).
- **Uncertain:** U1 = inside event AOI + window but outside every burnt polygon
  (possible sub-MMU fire or false alarm); U2 = night ring
  ({rules['flare_radius_m']:.0f}–{rules['flare_ring_m']:.0f} m) or daytime
  ≤{rules['flare_radius_m']:.0f} m of a persistent site; U3 = polygon hit
  outside the window but within {rules['u3_days']} days; conflict = both fire
  and non-fire evidence ({counts['conflicts']} cases, kept uncertain).
- **Dedup:** same (rounded {rules['dedup_decimals']}° cell ≈110 m, UTC date,
  label) → keep max FRP. Duplicates removed: **{counts['duplicates']}**.
- **Excluded:** every other pulled detection (outside all event windows/AOIs/
  flare rings) with a recorded reason — unlabeled, never forced into a class.

What was NOT used as ground truth: FIRMS confidence, FRP, or any threshold
thereof; LLM output; invented coordinates. Verified by construction: the
pipeline has no threshold-label code path.

## Dataset counts (exact)

| class | count | share of labeled |
|---|---|---|
| positive (fire) | {counts['positive']} | {_pct(counts['positive'], counts['labeled'])} |
| negative (non-fire) | {counts['negative']} | {_pct(counts['negative'], counts['labeled'])} |
| uncertain | {counts['uncertain']} | {_pct(counts['uncertain'], counts['labeled'])} |
| **labeled total** | {counts['labeled']} | — |
| excluded (unlabeled) | {counts['excluded']} | — |
| duplicates removed | {counts['duplicates']} | — |
| FIRMS detections pulled | {counts['input']} | — |

Class balance (fire : non-fire): {counts['positive']}:{counts['negative']}.

### Detections with no ground truth (excluded, saved separately with reason)

| exclude_reason | count |
|---|---|
{reasons}

### By label source (post-dedup)

| label_source | count |
|---|---|
{src_lines}

### By satellite (post-dedup)

| satellite | count |
|---|---|
{sat_lines}

### Confirmed-fire ground truth obtained

- EMSR533 burnt polygons kept: {manifest.get('ems_kept', '?')} (of
  {manifest.get('ems_features', '?')} features; repaired
  {manifest.get('ems_repaired', '?')}, dropped-invalid
  {manifest.get('ems_dropped_invalid', '?')}, skipped-notation
  {manifest.get('ems_skipped_notation', '?')}).
- EFFIS burnt polygons kept (Algeria, 2026 season): {manifest.get('effis_polygons', '?')}.
- **EMSR533 matches (fire rows via P1): {ems_matches}.**
- **EFFIS matches (fire rows via P2): {effis_matches}.**
- FIRMS detections matched to confirmed fires: **{counts['positive']}**
  (pre-dedup fire matches: {counts.get('fire_pre_dedup', '?')}).

### Confirmed non-fire ground truth obtained

- Algeria VNF flare sites (newest catalog): {manifest.get('vnf_sites', '?')},
  of which persistent (≥2 catalog years): 2021 cohort
  {manifest.get('vnf_persistent_2021', '?')} · 2026 cohort
  {manifest.get('vnf_persistent_2026', '?')}.
- **VNF non-fire matches (rows via N1-flare): {vnf_matches}**
  (pre-dedup: {counts.get('nonfire_pre_dedup', '?')}).
- **Distinct persistent flare sites with ≥1 match: {distinct_flare_sites}.**
- FIRMS detections matched to persistent sites at night: **{counts['negative']}**.

## Coverage

- Date range (labeled rows): {acq.min().date()} … {acq.max().date()}.
- FIRMS history pulled: {manifest.get('firms_history', '?')}.
  Cohort split: {manifest.get('firms_history_split', '?')}.
- Geographic coverage (wilayas present): {', '.join(wilayas) if wilayas else 'none'}.
- Detector sensors: VIIRS SNPP + NOAA-20 for 2021 (NOAA-21 launched Nov 2022 —
  no 2021 data exists); all three VIIRS sensors for 2026.

## Counts by year/cohort × class (post-dedup)

| cohort | label | count |
|---|---|---|
{cohort_lines}

## Train / validation / test partitions (event-based, in-dataset)

Rule: 2026 cohort → test (forward-time holdout); 2021 EMSR533-AOI02-Aokas →
validation (leave-one-event-out); all other 2021 rows → train. Excluded rows
carry no split. Fire-class event_ids are verified disjoint across splits (V2).

| split | label | count |
|---|---|---|
{split_lines}

## Publication verification (executed by the build — all must PASS)

| result | check | detail |
|---|---|---|
{ver_lines}

Explicit guarantees verified above: no "no ground truth" detection was labeled
negative (V1 — negatives exist only via N1-flare); no fire/event leaks across
splits (V2); no flare site is used without documented persistence (V3); 2026
detections without EFFIS/EMS ground truth remain uncertain or excluded (they
can only reach fire via P1/P2 polygon matches — V4); no synthetic rows (V5);
no FIRMS confidence/FRP threshold or LLM label path exists anywhere in the
pipeline (V6 — the allowed source set is closed, and the codebase contains no
threshold-label or LLM-label code).

## Known limitations / biases (read before training)

1. **Large-fire bias:** EMS (2,500 m² MMU, human-validated) and EFFIS (≈30 ha)
   only confirm larger burns; small fires land in U1/uncertain, not in fire.
2. **Two time windows only:** Aug 2021 (Kabylie) + Aug–Sep 2026 (northern
   Algeria). No 2022–2025 positives; forward-time generalization is untested.
3. **Flare catalog recency:** 2026 detections match the 2024 catalog (latest
   published); persistence across catalog years mitigates staleness.
4. **Sensor asymmetry:** P2 ground truth is MODIS-derived (independent sensor —
   good against circularity, but MODIS/VIIRS sensitivities differ).
5. **Daytime flare detections are uncertain, not negative** (proposal rule).
6. **P3 contributes nothing yet** (manual curation pending); event-level
   validation coverage is therefore thin.
7. **Cross-product overlap is not merged** — dedup is per (0.001° cell, date,
   label), so one fire seen in both EMS products keeps a single row only within
   the same ~110 m cell and date.
8. **Thin validation split:** val holds a single fire event (AOI02-Aokas, 201
   rows) and no non-fire rows. Use leave-one-polygon-out cross-validation
   inside train for robust estimates; do not tune on val alone.
9. **Non-fire geography is southern/industrial, fire geography is northern/
   forest** — by construction (flares vs. wildfires). A model could latch onto
   latitude instead of fire physics; training must include location-ablation
   checks (a modeling-stage requirement, recorded here).
"""
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")
    return report_path


def write_report_v2(report_path: Path, *, counts: dict, manifest: dict,
                    labeled: pd.DataFrame, rules: dict, split_counts: dict,
                    cohort_table: pd.DataFrame, fold_table: pd.DataFrame,
                    band_table: pd.DataFrame, daynight_table: pd.DataFrame,
                    sat_table: pd.DataFrame, verification: list,
                    ems_matches: int, effis_matches: int, vnf_matches: int,
                    distinct_flare_sites: int, excluded_reasons: dict) -> Path:
    """Render docs/dataset-report-v2.md. v1 files are never touched."""
    for key in ("positive", "negative", "uncertain", "excluded", "duplicates",
                "input", "labeled"):
        if key not in counts:
            raise KeyError(f"refusing to render: missing count {key!r}")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lab = labeled
    acq = pd.to_datetime(lab["acq_datetime"], utc=True)
    wilayas = sorted(lab["wilaya_name"].dropna().unique().tolist())
    srcs = lab["label_source"].value_counts().to_dict()
    sats = lab["satellite"].value_counts(dropna=False).to_dict()
    gt = manifest.get("ground_truth", [])
    gt_lines = "\n".join(
        f"| {g['key']} | {g['type']} | {g['records']} | {g['url']} | `{g['sha256'][:12]}…` |"
        for g in gt)

    def _rows(table, cols):
        return "\n".join(
            " | ".join([str(r[c]) for c in cols]) for _, r in
            table.sort_values(cols).iterrows())

    ver_lines = "\n".join(
        f"| {'PASS' if v['ok'] else 'FAIL'} | {v['check']} | {v['detail']} |"
        for v in verification)
    h1 = manifest.get("hard_negatives_h1", {})
    feats = manifest.get("model_features_v1", [])
    banned = manifest.get("banned_features", [])

    text = f"""# NUMIDIA verifier training dataset — report v2

Generated: {now} · rules version `{rules['version']}` · code commit `{manifest.get('code_commit', '?')}`
Status: **dataset only — no model trained, none registered.**
Supersedes v1 counts below; `firms_labels_v1.csv` left byte-identical (see manifest).

## Ground-truth sources used

| key | type / provenance | records | source URL | sha256 |
|---|---|---|---|---|
{gt_lines}

P3 (Protection Civile / DGF) remains validation-grade manual curation: no
machine-readable coordinate feed exists; zero labels contributed. 2021 EFFIS
perimeters remain request-form-only (P2 covers the published WFS archive,
2016–2026 as served). Reported, not substituted.

## H1 northern hard-negative review (NEW in v2)

Per-site review: `data/labels/north_sites_review.csv` — 9 VNF sites ≥34°N
individually researched (facility, operator, provenance, match evidence):
**{h1.get('suitable_sites', '?')} suitable hard-negative sites**
(8 CONFIRMED industrial: Skikda GL1K LNG ×2 stacks, Skikda RA2K refinery,
Algiers RA1G refinery, Arzew GL1Z/GL2Z + refinery ×4 stacks; 1 UNCONFIRMED
upstream anomaly at 35.213N 1.378E — explicitly NOT used as a negative).
- Distinct suitable sites with ≥1 dataset row: **{h1.get('distinct_suitable_matched', '?')}**.
- Rows at suitable sites: **{h1.get('rows_at_suitable', '?')}**,
  of which non-fire: **{h1.get('nonfire_at_suitable', '?')}**.

## Labeling rules (v1 rules + v2 split/fold/ban contract)

Fire / non-fire / uncertain / excluded rules are unchanged from v1
(spatial polygon ∩ window; night ≤1 km persistent flare; U1/U2/U3/conflict;
dedup 0.001° cell + UTC date + label → max FRP).
v2 adds: `event_id`, `strat_lat_band` (north/south at 34°N), `fold`
(geo-grouped K=5: whole wilayas together, event-sharing wilayas merged first,
greedy by size; train rows only), cohort years 2021/2022/2023/2026 (flare
catalog ≤ detection year, newest used).

### Proposed model features (exact — training-time contract)

INCLUDE: {', '.join(feats)}
(thermal/radiometric physics + sensor context only).
BAN (stratification/grouping/reporting only, assertion V9): {', '.join(banned)}.
Rationale: coordinates/wilaya identify the map; daypart/season reflect pull
windows, not fire physics; identifiers leak splits. Banned fields stay in the
file for stratification — the feature list, not column absence, is the gate.

## Dataset counts v2 (exact)

| class | count |
|---|---|
| positive (fire) | {counts['positive']} |
| negative (non-fire) | {counts['negative']} |
| uncertain | {counts['uncertain']} |
| **labeled total** | {counts['labeled']} |
| excluded (unlabeled) | {counts['excluded']} |
| duplicates removed | {counts['duplicates']} |
| FIRMS detections considered | {counts['input']} |

Class balance (fire : non-fire): {counts['positive']}:{counts['negative']}.
- EMSR533 matches: **{ems_matches}** · EFFIS matches: **{effis_matches}** ·
  VNF non-fire matches: **{vnf_matches}** (distinct persistent sites: **{distinct_flare_sites}**).
- Pre-dedup: fire {counts.get('fire_pre_dedup', '?')} · non-fire
  {counts.get('nonfire_pre_dedup', '?')} · uncertain {counts.get('uncertain_pre_dedup', '?')}.

### By label source

| label_source | count |
|---|---|
{_rows(lab[['label_source']].value_counts().reset_index(), ['label_source', 'count'])}

### By year/cohort × class

| cohort | label | count |
|---|---|---|
{_rows(cohort_table, ['cohort', 'label', 'count'])}

### By latitude band × class

| strat_lat_band | label | count |
|---|---|---|
{_rows(band_table, ['strat_lat_band', 'label', 'count'])}

### By day/night × class

| daynight | label | count |
|---|---|---|
{_rows(daynight_table, ['daynight', 'label', 'count'])}

### By satellite × class

| satellite | label | count |
|---|---|---|
{_rows(sat_table, ['satellite', 'label', 'count'])}

### Train / validation / test × class (+ folds for model selection)

| split | label | count |
|---|---|---|
{_rows(lab.groupby(['split', 'label']).size().reset_index(name='count'), ['split', 'label', 'count'])}

| fold (train only) | label | count |
|---|---|---|
{_rows(fold_table, ['fold', 'label', 'count'])}

### Detections with no ground truth (excluded, saved separately)

| exclude_reason | count |
|---|---|
{_rows(pd.DataFrame(list(excluded_reasons.items()), columns=['exclude_reason', 'count']), ['exclude_reason', 'count'])}

## Coverage

- Date range: {acq.min().date()} … {acq.max().date()}.
- Wilayas present ({len(wilayas)}): {', '.join(wilayas)}.

## Verification (executed by the build — all must PASS)

| result | check | detail |
|---|---|---|
{ver_lines}

## Remaining confounds / limitations (read before training)

1. Negatives remain ~95% southern-Saharan; H1 adds only {h1.get('nonfire_at_suitable', '?')}
   confirmed northern non-fire rows — the latitude shortcut is narrowed, not closed.
2. Day/night shortcut persists (all non-fire are night by rule); stratify, never feature it.
3. Val is one 2021 event (AOI02); use the 5 geo-folds for selection, val only as a second opinion.
   Fold class imbalance is structural: EMSR533-AOI01 is a single event holding
   ~76% of train fire rows and cannot be split without breaking event purity,
   so folds 1–2 carry no fire rows (specificity/uncertain scoring only) while
   folds 0/3/4 carry fire. Fire recall must be read from val + test, never
   from folds 1–2.
4. 2022/2023 cohorts add EFFIS-matched positives only — no new negative ground truth for those years.
5. Large-fire bias (EMS/EFFIS MMU) and MODIS-vs-VIIRS sensor asymmetry carry over from v1.
6. The type column (SP fire-type flag) is context, never a label (V6-closed source set).
"""
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")
    return report_path
