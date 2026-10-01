# NUMIDIA EYE — AI wildfire verifier readiness audit (v1)

**Status: NOT production-ready. No model is registered. `/ai` returns `503 AI_UNAVAILABLE`.**

This document is an audit only. It registers nothing, deploys nothing, and changes no
production behaviour. Every number below was measured from the repository on the date
of the audit. Anything that could not be measured is marked
`UNKNOWN — requires verification` rather than estimated.

- Audit date: 2026-10-01
- Dataset: `data/labels/firms_labels_v2.csv`
- Dataset SHA (LF-canonical): `9c103caa1d81eada55f24fd2cfce888af1cb6c010b0564c71eb5fd2ba7cf64b5`
- Registry state: `services/ml/MODELS.md` → "Registered for production: **NONE**"

---

## 1. Current architecture

```
NASA FIRMS / VIIRS (real detections)
   │
   ├──► numidia_core  ──► SQLite (data/db/numidia.db)  ──► FastAPI ──► React dashboard
   │      ingestion, validate, derive f_*, wilaya enrichment
   │
   └──► numidia_ml  ──► labeled dataset v2 (ground truth: EMSR533 / EFFIS / VNF)
          labels.py, ground_truth.py, experiment.py, audit.py, report.py,
          verify_artifact.py, cli.py
                    │
                    └──► candidate artifacts (gitignored, quarantined)

Serving path for verification:  FastAPI `/detections/{id}/ai`
   ──► numidia_core.pipeline.verification_status()
         returns AI_UNAVAILABLE on every branch (measured, §8)

The verifier is NOT connected to the serving path. The ML package produces
artifacts for review; it does not serve predictions.
```

---

## 2. Dataset audit

| Property | Measured value |
|---|---|
| Path | `data/labels/firms_labels_v2.csv` |
| Size | 23,654,437 bytes |
| Version | dataset `v2`, rules `v1` |
| Generated | 2026-09-22T17:20:15Z |
| Rows | **53,615** (from 72,832 input rows) |
| Columns | 42 |
| Positive (`fire`) | **21,445** |
| Negative (`non-fire`) | **21,317** |
| `uncertain` | **10,853** (retained but excluded from training) |
| `excluded` | **16,537** (not written to the labeled CSV) |
| Duplicates removed | 2,680 |
| Label conflicts | **0** |
| Missing values in model features | 0 for all features **except `type` (25,348 nulls)** |

**Split distribution (measured)**

| split | fire | non-fire | uncertain | rule |
|---|---|---|---|---|
| train | 10,921 | 10,924 | 6,221 | 2021/2022/2023 cohorts minus the val event |
| val | **201** | **0** | 0 | cohort 2021 + `event_id == EMSR533:AOI02-Aokas` |
| test | 10,323 | 10,393 | 4,632 | cohort 2026 (forward-time holdout) |

**Geo-grouped folds — assigned, published, but never used for model selection**

| fold | fire | non-fire |
|---|---|---|
| 0 | 8,274 | 251 |
| 1 | **0** | 4,914 |
| 2 | **0** | 3,674 |
| 3 | 1,961 | 509 |
| 4 | 686 | 1,576 |

Two folds contain **zero fire rows** and two are dominated by fire. The folds are the
correct mechanism for model selection, and `experiment.py` does not use them (§7).

---

## 3. Ground-truth audit

Label sources are a closed set (`labels.py:244 ALLOWED_SOURCES`, enforced by check V6).

| label_source | fire | non-fire | uncertain | meaning |
|---|---|---|---|---|
| `P1-EMSR533` | 3,734 | 0 | 0 | Copernicus EMSR533 burnt-area polygons |
| `P2-EFFIS` | 17,711 | 0 | 0 | EFFIS burnt-area polygons |
| `P2-EFFIS:U3-off-window` | 0 | 0 | 645 | EFFIS ref outside the acquisition window |
| `N1-flare` | 0 | **21,317** | 0 | night detection near a persistent VNF flare site |
| `N1-flare:U2-ring-or-daytime` | 0 | 0 | 8,755 | flare ring/daytime → uncertain |
| `U1-in-AOI-outside-polygon` | 0 | 0 | 1,453 | inside the AOI but outside every burnt polygon |

`ground_truth_id` prefixes: `VNF` 30,072 · `EFFIS` 18,356 · `EMSR533` 3,734 · `AOI` 1,453.

**Structural asymmetry that dominates everything downstream:** every positive comes from
a burnt-area polygon (EMSR533/EFFIS). Every negative comes from a single mechanism,
night-time gas flares near persistent VNF sites. There is **no non-flare negative in the
dataset**. "Non-fire" currently means "this is a flare", not "this is not a wildfire".

### Live detections and the dataset

**885 of the 2,977 detection IDs currently in the live database also appear in the
training dataset.** This is expected and correct: the dataset is built from *dated FIRMS
history windows* (`data/labels/firms_history/`), not from the live table, so overlapping
acquisitions are deduplicated by `detection_id`.

Critically, **live detections do not become positives by being detected.** A row is only
labelled `fire` if it falls inside an EMSR533/EFFIS burnt polygon with a valid temporal
window. The 20,716 fire/non-fire test rows come from the 2026 cohort — those *are* recent
live-era detections, labelled retrospectively against EFFIS. That is correct supervision,
not leakage, but it does mean the test set is the same era the model will serve.

---

## 4. Feature audit

`MODEL_FEATURES_V1` (11 features) and `BANNED_FEATURES` (17). Enforced in code and by
manifest check V9.

| Feature | Meaning | Source | Unit | Preprocessing | In live API? | Reproducible at inference? |
|---|---|---|---|---|---|---|
| `bright_ti4` | VIIRS band I4 brightness temperature | FIRMS CSV | K (per `docs/bias-audit-v1.md`) | none | ✅ | ✅ identical field |
| `bright_ti5` | VIIRS band I5 brightness temperature | FIRMS CSV | K | none | ✅ | ✅ |
| `f_bt_diff` | TI4 − TI5 contrast | derived `processing.py` | K | none | ✅ | ✅ recomputed by the same function |
| `frp` | Fire radiative power | FIRMS CSV | MW | none | ✅ | ✅ |
| `f_frp` | FRP feature copy | derived | MW | none | ✅ | ✅ |
| `confidence` | FIRMS confidence | FIRMS CSV | 0–1 | none | ✅ | ✅ |
| `f_confidence` | confidence copy | derived | 0–1 | none | ✅ | ✅ |
| `scan` | VIIRS scan angle | FIRMS CSV | degrees | none | ✅ | ✅ |
| `track` | VIIRS track angle | FIRMS CSV | degrees | none | ✅ | ✅ |
| `satellite` | platform id | FIRMS CSV | category | one-hot at fit time | ✅ | ✅ |
| `type` | fire classification hint | FIRMS CSV | category | one-hot at fit time | ✅ (often `null`) | ⚠️ **25,348 of 53,615 rows null** |

**All 11 features are present in the live `/detections` response** (measured against the
running API schema). No feature is training-only. `numidia_core.processing.derive_features`
is the shared derivation used by both ingestion and the labeled dataset, so the derived
features are reproduced by the same code path.

**Banned and correctly excluded**: `lat`, `lon`, `wilaya_code`, `wilaya_name`,
`strat_lat_band`, `acq_datetime`, `acq_date`, `acq_time`, `fetched_at`, `detection_id`,
`source`, `source_url`, `daynight`, `f_daynight`, `f_hour_utc`, `f_month`, `f_doy`.

The hour / month / day-of-year / day-night variables are **deliberately excluded from the
feature set**. This is the single most consequential modelling decision in the project:
it removes the most obvious temporal shortcut, but it also means the model cannot learn
diurnal or seasonal fire behaviour at all. See §5.

**Risks**

- `type` is null for 47% of rows. One-hot encoding of a mostly-null category is a
  **missingness shortcut**: if `type` is non-null only in one era or region, it becomes a
  proxy for the label. Feature-importance analysis is required before this feature is
  allowed into production.
- Categorical handling is done inside `experiment.make_pipeline`, not documented
  separately. `UNKNOWN — requires verification`: whether the fitted pipeline stores its
  own `categories_`, and therefore whether inference sees an identical mapping.
- The feature contract is a *list of names*. There is **no versioned feature schema**
  (no dtypes, no units, no ordering contract) recorded in the artifact beyond
  `feature_names_in_`.

---

## 5. Leakage audit

All checks measured on the 42,778 labelled rows (fire + non-fire).

| Leakage vector | Result | Verdict |
|---|---|---|
| Duplicate `detection_id` across splits | **0** | ✅ clean |
| Identical feature vectors across splits | **0** | ✅ clean |
| Fire `event_id` appearing in >1 split | **0 of 300** | ✅ clean |
| Non-fire `event_id` appearing in >1 split | **0 of 423** | ✅ clean |
| Cohorts across splits | 1 (`2021` in train and val, by design — val is a held-out 2021 AOI) | ✅ intentional |
| **Wilaya appearing in >1 split** | **22 of 34 wilayas** | ⚠️ **spatial leakage** |
| **Non-fire ~1 km cells appearing in >1 split** | **276 cells, 19,469 rows** | ⚠️ **spatial leakage** |
| **`acq_datetime` values in >1 split** | **30** | ⚠️ **temporal leakage** |

### Spatial leakage is present and material

The split is *event*-disjoint and *time*-disjoint, but it is **not geography-disjoint**.
22 of 34 wilayas contribute rows to both train and test. 19,469 non-fire rows sit in
~1 km cells that appear in more than one split — these are the same flare fields
catalogued in different years, as manifest check V8-adjacent INFO notes
("shared ~1 km non-fire cells across splits: 256").

Consequence: the model can see a flare field's *local radiometric signature* during
training and meet the same field in test. Because every negative is a flare, this is
exactly the memorisable pattern that inflates test performance without generalising to a
new flare field. **The geo-grouped folds in §2 exist precisely to fix this and are not
being used.**

### No temporal leakage, but also no temporal generalisation test

The test set is the 2026 cohort and training is 2021–2023: a genuine forward-time
holdout. This is good design and is preserved. However, the model has **never been
evaluated on a strictly later period than its training data with a fully disjoint
geography**, so the combined "new place *and* new time" case is untested.

### Label leakage

No post-fire information is used as a predictor: labels come from burnt-area polygons and
flare catalogues, never from the detection's own radiometry. Hour/month/day-of-year are
computed from `acq_datetime` and are **banned** as features, so the model cannot exploit
"time of acquisition" as a shortcut.

### The dominant shortcut is not leakage but label construction

`south` has **0 fire and 20,272 non-fire** rows; `north` has **21,445 fire and 1,045
non-fire**. Combined with `satellite` and `type` (both era-linked), the label is close to
linearly separable by region. `docs/bias-audit-v1.md` already measured a geo-only baseline
at 0.975 accuracy, confirming the confound dominates. This is not train/test leakage; it
is a dataset that cannot support the claim "this model detects wildfires".

---

## 6. Geographic bias audit

Measured on the untouched 2026 test cohort, threshold 0.6, from
`services/ml/models/exp_v1/metrics.json`.

| Stratum | n | precision | recall | F1 | ROC-AUC | notes |
|---|---|---|---|---|---|---|
| **Overall** | 20,716 | 0.619 | 0.960 | 0.752 | **0.918** | headline metric |
| **North** | 10,847 | **0.961** | 0.960 | **0.961** | 0.897 | where all fire is |
| **South** | 9,869 | **0.000** | **0.000** | **0.000** | n/a | `single_class: true` — **no fire rows at all** |
| Day (`D`) | 5,644 | 1.000 | 0.987 | 0.993 | n/a | single class (no negatives) |
| Night (`N`) | 15,072 | 0.415 | 0.927 | 0.574 | 0.844 | where all 6,105 FP live |
| Satellite `N` | 7,036 | 0.609 | 0.977 | 0.750 | 0.932 | |
| Satellite `N20` | 7,480 | 0.632 | 0.960 | 0.762 | 0.925 | |
| Satellite `N21` | 6,200 | 0.615 | 0.942 | 0.744 | 0.890 | |

**The south stratum is 5,707 false positives out of 9,869 rows — every single southern
detection is classified as fire, with precision 0.000.** The overall ROC-AUC of 0.918 is
carried entirely by the northern band. Publishing that number without the south column
would be misleading.

**Wilaya-level evaluation is not produced.** `test_stratified` contains only `lat_band`,
`daynight`, `satellite`, `cohort`. Measured non-fire concentration is extreme —
Illizi 9,093 and Ouargla 7,796 with zero fire each; Jijel 5,297 and Tizi Ouzou 4,140 with
zero non-fire each. `UNKNOWN — requires verification`: per-wilaya metrics; the strata
needed do not exist in the current harness.

**Event-level recall** (test fire events, n=140): median 1.000, **min 0.000**, p10 0.746.
Three events (`EFFIS:DZ:651196`, `:637281`, `:637265`) were missed entirely at n=1.

**Calibration**: test ECE **0.284**, Brier 0.244. Probabilities are off by ~28 points on
average and must not be presented as confidence.

---

## 7. Candidate model inventory

One candidate exists on disk. No winner is declared here.

### `exp-v1` — HistGradientBoostingClassifier (local run)

| Property | Value |
|---|---|
| Artifact | `services/ml/models/exp_v1/hgb_exp-v1.joblib` (453,642 bytes) |
| Registry state | **experimental, gitignored, quarantined, not registered** |
| Feature set | `MODEL_FEATURES_V1` (11 features) — `post_fit_check.matches_contract = true`, `no_banned = true` |
| Fit rows | 21,845 (fire + non-fire from train only) |
| Threshold | 0.6 |
| Selection rule | "higher val recall at chosen threshold; tie-break train PR-AUC" |
| Threshold selection | **max train F1** (self-documented as optimistic) |
| sklearn | 1.9.1 |
| random_state | 42 |
| params | `max_iter=300, learning_rate=0.06` |

| Metric (test, threshold 0.6) | Value |
|---|---|
| ROC-AUC | 0.9175 |
| PR-AUC | 0.9353 |
| Accuracy | 0.6852 |
| Precision | 0.6187 |
| Recall | 0.9597 |
| F1 | 0.7524 |
| Brier | 0.2440 |
| ECE | 0.2840 |
| Confusion | tp 9,907 · tn 4,288 · **fp 6,105** · fn 416 |

### Noted non-candidate

A cloud RandomForest run (ROC-AUC 0.9380, F1 0.7926 at threshold 0.7, sklearn 1.6.1) is
described in `docs/cloud-training.md`. **No artifact from it is present on this machine**,
so it is not verifiable here and is not inventoried as a candidate.

### Selection-methodology defects

1. **Threshold is tuned on train F1**, not on validation. `experiment.py` labels this
   optimistic in its own comment. The train sweep reaches accuracy 0.974 / F1 0.975 —
   versus 0.685 / 0.752 on test. That gap is overfitting plus an inflated tuning surface.
2. **The validation split has 0 negatives**, so precision cannot be measured on it.
   Selection therefore ran on 201 fire-only rows, and the tie-break used *train* PR-AUC
   (0.9992 / 0.9996), which is a training-set statistic.
3. **The geo-grouped folds were never used** for selection or evaluation, despite being
   computed and published.

---

## 8. Production inference audit

### Current `/ai` behaviour (measured against the running app)

```
GET /detections/{real_id}/ai
  HTTP            503
  status          AI_UNAVAILABLE
  probability     None
  verified        None
  model           None
GET /system/status -> ai = UNAVAILABLE, model = None
NUMIDIA_ACTIVE_MODEL set: False
```

### Fail-closed properties that already hold ✅

| Property | Evidence |
|---|---|
| No model registered | `MODELS.md` "NONE"; `ACTIVE_MODEL` empty |
| No probability served | route declares `status_code=503`; body fields are `None` |
| "READY" is unreachable | `verification_status()` returns `AI_UNAVAILABLE` on all three branches; the string `"READY"` does not appear in `pipeline.py` |
| Missing model file refused | branch returns `AI_UNAVAILABLE` with "refusing to serve" |
| Unreviewed model refused | branch refuses even when a file exists: "unevaluated predictions are refused" |
| Feature contract checked | `verify_artifact` asserts `feature_names_in_` == `MODEL_FEATURES_V1` and no banned columns |
| Dataset provenance gate | `verify-dataset` enforces manifest SHA; `verify-artifact` is fail-closed (see below) |

### Gaps that must close before any deployment ❌

| Gap | Detail |
|---|---|
| **No model loader** | Nothing in the serving path imports joblib or sklearn. There is no `load_model()`, no inference module, no scorer. `POST`/`GET /ai` cannot score a detection even if a model were registered. |
| **No inference feature builder** | The serving path never assembles `MODEL_FEATURES_V1` from a detection. `processing.derive_features` produces the `f_*` fields and the API already returns them, but no code selects and orders the 11 features into the pipeline's expected frame. |
| **No registry loader / no registry enforcement in code** | `MODELS.md` describes a 5-step gate as prose only. Nothing reads it at runtime. |
| **No model version at runtime** | `AiResult.model` is always `None`. There is no version string, no artifact hash, no build id. |
| **No dataset SHA verified at serving time** | The SHA gate exists as a *pre-deployment CLI* check only. `/ai` never checks it. |
| **No feature-schema verification at serving time** | Contract is checked only inside `verify-artifact`. |
| **No threshold verification at serving time** | Threshold lives only inside the artifact. |
| **Artifact provenance currently FAILS** | Measured: `verify-artifact` on exp-v1 exits **2**. Its `metrics.json` carries no `dataset_sha256`, and `config.json` records `d8e9fbb3…` while the manifest holds `9c103caa…`. **The existing artifact cannot pass the gate as it stands.** Note the metric replay itself PASSES, so the model is reproducible — only the provenance record is missing. |
| **No write-path audit trail for alerts** | `alerts.py` `history` has no actor. Out of scope here, noted as a Phase 9 item. |

---

## 9. Concrete blockers

Ranked. **No amount of threshold tuning addresses items 1–3.**

| # | Blocker | Evidence | Type |
|---|---|---|---|
| **B1** | **No positive examples south of 34°N.** The test south stratum has 5,707/9,869 false positives, precision 0.000. A model that cannot recognise a Saharan flare is unsafe to deploy, because flares are exactly where a false positive wastes an emergency response. | §6 | **data** |
| **B2** | **Spatial leakage.** 22/34 wilayas and 19,469 rows in ~1 km cells span splits. The test set is not independent of the training geography. | §5 | **data** |
| **B3** | **Only one negative mechanism.** All 21,317 negatives are night-time VNF flares. "Non-fire" is not a general concept in this dataset. | §3 | **data** |
| **B4** | **No inference path exists.** No loader, no scorer, no feature assembly, no runtime schema/threshold/SHA verification. | §8 | **architecture** |
| **B5** | **Validation split cannot measure precision** (201 fire, 0 non-fire), and the threshold was tuned on train. | §2, §7 | **methodology** |
| **B6** | **Geo-grouped folds computed but unused** for selection or evaluation. | §2, §7 | **methodology** |
| **B7** | **Calibration ECE 0.284** — probabilities unusable as confidence. | §6 | **model** |
| **B8** | **Artifact fails its own provenance gate** (missing `dataset_sha256`, stale SHA in `config.json`). | §8 | **provenance** |
| **B9** | **`type` is 47% null** and may act as a missingness shortcut; unquantified importance. | §4 | **model** |
| **B10** | **No per-wilaya evaluation** exists in the harness. | §6 | **evaluation** |
| **B11** | **Event recall floor is 0.000** — three single-detection events entirely missed. | §6 | **model** |

B1, B2 and B3 are **data** problems. No modelling decision can register a production
verifier until they are addressed, and none of them may be resolved by dropping the hard
negative examples that cause them.

---

## 10. Proposed acceptance gates

Deliberately expressed as *evidence required*, not as arbitrary numeric thresholds. Any
numeric bar must be set **before** the candidate is trained, and must be met by a model
that has never been tuned against the test set.

### Gate A — Data provenance
- A1 Dataset SHA recorded in **every** artifact and metrics bundle, LF-canonical, equal to the manifest.
- A2 Every label traces to a named ground-truth source in the closed `ALLOWED_SOURCES` set; zero conflicts.
- A3 Label rules versioned (`rules_version`) and the dataset rebuildable from pinned URLs + SHA.
- A4 Live detections demonstrably **never** become positives without polygon ground truth.

### Gate B — Leakage
- B1 Zero `event_id` overlap across splits (currently already true).
- B2 Zero `detection_id` and zero identical feature-vector overlap across splits (already true).
- B3 **Geo-disjoint evaluation**: model selection and reporting performed on the geo-grouped folds; a wilaya-disjoint holdout reported as the headline number.
- B4 Non-fire cells shared across splits quantified and reported, not merely noted.
- B5 Temporal holdout preserved (forward-time), plus an explicit "unseen geography **and** unseen period" evaluation.

### Gate C — Geography
- C1 Stratified metrics reported for north, south, day, night, per satellite, and **per wilaya**. No headline number may be published without the south column beside it.
- C2 **Southern false-positive rate reported explicitly** and gated. A model that cannot separate Saharan flares from fire is not deployable, whatever its overall AUC.
- C3 Any stratum with `single_class: true` is reported as such, never as a passing metric.

### Gate D — Negative diversity
- D1 At least one non-flare negative mechanism present, OR an explicit written statement that the verifier's scope is night-time flare discrimination only.
- D2 `uncertain` rows stay excluded from training and are documented as such.

### Gate E — Model quality
- E1 Threshold chosen on **validation only**, never on train.
- E2 Validation contains both classes, or the selection metric is stated to be recall-only with that limitation documented.
- E3 Reported: ROC-AUC, PR-AUC, precision, recall, F1, Brier, ECE — overall **and** per stratum.
- E4 Event-level recall reported (median, p10, min); a single missed event must not be hidden by the median.
- E5 Feature-importance table published; no feature may be justified only by an era/region correlation.
- E6 sklearn version pinned and recorded in the artifact.

### Gate F — Deployment
- F1 A model loader and scorer exist in the serving path, unit-tested.
- F2 Inference feature assembly is a **single shared function** used by both training and serving, with a test asserting the two produce identical frames for identical input.
- F3 Feature schema **versioned** and stored in the artifact; serving verifies it matches and refuses on mismatch.
- F4 Model version string exposed in `AiResult.model`.
- F5 Dataset SHA verified **at serving time**, not only pre-deployment.
- F6 Threshold read from the artifact and verified, never hardcoded.

### Gate G — Fail-closed safety
Each of these must demonstrably yield `AI_UNAVAILABLE` (503, all fields `None`):

| Condition | Expected |
|---|---|
| No model registered | `AI_UNAVAILABLE` ✅ already true |
| Artifact file missing | `AI_UNAVAILABLE` ✅ already true |
| Artifact present but unreviewed | `AI_UNAVAILABLE` ✅ already true |
| Dataset SHA mismatch | ❌ **not implemented** |
| Feature schema mismatch | ❌ **not implemented** |
| Corrupted/unloadable artifact | ❌ **not implemented** |
| Missing feature at inference time | ❌ **not implemented** |

---

## 11. Recommended next engineering steps

Ordered so that each step is verifiable before the next begins. **No model training or
model selection is authorised by this audit.**

1. **Add southern non-flare positives.** This is the long pole and everything else waits on it. Requires new ground truth for at least one non-flare southern mechanism. Until then, scope the verifier honestly as *northern wildfire vs. gas flare* and label it that way in the UI.
2. **Adopt the geo-grouped folds** for model selection and reporting, and replace the fire-only validation split with one containing both classes (val recall currently unmeasurable for precision).
3. **Re-cut splits to be geo-disjoint**, then re-measure. Expect the honest score to drop; that drop is the point.
4. **Add per-wilaya stratified metrics** to `experiment.py`. Cheap, and it is what makes C1/C2 enforceable.
5. **Fix artifact provenance**: make `metrics.json` record `dataset_sha256`, then re-run `verify-artifact` on exp-v1. Expect it to pass the metric replay and fail the SHA until the SHA is recorded canonically.
6. **Build the inference path** behind the existing 503: loader, scorer, shared feature assembly, runtime schema/threshold/SHA verification — each fail-closed and unit-tested. Keep the endpoint returning `AI_UNAVAILABLE` until the gates above are met.
7. **Only then** train a candidate and evaluate it against Gates A–G. Registration remains a separate, explicitly approved change.

---

## 12. What this audit did not do

- Registered, activated, or deployed any model.
- Changed `/ai`, its status code, or its response shape.
- Modified the dataset, the split, the labels, the FIRMS pipeline, the database, or any CI.
- Modified frontend code.
- Changed `MODELS.md` or lowered any evaluation standard.
- Removed any difficult or negative example.

`/ai` remains `503 AI_UNAVAILABLE` with `probability`, `verified` and `model` all `None`.