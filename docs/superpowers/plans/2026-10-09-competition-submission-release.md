# Competition Submission Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a fresh `git clone` of NUMIDIA EYE installable, runnable on port 8010, populated with real FIRMS data without any credentials, and documented so that no README claim contradicts the shipped verifier-v2.

**Architecture:** This is a release-engineering change, not a feature change. Nothing under `services/numidia_core`, `numidia_ml`, `numidia_intel`, `numidia_api` is modified — `verifier_v2`'s manifest pins `source_code_sha256` for `verifier_split.py`, `verifier_train.py`, `verifier_model.py`, `inference.py` and `labels.py`, and `verify_artifact` replays metrics against the dataset SHA, so touching those files would invalidate the artifact contract. The work is confined to documentation, `.gitignore`, one vendored licence file, and git operations.

**Tech Stack:** Python 3.12 + `uv` (FastAPI API on port 8010), Node ≥18 (`apps/web` React dashboard), plain static server for `apps/site` on port 5500, Git.

**Spec:** The four-phase release brief given in-session on 2026-10-09 (inspect/protect, fresh-clone reproducibility, documentation and licensing, clean-clone verification).

## Global Constraints

- **No modification** to `services/numidia_core/*`, `services/numidia_ml/*`, `services/numidia_intel/*`, `services/numidia_api/*`, `services/numidia_worker/*`, `apps/web/src/*`, or `tests/*`. Reason: `services/ml/models/verifier_v2/manifest.json` pins `source_code_sha256` over five of those files, and the freeze on verifier-v2 semantics is a standing project constraint.
- **No** retraining, no new model registration, no label changes, no database rewrites, no fabricated results.
- **Never** commit `.env`, `FIRMS_MAP_KEY`, `data/db/*`, or `data/raw/firms/*`. Enforced by `.gitignore`; re-checked in Task 1 and Task 7.
- **Never** run `git add .`, `git reset`, `git clean`, or `git push --force`.
- **Never** touch the untracked zero-byte `git` file at repo root. It is pre-existing and unrelated.
- **Fail closed**: any missing credential, artifact or data must produce a truthful `UNAVAILABLE`/`503`, never a placeholder value.
- **No overclaiming**: the word "national validation" must never be applied to this verifier. The authoritative scope string is `scope` in `services/ml/models/verifier_v2/manifest.json`, quoted verbatim in every corrected document.
- API port for all documentation is **8010**, not 8000.
- Unresolved southern-fire validation (0 positives across 9,869 southern test rows) must be stated as an open limitation wherever verifier performance is described.

## Review Focus

Conditions this spec implies but no existing test covers. Each gets a check in the task that owns it.

1. **A judge with no `FIRMS_MAP_KEY`.** Expected: the API starts, reports `firms=UNAVAILABLE`, and the site shows a truthful empty-data state — not an error page, not zeros presented as counts. Pinned by Task 3 Step 5.
2. **A judge with no model artifact.** Expected: `/ai` returns `503 AI_UNAVAILABLE` with no `probability` key, and every UI chip reads `Unavailable`. Already enforced in code; pinned by Task 7 Step 6.
3. **`data/db/` accidentally staged.** Expected: the commit contains no `*.db`, `*.db-wal`, `*.db-shm`. Pinned by Task 1 Step 3.
4. **A judge reading the README before running anything.** Expected: every capability claim is true of a fresh clone. Pinned by Task 5 Step 4, which greps for the four known stale strings and asserts zero matches.
5. **Redistribution of the 48.5 MB artifact and the VNF-derived labels.** Expected: not redistributed without a licence decision. Pinned by Task 4 Step 3 and Task 6.

---

## File Structure

**Modified (tracked):**
- `README.md` — remove four stale claims, add `apps/site`, correct port, correct roadmap.
- `.env.example` — remove false "runs offline on the committed historical sample" claim; set port 8010.
- `services/ml/MODELS.md` — "Registered for production: NONE" is false; correct the registry section only.
- `apps/site/provenance.md` — "Application code: MIT" asserts a licence that was never granted; correct it.
- `apps/web/package-lock.json` — currently gitignored; must be tracked to pin frontend deps.
- `.gitignore` — negate `services/ml/models/verifier_v2/*` for provenance files only, and stop ignoring `apps/web/package-lock.json`.

**Created:**
- `docs/SETUP.md` — the authoritative clone→demo path, including the no-key archive route.
- `docs/licensing.md` — source-by-source licence inventory and the open redistribution question.
- `apps/site/vendor/LICENSE-maplibre.txt` — BSD-3-Clause text required to redistribute MapLibre GL JS v4.7.1.
- `scripts/verify_clean_clone.ps1` — repeatable Phase 4 check.

**Committed as-is (untracked today):** the 10 files of `apps/site/`.

---

### Task 1: Protect and commit `apps/site/`

**Files:**
- Add: `apps/site/` (10 files, 1,600,685 bytes — `wilayas.geojson` 666,143; `site.js` 34,588; `vendor/maplibre-gl.js` 803,086; `vendor/maplibre-gl.css` 65,534; `site.css` 15,011; `README.md` 3,886; `llms.txt` 3,972; `provenance.md` 3,354; `index.html` 3,544; `index.md` 1,567)
- Test: `tests/` (unchanged — run as a regression gate)

**Interfaces:**
- Consumes: nothing.
- Produces: commit `A` on `main`, parent `6a2b62c`. Working tree clean except the untracked `git` file.

- [ ] **Step 1: Record the pre-commit baseline**

Run: `uv run pytest -q 2>&1 | Select-Object -Last 3`
Expected: `207 passed` (baseline at `6a2b62c`). If it is not 207, stop and report the delta — do not commit on a regression.

Run: `cd apps/web; npm test 2>&1 | Select-Object -Last 5`
Expected: `98 passed` (`vitest run`). If not 98, stop and report.

- [ ] **Step 2: Confirm nothing dangerous is inside `apps/site/`**

Run:
```
git check-ignore -q apps/site/site.js; echo "ignored=$?"
```
Expected: `ignored=1` (not ignored — merely untracked).

Run a secret scan over the directory, excluding `vendor/`:
```
Get-ChildItem -Recurse -File apps/site -Exclude *.geojson |
  Where-Object { $_.FullName -notmatch 'vendor' } |
  Select-String -Pattern 'MAP_KEY|api[_-]?key|secret|token|password|Bearer\s+[A-Za-z0-9]|AKIA[0-9A-Z]{16}|-----BEGIN'
```
Expected: zero matches. The one historical hit was `vendor/maplibre-gl.js:42`, a minified trigonometry `token` variable — not a credential, and excluded here.

- [ ] **Step 3: Stage exactly the ten files and prove no database is included**

Run:
```
git add apps/site/index.html apps/site/site.js apps/site/site.css apps/site/index.md apps/site/README.md apps/site/llms.txt apps/site/provenance.md apps/site/data/wilayas.geojson apps/site/vendor/maplibre-gl.js apps/site/vendor/maplibre-gl.css
git diff --cached --name-only
```
Expected: exactly those ten paths, no `data/db`, no `*.db`, no `.env`, and **not** the root `git` file.

Run: `git diff --cached --stat | Select-Object -Last 3`
Expected: 10 files changed, ~1,600,685 insertions. Every file under GitHub's 100 MB single-file limit.

- [ ] **Step 4: Commit**

```
git commit -m "feat(site): add standalone Algeria wildfire map surface

English-only static app over the live API. Blank MapLibre style with no
basemap source, so no neighbouring country can render and the page makes
zero external network requests. Wilaya boundaries are a display-only
Douglas-Peucker simplification of data/gis/algeria_wilayas.geojson.
Includes llms.txt and per-layer provenance/terms."
```
Expected: commit `A` created, 10 files.

- [ ] **Step 5: Confirm the working tree is clean and the audit file stayed ignored**

Run: `git status --short`
Expected: `?? git` only. The `data/raw/firms/viirs_algeria_audit_*.csv` written by the archive test must **not** appear.

---

### Task 2: Verify the remote, then push

**Files:** none modified.
**Interfaces:**
- Consumes: commit `A` from Task 1.
- Produces: `origin/main` == local `main`.

- [ ] **Step 1: Confirm the remote URL is the intended repository**

Run: `git remote -v; git config --get user.name; git config --get user.email`
Expected: `https://github.com/homixidestayz/NUMIDIA-EYE.git` (fetch and push). Report `user.name`/`user.email` verbatim — if either is unset or not the team account, **stop**; do not push under an unknown identity.

- [ ] **Step 2: Fetch and re-check divergence before pushing**

Run:
```
git fetch origin
git rev-list --count origin/main..HEAD
git rev-list --count HEAD..origin/main
```
Expected: `3` ahead, `0` behind. Any non-zero "behind" means the remote moved — **stop and report**, and do not push.

- [ ] **Step 3: Review exactly what will land on the remote**

Run: `git log --format='  %h %ad %s' --date=short origin/main..HEAD`
Expected exactly three commits: `bd96a55 feat(ml): ship live wildfire verifier`, `6a2b62c feat(ui): polish competition wildfire intelligence demo`, and `A feat(site): add standalone Algeria wildfire map surface`.

Run: `git diff --stat origin/main..HEAD | Select-Object -Last 3`
Expected: 13 files changed, ~1,601,000 insertions.

- [ ] **Step 4: Push without force**

Run: `git push origin main`
Expected: fast-forward, `main -> main`. If rejected, **stop and report**; do not retry with `--force`.

- [ ] **Step 5: Confirm the push**

Run: `git rev-parse HEAD; git rev-parse origin/main`
Expected: identical hashes.

---

### Task 3: Document the reproducible path from a fresh clone

**Files:**
- Create: `docs/SETUP.md`
- Test: `scripts/verify_clean_clone.ps1` (created in Task 7, referenced here)

**Interfaces:**
- Consumes: the archive-fetch behaviour proven in this session — `uv run python -m numidia_worker.cli --db <path> fetch --mode archive` returns `status: ok`, `new: 888`, `total: 888`, no key, and writes a 444 KB SQLite database whose `verification` block names `verifier-v2` and carries the manifest `scope` string.
- Produces: `docs/SETUP.md`, the single document a judge is pointed at from `README.md` and `apps/site/README.md`.

- [ ] **Step 1: Write the failure this document exists to prevent, at the top**

`docs/SETUP.md` opens with the verified fact: on a clean clone there is no database and no model artifact, and both are restored by two documented commands. Include the measured evidence — a clone contains 111 files, no `.env`, no `data/db/`, no `model.joblib`.

- [ ] **Step 2: Prerequisites and install**

Python `>=3.12,<3.14` (from `pyproject.toml`), Node ≥18 for `apps/web`, `uv`. Give:
```
uv sync --extra api --extra ml --extra dev
```
Note that `--extra ml` is required only for the model rebuild path and for `numidia_ml` CLI commands.

- [ ] **Step 3: The two run modes, with the no-key route first**

Order the document so the credential-free path comes first, because it is the one that works for every judge.

**Route A — no credentials (works for everyone):**
```
uv run python -m numidia_worker.cli --db data/db/numidia.db fetch --mode archive
```
State the verified result: `status: ok`, `new: 888`, `total: 888`, 444 KB database, pulls the three public `*_C2_Global_24h.csv` files from `firms.modaps.eosdis.nasa.gov`. State that these are rolling global files, so row counts will differ from the numbers quoted here and that is expected.

**Route B — live NRT with a key:** get a free key at `https://firms.modaps.eosdis.nasa.gov/api/map_key/`, write it to `.env` as `FIRMS_MAP_KEY=...`, never commit it, then `uv run python -m numidia_worker.cli fetch`. State that this is what upgrades `data_state` from `HISTORICAL` to `LIVE`.

- [ ] **Step 4: API and site startup on the agreed ports**

```
uv run uvicorn numidia_api.app:app --host 0.0.0.0 --port 8010
python -m http.server 5500 --bind 0.0.0.0     # from apps/site
```
Add the note that port 8010 is the project default because 8000 is occupied by another service on the reference machine, and that `apps/site/site.js` reads `API_PORT = 8010`, overridable with `?api=<port>` or `window.NUMIDIA_API_BASE`.

Also give the `apps/web` route: `cd apps/web && npm ci && npm run dev`.

- [ ] **Step 5: State what each missing piece actually does — verified, not asserted**

A table with one row per missing dependency, each carrying the observed behaviour:

| Missing | Observed behaviour |
|---|---|
| `.env` / `FIRMS_MAP_KEY` | scheduler records `skipped`; `/system/status` reports a non-`LIVE` state; no invented data |
| `data/db/` | `/detections` returns an empty set; site renders the 48 wilayas with no detections and says so |
| `model.joblib` | `/detections/{id}/ai` → `503 AI_UNAVAILABLE`, **no** `probability` field; chips read `AI verifier Unavailable` |
| `NUMIDIA_ACTIVE_MODEL` | as above — an unset variable is the fail-closed path, not an error |

Mark each row as verified in this session or as asserted, honestly. Do not claim verification for behaviour not observed.

- [ ] **Step 6: Link it from `README.md` and `apps/site/README.md`**

Both must point at `docs/SETUP.md`. `apps/site/README.md` already documents a run path; reconcile it rather than leaving two versions.

---

### Task 4: Resolve model-artifact acquisition without assuming redistribution

**Files:**
- Modify: `.gitignore`
- Add (tracked): `services/ml/models/verifier_v2/manifest.json` (1,750 B), `config.json` (16,882 B), `metrics.json` (75,072 B), `calibration.csv` (332 B), `feature_importance.csv` (411 B)

**Interfaces:**
- Consumes: the licence findings in Task 6.
- Produces: the tracked provenance bundle (~94 KB) and a documented, unexecuted rebuild path.

- [ ] **Step 1: Record the investigation finding before changing anything**

Write down, with the URLs, that `verifier-v2`'s negative class is predominantly catalogued gas flare drawn from EOG VIIRS Nightfire annual flare files for 2020–2024, listed in `data/labels/manifest_v2.json` under `ground_truth` with their SHA-256s. State that EOG's licensing page says that **effective 2025-01-10** all VNF data moved to a per-year Data Use License, and that EOG's own CC licence PDF covers *select subsets* of VNF under CC BY 4.0. Those files predate the change, but whether that extends to redistribution of a derived model is a legal determination this project has not made.

- [ ] **Step 2: Do not commit `model.joblib`**

48,569,963 bytes, excluded. State the reason in `docs/licensing.md` as an open question for the team, with the two named options: redistribute under an explicit licence, or rebuild from the committed labels.

- [ ] **Step 3: Track the provenance bundle only**

Add negations to `.gitignore` **after** the existing `services/ml/models/*` rule:
```
services/ml/models/*
!services/ml/models/verifier_v2/
services/ml/models/verifier_v2/*
!services/ml/models/verifier_v2/manifest.json
!services/ml/models/verifier_v2/config.json
!services/ml/models/verifier_v2/metrics.json
!services/ml/models/verifier_v2/calibration.csv
!services/ml/models/verifier_v2/feature_importance.csv
```
Run: `git check-ignore -v services/ml/models/verifier_v2/model.joblib`
Expected: still ignored. Run: `git check-ignore -v services/ml/models/verifier_v2/manifest.json`
Expected: no match (not ignored).

- [ ] **Step 4: Document the rebuild path, and mark it unexecuted**

`services/numidia_ml/verifier_train.py` exposes `train(dataset_path, out_dir, *, models=("hgb","rf","et"), calibrate=True)` and **has no `argparse`/`__main__` entry point** — `services/numidia_ml/cli.py` states "No model is trained or registered here" and exposes no `train` subcommand. So the rebuild is a library call:

```
uv run --extra ml python -c "from numidia_ml.verifier_train import train; train('data/labels/firms_labels_v2.csv', 'services/ml/models/verifier_v2')"
```

Document it **labelled as not executed in this release**, because retraining is out of scope. Do not add a CLI subcommand — that would modify a frozen module and `verifier_train.py` is SHA-pinned in the artifact manifest.

Record the honest limitation plainly: a rebuild is expected to reproduce the dataset linkage exactly, but byte-identical `model.joblib` output additionally depends on scikit-learn version, which `pyproject.toml` floors only (`>=1.5`) and `uv.lock` would pin. Reproducing the exact `model_sha256` is therefore **unverified**.

- [ ] **Step 5: Verify the tracked bundle is genuinely the one the verifier serves**

Run: `git add` the five files, then compare `git show :services/ml/models/verifier_v2/manifest.json` against the working copy — must be identical.
Run: `uv run python -m numidia_ml.cli verify-artifact --artifact services/ml/models/verifier_v2 --dataset data/labels/firms_labels_v2.csv`
Expected: 9/9 checks pass (the count verified in this session).

---

### Task 5: Correct every documentation claim that contradicts verifier-v2

**Files:**
- Modify: `README.md`, `.env.example`, `services/ml/MODELS.md`, `apps/site/provenance.md`
- Test: a grep assertion (Step 4)

**Interfaces:**
- Consumes: the `scope` string from `services/ml/models/verifier_v2/manifest.json`; the port decision from Task 3; the licence finding from Task 6.
- Produces: docs that match the shipped behaviour.

- [ ] **Step 1: `README.md` — remove the four stale claims**

Replace the block at lines 5–8, which says *"AI verification is **unavailable** and stays that way until a properly evaluated model is registered"* — false, `verifier-v2` is registered and serving.

In the architecture diagram, replace *"ML hook: trained verifier runs here once it exists / (today: explicit 503 AI_UNAVAILABLE - never faked)"* with a statement that the verifier runs here and that `AI_UNAVAILABLE` is the response when the artifact is absent.

In the layer table, replace the row *"| Trained AI verifier | **none registered** - `/ai` returns `503 AI_UNAVAILABLE`"* with the registered artifact, and delete the *"| API boundary | ... AI + incidents explicit `UNAVAILABLE` |"* implication that incidents are unavailable.

- [ ] **Step 2: `README.md` — correct the other stale rows and the roadmap**

The dashboard row says *"build unverified here (no Node toolchain in this env)"* — update to the measured result (98 frontend tests, production build green). The roadmap still reads *"labels decision → train verifier → wire `/ai`"* — those are done; mark them complete and move the open items up, with the unresolved southern-fire validation named as the blocking item.

- [ ] **Step 3: `.env.example` and `apps/site/provenance.md`**

`.env.example` line 2 claims *"the project runs offline on the committed historical sample"*. There is no such sample — `data/db/` is gitignored and the committed CSVs are training labels, not runtime detections. Replace with a pointer to `docs/SETUP.md` Route A. Also set `NUMIDIA_API_PORT=8010`.

`apps/site/provenance.md` ends with *"Application code: MIT."* No `LICENSE` file exists and no licence has been granted, so this asserts rights nobody has established. Replace with a pointer to `docs/licensing.md` and state that no project licence has been granted yet.

- [ ] **Step 4: `services/ml/MODELS.md` — correct the registry header only**

*"## Registered for production: NONE"* and *"The live API (`/ai`) returns `503 AI_UNAVAILABLE`. No model file, threshold, or probability is wired into any serving path."* are both false. Also *"load_verifier() currently returns `UnavailableVerifier`"* is false on the serving path. Update these three statements. **Leave the registration gate and the inference contract sections alone** — they are correct and describe real safeguards.

- [ ] **Step 5: Assert no stale string survives**

Run:
```
git grep -n -E 'none registered|once it exists|registered for production: NONE|stays that way until|runs offline on the committed historical sample|Application code: MIT' -- '*.md' '.env.example'
```
Expected: **zero matches.** Any hit is an uncorrected contradiction.

- [ ] **Step 6: Assert the scope limitation is stated everywhere verifier performance is described**

Run:
```
git grep -c -i 'southern' -- README.md services/ml/MODELS.md docs/SETUP.md
```
Expected: all three contain the term. Confirm each mentions the 0-positives finding and that none of them pairs it with a claim of nationwide validation.

---

### Task 6: Licensing — inventory the terms, propose no rights

**Files:**
- Create: `docs/licensing.md`
- Create: `apps/site/vendor/LICENSE-maplibre.txt`
- Modify: `.gitignore` (remove `apps/web/package-lock.json` from the ignore list)

**Interfaces:**
- Consumes: the licence findings in Task 4 Step 1.
- Produces: the evidence base the team needs to make the licence decision this plan deliberately does not make.

- [ ] **Step 1: Add the required MapLibre BSD-3-Clause text**

`apps/site/vendor/maplibre-gl.js` is MapLibre GL JS **v4.7.1**; its own header says *"3-Clause BSD. Full text of license: https://github.com/maplibre/maplibre-gl-js/blob/v4.7.1/LICENSE.txt"*. Redistributing it without the licence text is a redistribution defect. Fetch that exact URL at the `v4.7.1` tag and save it to `apps/site/vendor/LICENSE-maplibre.txt`. Verify the saved file's first line reads `Copyright (c) 2018-2024 MapLibre Authors` or similar — if the fetch fails, stop and report rather than reconstructing the text from memory.

- [ ] **Step 2: Inventory the Python and npm dependency licences from installed metadata, not memory**

For each package in `pyproject.toml` and `apps/web/package.json`, read the installed distribution metadata and record its declared licence. Do not copy licence names from prior knowledge — a wrong licence in this document is worse than a missing one. Record anything that cannot be determined as `UNDETERMINED` rather than guessing.

- [ ] **Step 3: Record the data-source licences with evidence**

| Source | Role | Terms | Evidence |
|---|---|---|---|
| NASA FIRMS NRT + archives | detections | open, attribution required | stated in `apps/site/provenance.md`; confirm against the FIRMS site |
| Copernicus EMS Rapid Mapping (EMSR533) | positive ground truth | EU open data, attribution | `data/labels/manifest_v2.json` `ground_truth[0..3]` |
| EFFIS burnt-area DB | positive ground truth | EU open data, attribution | `ground_truth[9]` |
| EOG VIIRS Nightfire 2020–2024 | negative ground truth | **UNRESOLVED** — CC BY 4.0 for select subsets pre-2025; Data Use License from 2025-01-10 | EOG licensing pages |
| geoBoundaries Algeria ADM1 | wilaya boundaries | check upstream before redistribution | `apps/site/provenance.md` already flags this |

- [ ] **Step 4: Stop tracking the frontend lockfile ignore**

`.gitignore` currently ignores `apps/web/package-lock.json`. The file exists locally at 0.12 MB. A lockfile is how a judge gets the same dependency versions, so ignoring it defeats the purpose of shipping a reproducible clone. Remove that one line and track the file in Task 7's commit.

- [ ] **Step 5: State plainly why no project LICENSE is proposed**

`docs/licensing.md` must end with the reason, not a licence: the repository has no `LICENSE` file, `pyproject.toml` declares no `license` field, and the copyright holder is the team — ownership has not been established in the materials inspected, and an assistant cannot grant copyright or pick a licence on the team's behalf. List what the team needs to decide: the licence, whether to grant any rights in the labels CSV given the unresolved VNF terms, and whether the model artifact may be redistributed. **Do not create a `LICENSE` file in this plan.**

---

### Task 7: Verify from a clean clone and leave a repeatable check

**Files:**
- Create: `scripts/verify_clean_clone.ps1`
- Add: `apps/web/package-lock.json` (0.12 MB, newly tracked)

**Interfaces:**
- Consumes: `docs/SETUP.md` (Task 3) — the script executes exactly the commands that document claims.
- Produces: a script that reproduces the Phase 4 evidence on demand.

- [ ] **Step 1: Write the script to clone, install, populate and probe — no arguments needed**

`scripts/verify_clean_clone.ps1` must: clone `origin` into a temp directory; assert `.env`, `data/db/`, `services/ml/models/verifier_v2/model.joblib` and `apps/web/package-lock.json` statuses and print them; run `uv sync --extra api --extra ml --extra dev`; run the Route A archive fetch and record the JSON `status` and row count; start the API on port 8010 and poll `/health` then `/system/status`; start the static site on 5500 and assert HTTP 200; assert `/detections/{id}/ai` returns 503 with **no** `probability` key. It must clean up its temp directory and kill only the PIDs it started.

- [ ] **Step 2: Run the backend suite from the clone**

Run from the clone root: `uv run pytest -q`
Expected: `207 passed`.

- [ ] **Step 3: Run the frontend suite and production build from the clone**

Run: `cd apps/web; npm ci; npm test; npm run build`
Expected: `98 passed` and a successful `vite build`. `npm ci` — not `npm install` — because that is what consumes the now-tracked lockfile; if it fails, the lockfile and `package.json` disagree and that is a real blocker to report.

- [ ] **Step 4: Probe the running clone and record the honest numbers**

Expected from the clone: `firms` reflects the archive fetch, `ai=UNAVAILABLE` with `model` absent because no artifact is tracked, `data_state` not `LIVE`. Confirm the site shows detections, not an error. **Report `ai=UNAVAILABLE` as the expected clone result — do not describe the clone as fully working, because the verifier is not reachable from a clean clone until Task 4's redistribution question is answered.**

- [ ] **Step 5: Verify the vendored library and the bundle shipped**

Run: `Select-String -Path apps/site/vendor/maplibre-gl.js -Pattern 'maplibre-gl-js/blob/v4.7.1/LICENSE.txt'`
Expected: a match, confirming the bundle is the version whose licence text was added.

Run: `Test-Path apps/site/vendor/LICENSE-maplibre.txt; Test-Path services/ml/models/verifier_v2/manifest.json`
Expected: `True` for both.

- [ ] **Step 6: Re-run the fail-closed check explicitly**

Run the clone's `/ai` on a real detection id and confirm HTTP 503 and that the body has no `probability` key. This is the property the whole project's honesty rests on; it must be demonstrated from the clone, not asserted from the working tree.

- [ ] **Step 7: Commit the documentation, licence and tooling work**

```
git add docs/SETUP.md docs/licensing.md scripts/verify_clean_clone.ps1 \
        apps/site/vendor/LICENSE-maplibre.txt apps/web/package-lock.json \
        README.md .env.example .gitignore services/ml/MODELS.md \
        apps/site/provenance.md \
        services/ml/models/verifier_v2/manifest.json \
        services/ml/models/verifier_v2/config.json \
        services/ml/models/verifier_v2/metrics.json \
        services/ml/models/verifier_v2/calibration.csv \
        services/ml/models/verifier_v2/feature_importance.csv
```
Expected: 13 files. Confirm with `git diff --cached --name-only` that no `*.db`, no `.env` and no `model.joblib` is present, then commit:

```
git commit -m "docs(release): make a fresh clone reproducible and correct stale claims

Add docs/SETUP.md with the credential-free archive route verified end to end,
docs/licensing.md recording source-by-source terms, the MapLibre BSD-3 text
required to redistribute the vendored bundle, and a repeatable clean-clone
verification script. Track the artifact provenance bundle and the frontend
lockfile. Correct README, MODELS.md, .env.example and site provenance claims
that contradicted the shipped verifier-v2. The 48.5 MB artifact stays
untracked pending a redistribution decision."
```

- [ ] **Step 8: Push and confirm**

Run: `git fetch origin; git rev-list --count HEAD..origin/main`
Expected: `0`. If non-zero the remote moved — stop, do not force.

Run: `git push origin main`, then `git rev-parse HEAD` and `git rev-parse origin/main` must be identical.

---

## Self-Review

**Spec coverage.** Phase 1 → Tasks 1–2 (inspect, secret scan, tests before commit, focused commit, remote verification, no force-push). Phase 2 → Tasks 3–4 (clean-clone audit done in-session and recorded; prerequisites, install, env vars, FIRMS key, artifact acquisition, DB init, API on 8010, site startup; fail-closed table; `.env`/DB exclusion; model-acquisition investigation with the licence basis; no synthetic fixture added, because none was needed — the archive route yields real data). Phase 3 → Tasks 5–6 (all four stale README claims plus the other stale rows; MODELS.md; `.env.example`; site provenance; licence inventory; no licence proposed, with reasons). Phase 4 → Task 7 (clone-based, not working-tree; health, port, site, data status, missing-artifact and missing-credential behaviour; backend, frontend, build; exact hashes, push status, counts, blockers, launch commands in `docs/SETUP.md`).

**Step scan.** Every step names a command and the output that means it passed. The one place a body is deliberately absent is the MapLibre licence text, which must be fetched at the pinned tag rather than reconstructed — that is recorded as a stop-and-report condition, not left to judgement.

**Type consistency.** Port 8010 is used consistently in Tasks 3, 5 and 7. Artifact path `services/ml/models/verifier_v2/` is identical in Tasks 4, 5 and 7. `train()`'s signature is quoted from the source, not paraphrased.

**Review Focus.** All five lines are pinned: 1 → Task 3 Step 5, 2 → Task 7 Steps 4 and 6, 3 → Task 1 Step 3, 4 → Task 5 Step 5, 5 → Task 4 Step 2 and Task 6 Step 3.

**Proportion.** The plan is longer than a one-line spec but every task is either a git operation, a documentation edit with a grep assertion, or a measurement with a stated expected result. No code bodies are written.

**Known limits of this plan.** It does not resolve the model redistribution question, because that needs a licence determination and an ownership decision the project has not made. It does not add a training CLI, because `verifier_train.py` is SHA-pinned in the artifact manifest. It does not verify the rebuild path by executing it, because retraining is excluded — so the documented rebuild command is labelled unexecuted rather than proven.