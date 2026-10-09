# Model artifact provenance and attribution

This document covers `services/ml/models/verifier_v2/model.joblib` and the
labelled dataset it was trained on. It exists so that anyone receiving this
artifact can trace it to its sources and satisfy those sources' attribution
requirements.

## Authorization

Redistribution of `model.joblib` in this repository was explicitly authorized by
the project founder on 2026-10-09, on the record that the underlying licence
position is understood to be uncertain (see "Known uncertainty" below). The
founder accepts that residual risk. This file documents the basis; it does not
convert that risk into a legal opinion.

## What the model is

| Field | Value |
|---|---|
| Artifact | `services/ml/models/verifier_v2/model.joblib` (48,569,963 bytes) |
| Model version | `verifier-v2` |
| Feature contract | `live-v1` (VIIRS structured features only) |
| Trained | `2026-10-01T18:48:39.711160+00:00` (from `manifest.json`) |
| Training dataset | `data/labels/firms_labels_v2.csv` — 53,615 rows |
| Dataset SHA-256 | `9c103caa1d81eada55f24fd2cfce888af1cb6c010b0564c71eb5fd2ba7cf64b5` |
| Model SHA-256 | `ec749e7006e7a6bb8945284b7ae50d96903815ddb78c8a49ce92e20f8304ab26` |
| Features | `bright_ti4, bright_ti5, f_bt_diff, frp, f_frp, confidence, f_confidence, scan, track, satellite` |

Verify before use. Both `--artifact` (the `.joblib` file, not its directory) and
`--metrics` are required; without `--metrics` the dataset SHA has nothing to compare
against and verification refuses to pass:

```
uv run python -m numidia_ml.cli verify-artifact \
  --artifact services/ml/models/verifier_v2/model.joblib \
  --dataset   data/labels/firms_labels_v2.csv \
  --metrics   services/ml/models/verifier_v2/metrics.json
```

Observed result on 2026-10-09: **9 checks, 9 PASS, exit 0**, ending
`[OK] candidate eligible for review (registration still requires approval).`

The dataset identity gate can be checked independently:

```
uv run python -m numidia_ml.cli verify-dataset \
  --dataset  data/labels/firms_labels_v2.csv \
  --manifest data/labels/manifest_v2.json
```

Observed: 2 checks, 2 PASS, exit 0.

`verify_artifact` replays the metric bundle against the dataset SHA and refuses a
mismatched or tampered artifact. It is read-only and never registers anything.

### Provenance chain pinned in `manifest.json`

The manifest records `source_code_sha256` over `verifier_split.py`,
`verifier_train.py`, `verifier_model.py`, `inference.py` and `labels.py`. Changing
any of those files invalidates the recorded hashes. This is why the training code
is not refactored casually and why there is no `train` CLI subcommand.

## Full provenance of the training labels

The labels are FIRMS/VIIRS thermal-pixel features joined against **independent**
ground truth. No label is derived from FIRMS itself.

### Negative class — predominantly catalogued gas flare

| File | Records | SHA-256 |
|---|---|---|
| `VIIRS_Global_flaring_d.7_slope_0.029353_2020_web_v1.xlsx` | 234 | `efd3992892bed975b8563f224214c49858d40e577645c40cd47d2e402a0c9ca6` |
| `VIIRS_Global_flaring_d.7_slope_0.029353_2021_web.xlsx` | 217 | `7d2a2aac8733f7290c4851fe54e30cbca3aeee463363af060efbc924a54ef488` |
| `VIIRS_Global_flaring_d.7_slope_0.029353_2022_v20230526_web.xlsx` | 210 | `c9fa2ec4440445155be99e44d1bdb88ae3b1a989c54bb788288b248b47d1b8a3` |
| `VIIRS_Global_flaring_d.7_slope_0.029353_2023_v20230614_web_IDmatch.xlsx` | 219 | `3a4607100413af2d56746d31ede71aea1a698dc1f9edfedd3694f70509470193` |
| `VIIRS_Global_flaring_d.7_slope_0.029353_2024_v20240730_web_IDmatch.xlsx` | 244 | `2fcf27fe9d4a4322b62ecf9f89a4a34ad0842c192f3903e9568ae4f32e0ed6` |

Source: Earth Observation Group (EOG), Payne Institute for Public Policy,
Colorado School of Mines. Distributed from
<https://eogdata.mines.edu/products/vnf/global_gas_flare.html>.

### Positive class — human-validated burnt area

| Product | Area | Records | SHA-256 |
|---|---|---|---|
| `EMSR533_AOI01_DEL_PRODUCT_r1_RTP01_v2_vector.zip` | Tizi Ouzou | 81 | `dd7c8f2ec1584aa2725649a0fbf97b260d4122bd6783efe2e70c26422801f10e` |
| `EMSR533_AOI01_GRA_PRODUCT_r1_RTP01_v1_vector.zip` | Tizi Ouzou | 111 | `afd970a790d0e6feb5907f48412ab8b07597b7fad307673c876df70b02c3a31b` |
| `EMSR533_AOI02_DEL_PRODUCT_r1_RTP01_v2_vector.zip` | Aokas | 26 | `ecdbac7e0aa7919d8e5b2c2871af15d454a9b06be7a86c0150528ed3d37e6e9e` |
| `EMSR533_AOI02_GRA_PRODUCT_r1_RTP01_v1_vector.zip` | Aokas | 35 | `762ee17e62d0260439d24fea50c32baecf3bc3fc5fc7370ce22a024df01b2b37` |
| EFFIS MODIS seasonal burnt-area DB (WFS `ms:modis.ba.poly`, 2016-2026) | Algeria-wide | 4,554 sites used | `8ced1e04d4c51a37e16de23ae7a5fb60824aee557b1797b259f15942f7f7390a` |

Source: Copernicus Emergency Management Service, activation **EMSR533 — Algeria
Forest Fires**, and the EFFIS Rapid Damage Assessment service.

### Sensor features

NASA FIRMS (VIIRS) active-fire detections, produced by NASA and its partners.
NASA data are open; attribution to NASA FIRMS is required. No FIRMS observation is
used as its own label.

## Attribution

**If you use `model.joblib`, the labels, or anything derived from them, attribute
the sources below.**

### EOG VIIRS Nightfire

> Gas flaring data: Earth Observation Group, Payne Institute for Public Policy,
> Colorado School of Mines. https://eogdata.mines.edu/products/vnf/global_gas_flare.html

Cite the applicable publications:

- Zhizhin, M.; Matveev, A.; Ghosh, T.; Hsu, F.-C.; Howells, M.; Elvidge, C.
  *Measuring Gas Flaring in Russia with Multispectral VIIRS Nightfire.*
  Remote Sensing 2021, 13, 3078. <https://doi.org/10.3390/rs13163078>
- Elvidge, C.D.; Zhizhin, M.; Baugh, K.; Hsu, F.-C.
  *Methods for Global Survey of Natural Gas Flaring from Visible Infrared Imaging
  Radiometer Suite Data.* Energies 2016, 9, 14. <https://doi.org/10.3390/en9010014>
- Elvidge, C.D.; Zhizhin, M.; Hsu, F.-C.; Baugh, K.E.
  *VIIRS Nightfire: Satellite Pyrometry at Night.*
  Remote Sensing 2013, 5, 4423-4449. <https://doi.org/10.3390/rs5094423>

These are the citations EOG itself publishes as the required credit.

### Copernicus Emergency Management Service

> Burnt-area perimeters: Copernicus Emergency Management Service (CEMS),
> activation EMSR533 (Algeria Forest Fires), and the EFFIS Rapid Damage Assessment
> service. <https://mapping.emergency.copernicus.eu/activations/EMSR533/>

Copernicus data are free and open under the EU's reuse policy; attribution to the
Copernicus Emergency Management Service with the activation identifier is required.
Confirm the exact notice required for your intended use against the activation page.

### NASA FIRMS

> Active-fire detections: NASA FIRMS. <https://firms.modaps.eosdis.nasa.gov/>

## Known uncertainty — read before redistributing further

The EOG VIIRS Nightfire licence changed. EOG states that **effective 10 January
2025, all VIIRS Nightfire data is available only under a VIIRS Nightfire Data Use
License** (academic: no-cost one-year signed license; commercial: paid one-year
subscription; non-profit: annual subscription). Separately, an EOG licensing
document places **select subsets** of VNF under
**Creative Commons Attribution 4.0 International**, which permits copying,
modification and distribution in any format, including commercially, provided
attribution is given.

The specific annual flare files listed above are from **2020-2024** and therefore
predate the 10 January 2025 change. What is *not* established here is whether that
predates the change is sufficient to place a **model derived from** those files —
rather than the files themselves — under CC BY 4.0. Determining that is a legal
question this project has not answered.

The founder has accepted this residual risk for redistribution inside this
repository. Anyone redistributing further, or using the model commercially, should
resolve it — by contacting EOG at `eog@mines.edu` — rather than relying on this
file.

## Downstream compliance is your responsibility

Nothing in this document is legal advice, and nothing in it grants you rights.
If you use the model or the labels:

- you are responsible for complying with the terms of every source listed above;
- you are responsible for determining whether your use is permitted, particularly
  for commercial use;
- you should carry the attribution statements in this file with any publication,
  demo, or derivative product;
- you accept that this project makes no representation about the licence status of
  data derived from sources it does not control.

## The already-committed dataset

`data/labels/firms_labels_v2.csv` (22.6 MB, 53,615 rows) has been committed to
this repository's history since 2026-10-01. It carries the same VNF-derived
negative labels described above. This is a pre-existing exposure rather than
something introduced by distributing the model, and the founder has been informed
of it and elected to keep it in history. It is recorded here so that the fact is
discoverable rather than buried.