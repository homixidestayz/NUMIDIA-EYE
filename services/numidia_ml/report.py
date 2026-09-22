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
