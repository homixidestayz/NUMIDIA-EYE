# NUMIDIA verifier — labeling proposal (decision required before any training)

## The problem in one paragraph

The verifier must classify VIIRS detections as **fire / non-fire / uncertain**.
FIRMS detections are *candidate* hotspots, not confirmed fires: the archive
contains wildfires, agricultural burns, gas flares, industrial heat and noise.
Training on "every FIRMS detection = fire" would bake that confusion into the
model and produce fake confidence. Labels must therefore come from
**independent observations**, never from FIRMS itself and never from arbitrary
thresholds. No model is trained or wired in until the labeling below is
approved and the resulting evaluation report is committed.

## What we refuse to do (explicit non-labels)

- ❌ "All FIRMS detections are fires" (the circularity trap).
- ❌ Confidence/FRP cutoffs as labels (that's re-packaging the input as output).
- ❌ LLM-generated labels (an LLM is not an observation; per product rules it
  may only explain results *after* a real model verdict exists).
- ❌ Treating isolated low-confidence pixels as "non-fire" without evidence.

## Proposed positive labels (confirmed fire)

### P1 — Copernicus EMS Rapid Mapping perimeters (STRONG)
- **What:** delineation + grading polygons produced by human-validated rapid
  mapping for a specific event, with acquisition dates.
- **Verified example:** activation **EMSR533 – Algeria Forest Fires
  (2021-08-11)**, Kabylie/Tizi Ouzou, 2 areas of interest, burnt-area and
  grading products at 2,500 m² minimum mapping unit.
  - https://mapping.emergency.copernicus.eu/activations/EMSR533/
  - JRC catalogue record: https://data.jrc.ec.europa.eu/dataset/452fc022-5ff1-40a9-b604-62fb276c0cfb
- **Label rule:** a VIIRS detection inside a delineation/grading polygon and
  within [polygon start − 1 day, last update + 1 day] → **fire (strong)**.
- **Why legitimate:** independent observation (post-event burnt-scar mapping,
  human-validated), zero circularity with FIRMS active-fire points.
- **Next step:** query the EMS archive for further Algeria activations
  (2022 El Tarf, July 2023 Béjaïa/Jijel — codes not yet verified, so no codes
  are asserted here).

### P2 — EFFIS burnt-area perimeters (STRONG, large fires)
- **What:** Rapid Damage Assessment burnt-area perimeters (MODIS 250 m,
  refined with Sentinel-2 since 2018; VIIRS-derived perimeters in the current
  situation viewer). EFFIS explicitly covers Middle East & North Africa and
  publishes a real-time burnt-area database plus historic extracts on request.
  - https://forest-fire.emergency.copernicus.eu/applications/data-and-services
  - https://forest-fire.emergency.copernicus.eu/downloads-instructions
- **Label rule:** same spatiotemporal join as P1 → **fire (strong)**.
- **Why legitimate:** independent burnt-scar observation, harmonized method.
- **Limitation (declared):** perimeters cover fires of roughly ≥30 ha, so P1+P2
  skew toward large events. We mitigate with P3 (below) and by reporting
  metrics stratified by FRP/size; the "uncertain" band absorbs small-fire
  ambiguity rather than forcing labels.

### P3 — Protection Civile / DGF event records (WEAK, validation-grade)
- **What:** Protection Civile situation bulletins (wilaya, often commune and
  named-place level, with dates — e.g. the July 2023 bulletins naming Aokas,
  Fenaïa, Amizour…) and DGF annual statistics (foyers + hectares per wilaya).
- **Use:** geocode to commune level, manually review a sample, and use as
  **event-level validation/stratification only** — never as strong training
  labels, because they carry no coordinates.
- **Why legitimate (in this limited role):** official ground-truth that an
  event happened; honest about its resolution limits.

## Proposed negative labels (confirmed non-fire)

### N1 — VIIRS Nightfire gas-flare catalog (STRONG)
- **What:** the Earth Observation Group's global gas-flare survey derived from
  VIIRS Nightfire (nighttime SWIR pyrometry), which separates flares from
  biomass burning by temperature + persistence. Annual flare-site files
  (spreadsheets/KML, 2012–2024) plus the archived scientific dataset
  (ORNL DAAC, DOI 10.3334/ORNLDAAC/1874).
  - https://eogdata.mines.edu/products/vnf/global_gas_flare.html
  - https://eogdata.mines.edu/download_global_flare.html
  - https://www.earthdata.nasa.gov/data/catalog/ornl-cloud-methane-flaring-sites-viirs-1874-1
- **Label rule:** a VIIRS detection within ~1 km of a catalog flare site,
  at night, at a site active in that year → **non-fire (strong)**.
- **Why legitimate:** independent physics (SWIR temperature/persistence
  signature of industrial flares vs. vegetation fires), exactly the confuser
  class that plagues southern Algeria (Hassi Messaoud, Hassi R'Mel, In Amenas,
  Berkine…).
- **Caveat (declared):** since January 2025 the VNF portal requires a Data Use
  License; the ORNL DAAC 2012–2019 archive and published annual flare files
  remain the practical route — license status to be confirmed before download.

### N2 — Persistent industrial clusters with manual review (STRONG, curated)
- **What:** multi-year FIRMS hotspot clusters at known oil/gas infrastructure
  coordinates, each confirmed by visual satellite-imagery inspection before
  admission. Small (dozens of sites) but high-precision.
- **Why legitimate:** persistence + infrastructure colocation + human review;
  documented per-site in the dataset card.

## Training & evaluation protocol (after label approval)

1. Spatiotemporal join with the rules above; dedupe; per-event IDs.
2. Splits: **leave-one-event-out** plus a forward-in-time holdout (no random
   split — fires are spatially/temporally correlated).
3. Model family: small gradient boosting / random forest on the 7 real
   features + wilaya context (auditable, no GPU theatrics).
4. Metrics: precision/recall, PR-AUC, stratified by FRP and by label source;
   calibration curve; an **uncertain band** from the calibrated threshold
   (_outputs fire / non-fire / uncertain_).
5. Gate: evaluation report committed to `data/evaluation/`; only then is a
   model registered via `NUMIDIA_ACTIVE_MODEL` and the `/ai` endpoint allowed
   to return READY. Until that commit, the API stays 503 by construction.

## Decision requested

Approve P1+P2+N1+N2 as the label program (P3 validation-only), and authorize
downloading the EMSR533 + EFFIS perimeters and the flare catalog as
`data/gis/labels/` + `data/evaluation/` inputs. Anything weaker than this
(e.g. threshold labels) will be refused rather than silently used.