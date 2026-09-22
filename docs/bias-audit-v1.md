# NUMIDIA verifier â€” dataset bias audit v1

Generated: 2026-09-22 16:39 UTC Â· dataset `firms_labels_v1.csv` (sha256 `44165a2e7a93â€¦`, read-only â€” v1 immutable) Â· rules `v1`
Status: **audit only â€” no model trained, none registered, no v2 dataset created.**

## 1â€“2. Latitude / longitude / wilaya by class

| class | n | p5 | p25 | median | p75 | p95 |
|---|---|---|---|---|---|---|
| fire | 18498 | 36.40 | 36.57 | 36.65 | 36.73 | 36.85 |
| non-fire | 14987 | 27.75 | 28.68 | 31.01 | 31.85 | 33.13 |
(latitude, degrees North)

| class | n | p5 | p25 | median | p75 | p95 |
|---|---|---|---|---|---|---|
| fire | 18498 | 3.68 | 4.46 | 5.81 | 6.56 | 8.00 |
| non-fire | 14987 | 3.18 | 5.96 | 6.72 | 8.17 | 9.79 |
(longitude, degrees East)

Histogram overlap (1 = identical distributions): latitude **0.033**,
longitude **0.4835**, FRP **0.763**,
band-difference **0.7062**.

| wilaya | fire | non-fire | total | fire_rate |
|---|---|---|---|---|
| Illizi | 0 | 6310 | 6310 | 0.0 |
| Ouargla | 0 | 5627 | 5627 | 0.0 |
| Jijel | 5259 | 0 | 5259 | 1.0 |
| Tizi Ouzou | 4121 | 0 | 4121 | 1.0 |
| Bejaia | 2561 | 0 | 2561 | 1.0 |
| Skikda | 1498 | 373 | 1871 | 0.801 |
| Annaba | 1382 | 0 | 1382 | 1.0 |
| Laghouat | 0 | 1231 | 1231 | 0.0 |
| El Tarf | 932 | 0 | 932 | 1.0 |
| Ghardaia | 0 | 842 | 842 | 0.0 |
| Guelma | 703 | 0 | 703 | 1.0 |
| Bouira | 396 | 0 | 396 | 1.0 |
| Aïn Defla | 351 | 0 | 351 | 1.0 |
| Sétif | 302 | 0 | 302 | 1.0 |
| Mila | 258 | 0 | 258 | 1.0 |
| Oran | 0 | 246 | 246 | 0.0 |
| Tébessa | 241 | 0 | 241 | 1.0 |
| Blida | 181 | 0 | 181 | 1.0 |
| El Oued | 0 | 156 | 156 | 0.0 |
| Adrar | 0 | 119 | 119 | 0.0 |
| Algiers | 0 | 70 | 70 | 0.0 |
| Médéa | 66 | 0 | 66 | 1.0 |
| Oum El Bouaghi | 65 | 0 | 65 | 1.0 |
| Souk Ahras | 47 | 0 | 47 | 1.0 |
| Khenchela | 41 | 0 | 41 | 1.0 |
| Boumerdès | 30 | 0 | 30 | 1.0 |
| Constantine | 21 | 0 | 21 | 1.0 |
| Batna | 14 | 0 | 14 | 1.0 |
| Tamanrasset | 0 | 13 | 13 | 0.0 |
| Tipaza | 10 | 0 | 10 | 1.0 |
| Chlef | 9 | 0 | 9 | 1.0 |
| M'Sila | 6 | 0 | 6 | 1.0 |
| Biskra | 2 | 0 | 2 | 1.0 |
| Tissemsilt | 2 | 0 | 2 | 1.0 |

Wilaya-lookup accuracy (in-sample majority class per wilaya â€” separability
ceiling, not a classifier): **0.9889**
(n=33485, wilayas 34,
mixed-class wilayas 1).

## 3â€“4. FRP / brightness-temperature by class

| class | n | p5 | p25 | median | p75 | p95 |
|---|---|---|---|---|---|---|
| fire | 18498 | 1.74 | 4.29 | 12.22 | 35.46 | 132.91 |
| non-fire | 14987 | 0.76 | 1.41 | 2.32 | 4.30 | 11.66 |
(FRP, MW)

| class | n | p5 | p25 | median | p75 | p95 |
|---|---|---|---|---|---|---|
| fire | 18498 | 312.38 | 324.81 | 346.09 | 367.00 | 367.00 |
| non-fire | 14987 | 304.08 | 309.48 | 316.27 | 329.02 | 347.82 |
(I4 brightness temperature, K)

| class | n | p5 | p25 | median | p75 | p95 |
|---|---|---|---|---|---|---|
| fire | 18498 | 295.49 | 300.74 | 306.55 | 318.93 | 342.85 |
| non-fire | 14987 | 289.60 | 293.75 | 295.92 | 297.92 | 301.00 |
(I5 brightness temperature, K)

| class | n | p5 | p25 | median | p75 | p95 |
|---|---|---|---|---|---|---|
| fire | 18498 | 11.96 | 20.10 | 30.74 | 40.40 | 58.77 |
| non-fire | 14987 | 10.74 | 14.11 | 20.76 | 31.98 | 50.56 |
(I4 âˆ’ I5 band difference, K)

## 5â€“7. Day/night, satellite, date by class

Day/night Ã— class: {'fire': {'N': 8550, 'D': 9948}, 'non-fire': {'N': 14987, 'D': 0}}

Satellite Ã— class: {'fire': {'N': 7876, 'N20': 7370, 'N21': 3252}, 'non-fire': {'N': 6167, 'N20': 5872, 'N21': 2948}}

Acquisition dates â€” fire: 2021-08-08 … 2026-09-07 Â· non-fire: 2021-08-08 … 2026-09-22.

## 8. Single-threshold separability (in-sample diagnostic)

| feature | best threshold | direction | accuracy |
|---|---|---|---|
| latitude | 35.08879020510255 | ge | 0.9792743019262357 |
| longitude | 6.695655152576288 | lt | 0.6719725250111991 |
| frp | 4.969269634817408 | ge | 0.7507540689861132 |
| band_difference | 24.847013506753363 | ge | 0.6364342242795281 |
(direction `lt` = predict fire when value < threshold.)

## 9. Geography-only baseline (diagnostic â€” fitted object discarded)

Logistic regression on [lat, lon] only, fit on train split:

- test: accuracy **0.9746**,
  AUC **0.9749**
  (n_train=12568,
  n_eval=20716,
  eval fire_rate=0.4983)
- val: accuracy **1.0**,
  AUC **nan**
  (n_eval=201)
- median latitude train 36.529 vs test
  35.979.

Reading guide: accuracy/AUC near 1.0 on the forward-time test means coordinates
alone predict the label â€” the confound is decisive and v1 must not train a
model that sees raw coordinates.

## 10. Northern persistent-flare pool (lat â‰¥ 34.0)

Persistent northern sites: **9** of
182; already referenced by dataset rows:
**7**.

| site_id | lat | lon | sector | catalog | years_seen |
|---|---|---|---|---|---|
| VNF:2024:243 | 36.883 | 6.961 | flare gas downstream | 2024 | 3 |
| VNF:2024:242 | 36.879 | 6.947 | flare gas downstream | 2024 | 5 |
| VNF:2024:239 | 36.870 | 6.982 | flare oil downstream | 2024 | 5 |
| VNF:2024:236 | 36.682 | 3.123 | flare oil downstream | 2024 | 5 |
| VNF:2024:235 | 35.831 | -0.305 | flare oil downstream | 2024 | 5 |
| VNF:2024:234 | 35.825 | -0.325 | flare oil downstream | 2024 | 5 |
| VNF:2024:240 | 35.815 | -0.270 | flare gas downstream | 2024 | 5 |
| VNF:2024:241 | 35.810 | -0.256 | flare gas downstream | 2024 | 5 |
| VNF:2024:8 | 35.213 | 1.378 | flare upstream | 2024 | 5 |

## 11. Proposed hard-negative sources (PROPOSAL â€” not implemented)

H1 — Northern persistent VNF sites (measured above): 9 persistent sites at/above 34.0°N, of which 7 already anchor dataset rows. Dataset today holds 689 northern negatives vs 14298 southern negatives against 18498 northern fires. H1 is real, committed ground truth in the confusing latitude band — the immediate hard-negative pool. Required before training: per-site review confirming each northern site is industrial (sector + imagery), then stratify/upsample them so the model cannot trade latitude for physics.
H2 — N2-style manual curation of northern industrial heat (cement works, power stations, refinery flares with operator-confirmed events): coordinates + event dates + imagery review, admitted per-site like N2. Not downloaded — field/literature work, no ETA.
REJECTED: labeling 'no ground truth' northern detections as negative; EFFIS unburned-area inversion; agricultural burns (combustion — at best uncertain); any threshold-derived labels.

## 12. Proposed revised split (PROPOSAL â€” not implemented)

Revise to a dual-axis design (v2 dataset fields: split stays, rule changes): (a) TIME axis — keep the 2026 forward holdout as test; (b) GEOGRAPHY axis — within 2021, geo-grouped K-fold by event (EMSR533 AOI01 vs AOI02 plus EFFIS-2021 polygon groups) for model selection, replacing single-AOI02 validation; (c) REPORTING axis — every metric stratified by latitude band (≥34°N vs <34°N) and by day/night, so geo-cheating is visible even if aggregate scores look good; (d) FEATURE RULE — raw lat/lon and wilaya identifiers are banned from model inputs (stratification-only); verification V2 extends to assert train/val/test event disjointness per fold.

## 13. Suitability verdict (PROPOSAL â€” awaiting your approval)

v1 is NOT suitable for training as-is: the negative class is geographically isolated by construction, and the measured baseline proves coordinates alone separate the classes (lat/lon-only logistic regression: 0.975 accuracy, 0.975 AUC on the 2026 forward-time test; single latitude threshold: 97.9%; wilaya lookup: 98.9%). Any model with location features would learn the map, not fire physics. A second, independent shortcut exists: every non-fire row is nighttime by construction while fires are day+night, so day/night must also be stratified at evaluation, never trusted as a feature. v1 REMAINS the approved immutable evidence base; training waits on v2 with H1 verified+stratified, the coordinate ban, and the dual-axis split.

## 14. Additional data needed before training (PROPOSAL)

1. H1 per-site industrial confirmation (sector + imagery) for the northern persistent VNF sites, committed as data/labels/north_sites_review.csv. 2. H2 northern industrial-heat curation (manual, no ETA). 3. 2022–2025 positives via EFFIS DATA REQUEST FORM / EMS archive query (manual). 4. P3 commune-level curation for event validation. 5. v2 dataset build implementing the revised split + stratification fields. None of these invent labels; all extend ground truth.
