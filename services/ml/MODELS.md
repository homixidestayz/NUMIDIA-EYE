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

## Registration gate (all required, in order)

1. Candidate passes `verify-artifact` (contract + SHA + metric replay).
2. Stratified review approved (north band, night slice, events) against the
   current experiment report.
3. Explicit user approval naming the exact artifact file + threshold.
4. `NUMIDIA_ACTIVE_MODEL` pointed at the artifact AND the `/ai` gate
   deliberately flipped (separate change, separate commit).
5. Post-registration smoke test on live detections with logged probabilities.

Until then: no probabilities are served anywhere, by anyone, for any reason.
