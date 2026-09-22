# NUMIDIA verifier training dataset — report v2

Generated: 2026-09-22 17:25 UTC · rules version `v1` · code commit `9e414e8`
Status: **dataset only — no model trained, none registered.**
Supersedes v1 counts below; `firms_labels_v1.csv` left byte-identical (see manifest).

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
| P2-EFFIS:MODIS-seasonal (2016-2026 as published) | EFFIS Rapid Damage Assessment burnt-area DB (MODIS, WFS SHAPEZIP) | 107428 | https://maps.effis.emergency.copernicus.eu/effis?service=WFS&request=getfeature&typename=ms:modis.ba.poly&version=1.1.0&outputformat=SHAPEZIP | `8ced1e04d4c5…` |

P3 (Protection Civile / DGF) remains validation-grade manual curation: no
machine-readable coordinate feed exists; zero labels contributed. 2021 EFFIS
perimeters remain request-form-only (P2 covers the published WFS archive,
2016–2026 as served). Reported, not substituted.

## H1 northern hard-negative review (NEW in v2)

Per-site review: `data/labels/north_sites_review.csv` — 9 VNF sites ≥34°N
individually researched (facility, operator, provenance, match evidence):
**8 suitable hard-negative sites**
(8 CONFIRMED industrial: Skikda GL1K LNG ×2 stacks, Skikda RA2K refinery,
Algiers RA1G refinery, Arzew GL1Z/GL2Z + refinery ×4 stacks; 1 UNCONFIRMED
upstream anomaly at 35.213N 1.378E — explicitly NOT used as a negative).
- Distinct suitable sites with ≥1 dataset row: **7**.
- Rows at suitable sites: **881**,
  of which non-fire: **524**.

## Labeling rules (v1 rules + v2 split/fold/ban contract)

Fire / non-fire / uncertain / excluded rules are unchanged from v1
(spatial polygon ∩ window; night ≤1 km persistent flare; U1/U2/U3/conflict;
dedup 0.001° cell + UTC date + label → max FRP).
v2 adds: `event_id`, `strat_lat_band` (north/south at 34°N), `fold`
(geo-grouped K=5: whole wilayas together, event-sharing wilayas merged first,
greedy by size; train rows only), cohort years 2021/2022/2023/2026 (flare
catalog ≤ detection year, newest used).

### Proposed model features (exact — training-time contract)

INCLUDE: bright_ti4, bright_ti5, f_bt_diff, frp, f_frp, confidence, f_confidence, scan, track, satellite, type
(thermal/radiometric physics + sensor context only).
BAN (stratification/grouping/reporting only, assertion V9): lat, lon, wilaya_code, wilaya_name, strat_lat_band, acq_datetime, acq_date, acq_time, fetched_at, detection_id, source, source_url, daynight, f_daynight, f_hour_utc, f_month, f_doy.
Rationale: coordinates/wilaya identify the map; daypart/season reflect pull
windows, not fire physics; identifiers leak splits. Banned fields stay in the
file for stratification — the feature list, not column absence, is the gate.

## Dataset counts v2 (exact)

| class | count |
|---|---|
| positive (fire) | 21445 |
| negative (non-fire) | 21317 |
| uncertain | 10853 |
| **labeled total** | 53615 |
| excluded (unlabeled) | 16537 |
| duplicates removed | 2680 |
| FIRMS detections considered | 72832 |

Class balance (fire : non-fire): 21445:21317.
- EMSR533 matches: **3734** · EFFIS matches: **17711** ·
  VNF non-fire matches: **21317** (distinct persistent sites: **456**).
- Pre-dedup: fire 22442 · non-fire
  22584 · uncertain 11269.

### By label source

| label_source | count |
|---|---|
N1-flare | 21317
N1-flare:U2-ring-or-daytime | 8755
P1-EMSR533 | 3734
P2-EFFIS | 17711
P2-EFFIS:U3-off-window | 645
U1-in-AOI-outside-polygon | 1453

### By year/cohort × class

| cohort | label | count |
|---|---|---|
2021 | fire | 8175
2021 | non-fire | 4594
2021 | uncertain | 3275
2022 | fire | 1527
2022 | non-fire | 3502
2022 | uncertain | 1470
2023 | fire | 1420
2023 | non-fire | 2828
2023 | uncertain | 1476
2026 | fire | 10323
2026 | non-fire | 10393
2026 | uncertain | 4632

### By latitude band × class

| strat_lat_band | label | count |
|---|---|---|
north | fire | 21445
north | non-fire | 1045
north | uncertain | 2761
south | non-fire | 20272
south | uncertain | 8092

### By day/night × class

| daynight | label | count |
|---|---|---|
D | fire | 12197
D | uncertain | 8372
N | fire | 9248
N | non-fire | 21317
N | uncertain | 2481

### By satellite × class

| satellite | label | count |
|---|---|---|
N | fire | 9069
N | non-fire | 9283
N | uncertain | 4859
N20 | fire | 9124
N20 | non-fire | 9086
N20 | uncertain | 4676
N21 | fire | 3252
N21 | non-fire | 2948
N21 | uncertain | 1318

### Train / validation / test × class (+ folds for model selection)

| split | label | count |
|---|---|---|
test | fire | 10323
test | non-fire | 10393
test | uncertain | 4632
train | fire | 10921
train | non-fire | 10924
train | uncertain | 6221
val | fire | 201

| fold (train only) | label | count |
|---|---|---|
0 | fire | 8274
0 | non-fire | 251
0 | uncertain | 2150
1 | non-fire | 4914
1 | uncertain | 1645
2 | non-fire | 3674
2 | uncertain | 1798
3 | fire | 1961
3 | non-fire | 509
3 | uncertain | 253
4 | fire | 686
4 | non-fire | 1576
4 | uncertain | 375

### Detections with no ground truth (excluded, saved separately)

| exclude_reason | count |
|---|---|
no_ground_truth | 16537

## Coverage

- Date range: 2021-08-08 … 2026-09-22.
- Wilayas present (34): Adrar, Algiers, Annaba, Aïn Defla, Batna, Bejaia, Biskra, Blida, Bouira, Boumerdès, Chlef, Constantine, El Oued, El Tarf, Ghardaia, Guelma, Illizi, Jijel, Khenchela, Laghouat, M'Sila, Mila, Médéa, Oran, Ouargla, Oum El Bouaghi, Skikda, Souk Ahras, Sétif, Tamanrasset, Tipaza, Tissemsilt, Tizi Ouzou, Tébessa.

## Verification (executed by the build — all must PASS)

| result | check | detail |
|---|---|---|
| PASS | V1: every non-fire row is a night detection <=1000 m of a persistent flare site (N1-flare) | non-fire rows: 21317 |
| PASS | V4: every fire row traces to a burnt polygon (P1-EMSR533 or P2-EFFIS only) | fire rows: 21445 |
| PASS | V6: label_source values come only from the documented rule set (no threshold/LLM path exists) | offenders: [] |
| PASS | V5: every labeled row traces to a real FIRMS pull (no synthetic rows) | untraced: 0 |
| PASS | V3: every flare-referenced row uses a persistent (>=2 catalog years) site | distinct flare sites referenced: 456, outside persistent set: 0 |
| PASS | V2: fire-class event_ids are disjoint across train/val/test (no event leakage) | shared fire events across splits: []; train 159 / val 1 / test 140 events |
| PASS | labeled rows all carry a split; excluded rows carry none | labeled without split: 0 |
| PASS | V8a: no wilaya spans two folds (geographic blocking) | offenders: [] |
| PASS | V8b: no train event spans two folds | offenders: [] (total 0) |
| PASS | V9: proposed features exclude all banned fields and exist in the dataset | banned-in-features: []; missing: [] |
| PASS | V10: folds cover exactly the train rows; strat band present everywhere | train w/o fold: 0, non-train w/ fold: 0, w/o band: 0 |
| PASS | INFO: physical non-fire site cells shared across splits (same flare field, different catalog years; coordinates banned from features) | shared ~1 km non-fire cells across splits: 256 |

## Remaining confounds / limitations (read before training)

1. Negatives remain ~95% southern-Saharan; H1 adds only 524
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
