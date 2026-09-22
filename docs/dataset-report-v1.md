# NUMIDIA verifier training dataset — report v1

Generated: 2026-09-22 16:29 UTC · rules version `v1` · code commit `8bb32dc`
Status: **dataset only — no model trained, none registered.**

## Ground-truth sources used

| key | type / provenance | records | source URL | sha256 |
|---|---|---|---|---|
| P1-EMSR533:AOI01-TiziOuzou:DEL_PRODUCT | Copernicus EMS Rapid Mapping burnt-area polygons (human-validated) | 81 | https://cems-mapping-website.s3.eu-west-1.amazonaws.com/static/activations/EMSR533/EMSR533_AOI01_DEL_PRODUCT_r1_RTP01_v2_vector.zip | `dd7c8f2ec158…` |
| P1-EMSR533:AOI01-TiziOuzou:GRA_PRODUCT | Copernicus EMS Rapid Mapping burnt-area polygons (human-validated) | 111 | https://cems-mapping-website.s3.eu-west-1.amazonaws.com/static/activations/EMSR533/EMSR533_AOI01_GRA_PRODUCT_r1_RTP01_v1_vector.zip | `afd970a790d0…` |
| P1-EMSR533:AOI02-Aokas:DEL_PRODUCT | Copernicus EMS Rapid Mapping burnt-area polygons (human-validated) | 26 | https://cems-mapping-website.s3.eu-west-1.amazonaws.com/static/activations/EMSR533/EMSR533_AOI02_DEL_PRODUCT_r1_RTP01_v1_vector.zip | `ecdbac7e0aa7…` |
| P1-EMSR533:AOI02-Aokas:GRA_PRODUCT | Copernicus EMS Rapid Mapping burnt-area polygons (human-validated) | 35 | https://cems-mapping-website.s3.eu-west-1.amazonaws.com/static/activations/EMSR533/EMSR533_AOI02_GRA_PRODUCT_r1_RTP01_v1_vector.zip | `762ee17e62d0…` |
| N1-VNF:2020 | EOG VIIRS Nightfire annual gas-flare survey (SWIR pyrometry) | 234 | https://eogdata.mines.edu/global_flare_data/VIIRS_Global_flaring_d.7_slope_0.029353_2020_web_v1.xlsx | `efd3992892be…` |
| N1-VNF:2021 | EOG VIIRS Nightfire annual gas-flare survey (SWIR pyrometry) | 217 | https://eogdata.mines.edu/global_flare_data/VIIRS_Global_flaring_d.7_slope_0.029353_2021_web.xlsx | `7d2a2aac8733…` |
| N1-VNF:2022 | EOG VIIRS Nightfire annual gas-flare survey (SWIR pyrometry) | 210 | https://eogdata.mines.edu/global_flare_data/VIIRS_Global_flaring_d.7_slope_0.029353_2022_v20230526_web.xlsx | `c9fa2ec44404…` |
| N1-VNF:2023 | EOG VIIRS Nightfire annual gas-flare survey (SWIR pyrometry) | 219 | https://eogdata.mines.edu/global_flare_data/VIIRS_Global_flaring_d.7_slope_0.029353_2023_v20230614_web_IDmatch.xlsx | `3a4607100413…` |
| N1-VNF:2024 | EOG VIIRS Nightfire annual gas-flare survey (SWIR pyrometry) | 244 | https://eogdata.mines.edu/global_flare_data/VIIRS_Global_flaring_d.7_slope_0.029353_2024_v20240730_web_IDmatch.xlsx | `2fcf6f27fe9d…` |
| P2-EFFIS:2026-season-MODIS | EFFIS Rapid Damage Assessment burnt-area DB (MODIS, WFS SHAPEZIP) | 107428 | https://maps.effis.emergency.copernicus.eu/effis?service=WFS&request=getfeature&typename=ms:modis.ba.poly&version=1.1.0&outputformat=SHAPEZIP | `8ced1e04d4c5…` |

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
- **Spatial (non-fire):** haversine distance ≤ 1000 m
  to a **persistent** VNF flare site (seen in ≥2 catalog years within
  500 m) **and** nighttime acquisition (`daynight=N`).
- **Uncertain:** U1 = inside event AOI + window but outside every burnt polygon
  (possible sub-MMU fire or false alarm); U2 = night ring
  (1000–5000 m) or daytime
  ≤1000 m of a persistent site; U3 = polygon hit
  outside the window but within 30 days; conflict = both fire
  and non-fire evidence (0 cases, kept uncertain).
- **Dedup:** same (rounded 3° cell ≈110 m, UTC date,
  label) → keep max FRP. Duplicates removed: **2362**.
- **Excluded:** every other pulled detection (outside all event windows/AOIs/
  flare rings) with a recorded reason — unlabeled, never forced into a class.

What was NOT used as ground truth: FIRMS confidence, FRP, or any threshold
thereof; LLM output; invented coordinates. Verified by construction: the
pipeline has no threshold-label code path.

## Dataset counts (exact)

| class | count | share of labeled |
|---|---|---|
| positive (fire) | 18498 | 44.7% |
| negative (non-fire) | 14987 | 36.2% |
| uncertain | 7907 | 19.1% |
| **labeled total** | 41392 | — |
| excluded (unlabeled) | 12472 | — |
| duplicates removed | 2362 | — |
| FIRMS detections pulled | 56226 | — |

Class balance (fire : non-fire): 18498:14987.

### Detections with no ground truth (excluded, saved separately with reason)

| exclude_reason | count |
|---|---|
| no_ground_truth | 12472 |

### By label source (post-dedup)

| label_source | count |
|---|---|
| `N1-flare` | 14987 |
| `N1-flare:U2-ring-or-daytime` | 6311 |
| `P1-EMSR533` | 3734 |
| `P2-EFFIS` | 14764 |
| `P2-EFFIS:U3-off-window` | 143 |
| `U1-in-AOI-outside-polygon` | 1453 |

### By satellite (post-dedup)

| satellite | count |
|---|---|
| N | 17570 |
| N20 | 16304 |
| N21 | 7518 |

### Confirmed-fire ground truth obtained

- EMSR533 burnt polygons kept: 253 (of
  253 features; repaired
  13, dropped-invalid
  0, skipped-notation
  0).
- EFFIS burnt polygons kept (Algeria, 2026 season): 4554.
- **EMSR533 matches (fire rows via P1): 3734.**
- **EFFIS matches (fire rows via P2): 14764.**
- FIRMS detections matched to confirmed fires: **18498**
  (pre-dedup fire matches: 19416).

### Confirmed non-fire ground truth obtained

- Algeria VNF flare sites (newest catalog): 244,
  of which persistent (≥2 catalog years): 2021 cohort
  186/217 sites · 2026 cohort
  181/244 sites.
- **VNF non-fire matches (rows via N1-flare): 14987**
  (pre-dedup: 16082).
- **Distinct persistent flare sites with ≥1 match: 232.**
- FIRMS detections matched to persistent sites at night: **14987**.

## Coverage

- Date range (labeled rows): 2021-08-08 … 2026-09-22.
- FIRMS history pulled: C:\Users\Admin\Documents\NUMIDIA-EYE\data\labels\firms_history: 54423 rows after features+Algeria clip.
  Cohort split: 2021: 20311 rows; 2026: 34112 rows; other years ignored: 0 rows.
- Geographic coverage (wilayas present): Adrar, Algiers, Annaba, Aïn Defla, Batna, Bejaia, Biskra, Blida, Bouira, Boumerdès, Chlef, Constantine, El Oued, El Tarf, Ghardaia, Guelma, Illizi, Jijel, Khenchela, Laghouat, M'Sila, Mila, Médéa, Oran, Ouargla, Oum El Bouaghi, Skikda, Souk Ahras, Sétif, Tamanrasset, Tipaza, Tissemsilt, Tizi Ouzou, Tébessa.
- Detector sensors: VIIRS SNPP + NOAA-20 for 2021 (NOAA-21 launched Nov 2022 —
  no 2021 data exists); all three VIIRS sensors for 2026.

## Counts by year/cohort × class (post-dedup)

| cohort | label | count |
|---|---|---|
| 2021 | fire | 8175 |
| 2021 | non-fire | 4594 |
| 2021 | uncertain | 3275 |
| 2026 | fire | 10323 |
| 2026 | non-fire | 10393 |
| 2026 | uncertain | 4632 |

## Train / validation / test partitions (event-based, in-dataset)

Rule: 2026 cohort → test (forward-time holdout); 2021 EMSR533-AOI02-Aokas →
validation (leave-one-event-out); all other 2021 rows → train. Excluded rows
carry no split. Fire-class event_ids are verified disjoint across splits (V2).

| split | label | count |
|---|---|---|
| test | fire | 10323 |
| test | non-fire | 10393 |
| test | uncertain | 4632 |
| train | fire | 7974 |
| train | non-fire | 4594 |
| train | uncertain | 3275 |
| val | fire | 201 |

## Publication verification (executed by the build — all must PASS)

| result | check | detail |
|---|---|---|
| PASS | V1: every non-fire row is a night detection <=1000 m of a persistent flare site (N1-flare) | non-fire rows: 14987 |
| PASS | V4: every fire row traces to a burnt polygon (P1-EMSR533 or P2-EFFIS only) | fire rows: 18498 |
| PASS | V6: label_source values come only from the documented rule set (no threshold/LLM path exists) | offenders: [] |
| PASS | V5: every labeled row traces to a real FIRMS pull (no synthetic rows) | untraced: 0 |
| PASS | V3: every flare-referenced row uses a persistent (>=2 catalog years) site | distinct flare sites referenced: 232, outside persistent set: 0 |
| PASS | V2: fire-class event_ids are disjoint across train/val/test (no event leakage) | shared fire events across splits: []; train 102 / val 1 / test 140 events |
| PASS | labeled rows all carry a split; excluded rows carry none | labeled without split: 0 |

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
