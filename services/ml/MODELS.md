# NUMIDIA EYE — model registry

## Registered for production: NONE

The live API (`/ai`) returns `503 AI_UNAVAILABLE`. No model file, threshold,
or probability is wired into any serving path.

## Candidates (experimental, local-only, gitignored)

| artifact | status | test summary | location |
|---|---|---|---|
| `hgb_exp-v1.joblib` (exp-v1, local run) | EXPERIMENTAL — not production | ROC-AUC 0.9175 · PR-AUC 0.9353 · F1 0.7524 · north F1 0.96 / south precision 0 | `services/ml/models/exp_v1/` (gitignored) |

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

`load_verifier()` currently returns `UnavailableVerifier`, which raises
`VerifierUnavailable` rather than returning a probability. `verify_detections()`
propagates that failure rather than returning partial results, so a caller can
never mistake a failed run for a successful one.

## Registration gate (all required, in order)

1. Candidate passes `verify-artifact` (contract + SHA + metric replay).
2. Stratified review approved (north band, night slice, events) against the
   current experiment report.
3. Explicit user approval naming the exact artifact file + threshold.
4. `NUMIDIA_ACTIVE_MODEL` pointed at the artifact AND the `/ai` gate
   deliberately flipped (separate change, separate commit).
5. Post-registration smoke test on live detections with logged probabilities.

Until then: no probabilities are served anywhere, by anyone, for any reason.
