# NUMIDIA EYE — feature verification tracker

**27 items. Status recorded against the running system, not against the code.**

A tick here is a claim that the feature was **exercised and observed**, with the
evidence recorded below it. An unticked item is not a failure — it is an item that
has not been proven yet, and it stays unticked until someone runs it.

Verification pass: **2026-10-09**, against `origin/main` @ `de84cc6`, API on port
8010, static site on 5500, `NUMIDIA_ACTIVE_MODEL=services/ml/models/verifier_v2`.

## Legend

| Status | Meaning |
|---|---|
| **VERIFIED** | Exercised against the running system; evidence recorded |
| **PARTIAL** | Exists, but does not meet the item as written |
| **NOT BUILT** | Does not exist. No claim is made for it anywhere |
| **BY DESIGN** | Deliberately excluded, with the reason stated |
| **FUTURE** | Acknowledged as planned; explicitly not claimed as working |

---

## 1. DETECT — 5/5 verified

| # | Item | Status | Evidence |
|---|---|---|---|
| 1.1 | Real NASA FIRMS / VIIRS detections | **VERIFIED** | `/system/status` → `firms=CONNECTED`, `data_state=LIVE`, 4,677 detections. Message: *"Live: freshly acquired VIIRS detections via FIRMS NRT API (VIIRS_NOAA21_NRT, VIIRS_SNPP_NRT, VIIRS_NOAA20_NRT); pipeline healthy."* |
| 1.2 | Interactive Algeria map with wilaya boundaries | **VERIFIED** | `apps/site/data/wilayas.geojson`, 48 features, confirmed parsing. Site serves HTTP 200 and renders on a blank MapLibre style with **no** external tile requests. |
| 1.3 | Detection markers, clustering, filtering | **VERIFIED** | Site renders detection + cluster layers; cluster counts via `querySourceFeatures`. Focus filters and writes `?wilaya=<code>`. |
| 1.4 | Detection details: coordinates, timestamp, satellite, FRP, confidence | **VERIFIED** | Live row carries `lat=30.37457`, `lon=7.0109`, `acq_datetime`, `satellite=N20`, `frp=4.09`, `confidence=0.6`, plus `instrument`, `confidence_raw`, `source_url`, `fetched_at`. |
| 1.5 | Data freshness, source status, ingestion health | **VERIFIED** | `/system/status` reports `firms`, `data_state`, `db`, and a human message. States enforced: LIVE / HISTORICAL / STALE / UNAVAILABLE. |

> Note on 1.4: fields are `lat`/`lon`, not `latitude`/`longitude`. Both present in
> the payload as raw FIRMS names.

## 2. VERIFY — 5/5 verified

| # | Item | Status | Evidence |
|---|---|---|---|
| 2.1 | Actual verifier-v2 model inference | **VERIFIED** | `/detections/{id}/ai` → `model=verifier-v2`, real `probability=0.9603744465852715`. Served value matches `predict_proba` (max abs diff 5.55e-17). |
| 2.2 | FIRE / NON_FIRE / UNCERTAIN outcomes | **VERIFIED** | Three-way classifier confirmed in code and exercised live (`FIRE` returned). Threshold `0.52`, non-fire threshold `0.3282`. |
| 2.3 | Real probabilities and verification status | **VERIFIED** | Live verdict returned genuine float probability, `verified`, `threshold`, `features_schema=live-v1`. |
| 2.4 | Artifact integrity + feature-schema validation | **VERIFIED** | `verify-artifact` → **9 checks, 9 PASS**, exit 0. `model.joblib` SHA-256 equals `manifest.model_sha256`. Tampered copy correctly refused (`UnavailableVerifier`, no probability). |
| 2.5 | Clear unavailable state when the model cannot run | **VERIFIED** | From a clean clone: HTTP **503**, `probability: null`, `model: null`, `prediction: null`, with a stated reason. Never a fabricated number. |

> **Known gap, reported not fixed:** the model is **not calibrated**
> (`calibrated: false`). A probability is a model score, not a literal confidence.
> See "Open issues" below.

## 3. UNDERSTAND — 4/4 verified

| # | Item | Status | Evidence |
|---|---|---|---|
| 3.1 | Group detections into incidents | **VERIFIED** | `/incidents` returns clusters with `detection_count`, `centroid_lat/lon`. Observed incident `INC-b965af56079e`, 13 detections. |
| 3.2 | Incident timeline and supporting observations | **VERIFIED** | `first_acq=2026-10-09T00:52Z`, `last_acq=2026-10-09T13:08Z`, `persistence_hours=12.267`, `satellites`, `wilayas`. |
| 3.3 | Location, wilaya, source, signal information | **VERIFIED** | Centroids, `wilaya_code`/`wilaya_name` per detection, `source` and `source_url` provenance retained per row. |
| 3.4 | Incident detail with traceable evidence | **VERIFIED** | `/incidents/{id}` returns `verification`, `priority` (with factors), `sources`, `provenance`. |

## 4. PRIORITISE — 2 verified, 1 partial, 1 not built

| # | Item | Status | Evidence |
|---|---|---|---|
| 4.1 | Existing priority-v1 assessment and score | **VERIFIED** | `priority.level` and `priority.score` computed by `priority-v1`, rule-based, **no model input**. |
| 4.2 | Explainable contributing factors and evidence | **VERIFIED** | 4 factors returned with `value`, `normalized`, `weight` — e.g. `thermal_intensity` value 3.59 / norm 0.3302 / weight 0.4; `persistence` 12.267 / 0.1704 / 0.25; `detection_count` 13 / 0.65 / 0.2. Score re-derivable by hand. |
| 4.3 | Environmental context when validated and available | **NOT BUILT** | Confirmed absent: the strings `environment` and `weather` appear in **neither** the `/incidents` payload **nor** the report. No wind, humidity, temperature or soil moisture anywhere. `priority.unavailable_factors` is the honest empty state today. |
| 4.4 | Explicit uncertainty and missing-data handling | **VERIFIED** | `priority.unavailable_factors` and `priority.methodology` present. GIS context beyond wilaya is reported `UNAVAILABLE` with a reason rather than filled. |

## 5. RESPOND — 2 verified, 1 partial, 1 future

| # | Item | Status | Evidence |
|---|---|---|---|
| 5.1 | Automatically generated incident reports | **VERIFIED** | `GET /incidents/{id}/report` → `INC-b965af56079e`. Returns `incident_id`, `generated_at`, detection stats, `verification`, `gis_context`, `priority`, `sources`, `limitations`, `provenance`. |
| 5.2 | Report evidence, timestamps, and limitations | **VERIFIED** | `limitations` and `provenance` blocks are present in every report. |
| 5.3 | Incident status and response workflow | **PARTIAL** | Incidents carry a `status` field, but there is **no workflow**: no transitions, no assignment, no acknowledgement, no state history. |
| 5.4 | Authorized notifications | **FUTURE** | **No notification is sent, simulated, or faked anywhere.** Alerts are labelled prototype-only and explicitly not Civil Protection. Correct as-is; must stay that way until an authority integrates. |

## 6. PRODUCT & OPERATIONS — 4 verified, 1 partial

| # | Item | Status | Evidence |
|---|---|---|---|
| 6.1 | English and Arabic interface | **PARTIAL** | `apps/web` has full EN/AR i18n including the `ar:` dictionary and RTL strings. `apps/site` is **English-only by explicit requirement** — no Arabic, no RTL toggle. Both are intentional; the item is met by `apps/web` only. |
| 6.2 | Responsive, polished competition-ready UI | **VERIFIED** | 5-stage chain rail, incident panel, 3-column console, deep-pine palette. 98 frontend tests, production build green. |
| 6.3 | Backend/API health and truthful live/stale status | **VERIFIED** | `/health`, `/system/status`. Fail-closed verified from a clean clone. Truthful degradation on missing credential/artifact/database. |
| 6.4 | Reliable startup instructions, reproducible setup | **VERIFIED** | `docs/SETUP.md`. Clean-clone script `scripts/verify_clean_clone.ps1` → **PASS**, twice, no leaked processes. |
| 6.5 | Error handling, tests, security, deployment readiness | **PARTIAL** | 207 backend + 98 frontend tests. No secrets in Git (verified across every commit). **Gaps:** no CI pipeline, no deployment target defined, no monitoring, and `/ai` returns HTTP 500 on an uninitialised database (see below). |

---

## Score: 22 verified · 2 partial · 1 not built · 1 future · 1 by design

## Open issues found during this pass

1. **Model is not calibrated** (`calibrated: false`). Probabilities are scores, not
   literal confidences. Highest remaining risk of the AI being *misread* rather than
   being wrong. Fixable by calibrating, or by relabelling the field.
2. **`/ai` can return HTTP 500 — but only in tests, not in operation.**
   `sqlite3.connect()` creates a database *file* without the schema. If the app is
   then driven as `TestClient(app)` **without the context manager**, the lifespan
   never runs, the schema is never initialised, and `get_detection_row()` raises
   `sqlite3.OperationalError` → 500 instead of a truthful response.

   **Not reachable under uvicorn**, where the lifespan runs and
   `CREATE TABLE IF NOT EXISTS` initialises the schema; there `/ai` returns a clean
   404. Verified both ways. An earlier note in this file called this a production
   bug — that was an overstatement, corrected here.

   It is worth hardening anyway (defence in depth), but it is not an incident.
3. **Southern-fire validation unresolved.** 0 confirmed positives in the labels;
   southern metrics recorded `UNAVAILABLE`, never as a number.
4. **No incident workflow** (5.3). A `status` field with no transitions is not a
   response capability.
5. **Environmental intelligence absent** (4.3). The single largest genuine gap, and
   the highest-value thing to build next — real, keyless, and additive.

## Not claimed anywhere in this repository

Safe-road routing · evacuation advice · shelter availability · authorised
notification · nationwide validation · Civil Protection integration. All are
roadmap items. See `README.md` → "Planned, not implemented".