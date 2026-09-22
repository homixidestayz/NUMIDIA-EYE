# NUMIDIA EYE — cloud training workflow

**Scope: EXPERIMENTAL tabular baselines only. Nothing here registers a model.
The live API stays `503 AI_UNAVAILABLE` until the registration gate in
`services/ml/MODELS.md` is satisfied by explicit approval.**

## Why cloud

The reference laptop cannot train. Cloud (Colab/Kaggle CPU) runs the exact
same versioned code and frozen V2 dataset. No GPU is needed for the sklearn
baseline (CPU runtime, minutes); GPU runtimes only matter for the future
Sentinel-2 vision experiment (`services/ml/vision/`).

## Reproducibility contract

Every run must record four things (the notebook prints all of them):

1. **Code commit** — `git rev-parse HEAD` inside the clone.
2. **Dataset SHA** — verified automatically against `data/labels/manifest_v2.json`
   before training starts (mismatch = hard stop).
3. **Package versions** — printed by the env cell and stored in the experiment
   `config.json` (`sklearn_version` included).
4. **Seed** — fixed at 42 in `services/numidia_ml/experiment.py`.

`joblib` artifacts are portable across machines but sensitive to major
`scikit-learn` version changes: always run `verify-artifact` on bring-back
(see below). A version mismatch does not silently pass — metric comparison
fails loudly beyond tolerance.

## Option A — Google Colab (recommended)

1. Runtime → **CPU** (no GPU needed for the baseline).
2. Upload or open `notebooks/numidia_cloud_train.ipynb`.
3. Run all cells top to bottom. Expected: clone → pip install → dataset SHA
   check → `python -m numidia_ml.cli experiment` (train → val-select →
   test-once) → metrics display → `numidia_exp_cloud.tar.gz` downloads.
4. Copy the printed **commit SHA**, **dataset SHA**, and **test metrics** into
   your run notes.

## Option B — Kaggle

1. New Notebook, enable **Internet** (Settings → Internet ON), CPU accelerator.
2. Upload `notebooks/numidia_cloud_train.ipynb` (File → Import) or paste cells.
3. Replace `/content` paths only if needed — defaults work (`/content` exists
   on Kaggle too when internet notebooks run; otherwise use `/kaggle/working`
   for `--out` and the tarball, then download from the Output tab).
4. Same reproducibility contract as Colab.

## What a run produces (inside the tarball)

- `<model>_exp-v1.joblib` — fitted sklearn Pipeline (preprocessing + classifier).
- `metrics.json` — full record: selection, test-once metrics, stratified
  metrics, event recall, feature contract, dataset SHA, sklearn version.
- `calibration.csv`, `feature_importance.csv`, `config.json`.
- `model-experiment-cloud.md` — human-readable report.

## Bring-back procedure (mandatory, read-only)

1. Extract the tarball locally (do NOT place anything under
   `services/ml/models/` yet except a quarantine folder):
   `services/ml/models/candidates/<run-name>/`.
2. Run verification (never registers anything):
   `uv run python -m numidia_ml.cli verify-artifact --artifact services/ml/models/candidates/<run-name>/<model>_exp-v1.joblib --dataset data/labels/firms_labels_v2.csv --metrics services/ml/models/candidates/<run-name>/metrics.json`
3. Require `PASS` on every check (feature contract, dataset SHA, recomputed
   test metrics within tolerance).
4. Open a review: compare stratified rows (north band, night slice) against
   `docs/model-experiment-v1.md`. Registration needs a separate explicit
   approval — see `services/ml/MODELS.md`.

## Cost / time guidance

- V2 supervised rows (~43k) × 11 features: RandomForest(300) / HGB(300) train
  in minutes on Colab CPU; peak RAM well under 2 GB. No huge downloads: the
  repo clone (~25 MB incl. dataset) plus pip wheels is everything.
- Do NOT pull FIRMS history or ground truth in the cloud: the frozen,
  committed V2 CSV is the only training input.

## Troubleshooting

- `ModuleNotFoundError: numidia_ml` → the `PYTHONPATH=.../services` prefix on
  the experiment command is required (no `pip install -e .` needed).
- Dataset SHA mismatch → stop; re-clone pristine (notebook asserts clean
  `git status`); never train on an edited CSV.
- `verify-artifact` metric drift beyond tolerance → almost always a major
  scikit-learn version difference; record both versions, retrain with a
  pinned version if bitwise parity is required.
