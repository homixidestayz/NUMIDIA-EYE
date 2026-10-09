# NUMIDIA EYE — model registry

## Registered: `verifier-v2` (EXPERIMENTAL)

`verifier-v2` is registered and serving. With `NUMIDIA_ACTIVE_MODEL` pointed at
`services/ml/models/verifier_v2`, `/ai` returns real FIRE / NON_FIRE / UNCERTAIN
verdicts over live VIIRS features, with threshold `0.52`.

| | |
|---|---|
| Artifact | `services/ml/models/verifier_v2/model.joblib` (48,569,963 bytes) |
| Dataset | `data/labels/firms_labels_v2.csv` — 53,615 rows, SHA-pinned in `manifest_v2.json` |
| Test split | n=20,716 (10,323 fire / 10,393 non-fire) |
| Test metrics | ROC-AUC 0.9496 · PR-AUC 0.9568 · precision 0.9361 · recall 0.8085 · F1 0.8676 · Brier 0.0905 · ECE 0.037 · not calibrated |
| Provenance / attribution | `MODEL_LICENSE.md` |

**What it is not.** These metrics are not a claim of Algerian wildfire detection.
The labels contain **no independently confirmed southern Algerian wildfire
positive**, so southern ROC-AUC, precision, recall and F1 are recorded
`UNAVAILABLE` rather than as numbers. The negative class is predominantly
catalogued gas flare, so the model is closer to a flare-vs-wildfire
discriminator than a general fire detector. It has not been validated nationwide
and is not integrated with Civil Protection. The authoritative statement is the
`scope` field in `services/ml/models/verifier_v2/manifest.json`, returned verbatim
with every served verdict.

With `NUMIDIA_ACTIVE_MODEL` unset or pointing nowhere, `/ai` returns
`503 AI_UNAVAILABLE` with every model field `null` — including `probability`.
That is the deliberate fail-closed default.

The artifact is re-verified on every load (contract, dataset SHA, metric replay
against `metrics.json`). A mismatched or tampered artifact is refused and no
probability is served. Observed 2026-10-09: `verify-artifact` 9 checks, 9 PASS.

## Candidates (experimental, not registered)

| artifact | status | test summary | location |
|---|---|---|---|
| `hgb_exp-v1.joblib` (exp-v1, superseded) | EXPERIMENTAL — not registered | ROC-AUC 0.9175 · PR-AUC 0.9353 · F1 0.7524 · north F1 0.96 / south precision 0 | `services/ml/models/exp_v1/` (gitignored) |

Full results: `docs/model-experiment-v1.md`. Known decisive limitation: the
model cannot separate Saharan flares (south precision 0.000) — see the
stratified rows before trusting aggregates.

Cloud candidates land under `services/ml/models/candidates/<run-name>/`
(quarantine) and must pass `verify-artifact` before any review. Quarantine
is NOT registration.

## Live inference contract

`services/numidia_ml/inference.py` is the production boundary:

```
NASA FIRMS NRT API -> normalize -> derive_features -> build_inference_features
                                                           -> verifier.verify()
```

The contract is `LIVE_INFERENCE_FEATURES`, derived from
`labels.MODEL_FEATURES_V1` so training and serving cannot drift apart:

`bright_ti4, bright_ti5, f_bt_diff, frp, f_frp, confidence, f_confidence,
scan, track, satellite`

`type` is excluded: present in historical archives, null in every live NRT
detection and in the whole 2026 test cohort, so it identifies the split rather
than the physics. It is never imputed and its absence is never used as a signal.
A detection carries many columns that are deliberately *not* features (`lat`,
`lon`, `wilaya_name`, `f_month`, `type`, …); they are ignored, not rejected.

SQLite is an operational cache and history, not the AI's source of truth.
`features_from_live_frame()` scores a live FIRMS frame with no database in the
loop.

`load_verifier()` returns a verified `verifier-v2` verifier when
`NUMIDIA_ACTIVE_MODEL` is set and the artifact passes verification; otherwise it
returns `UnavailableVerifier`, which raises `VerifierUnavailable` rather than
returning a probability. `verify_detections()` propagates that failure rather than
returning partial results, so a caller can never mistake a failed run for a
successful one.

## Registration gate (all required, in order)

1. Candidate passes `verify-artifact` (contract + SHA + metric replay).
2. Stratified review approved (north band, night slice, events) against the
   current experiment report.
3. Explicit user approval naming the exact artifact file + threshold.
4. `NUMIDIA_ACTIVE_MODEL` pointed at the artifact AND the `/ai` gate
   deliberately flipped (separate change, separate commit).
5. Post-registration smoke test on live detections with logged probabilities.

This gate was satisfied for `verifier-v2` on 2026-10-09: it passed
`verify-artifact` (9/9, observed), the stratified review is recorded in
`docs/model-experiment-v1.md`, and the founder approved the exact artifact file
and threshold 0.52. Steps 4 and 5 remain the standing requirement for any future
candidate: **until its gate is satisfied in full, no probabilities are served
anywhere, by anyone, for any reason.**
