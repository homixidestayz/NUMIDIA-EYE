# Setup — from a fresh clone to a running demo

This is the authoritative path for running NUMIDIA EYE. If it disagrees with
`README.md`, this document is right.

## What a fresh clone does and does not contain

A `git clone` gives you the code, the labelled dataset, the map site, and the
trained verifier with its provenance. It does **not** give you a database or a
`.env` — and that is deliberate: the database is regenerated from NASA FIRMS, and
credentials are never committed.

Measured on a clean clone of `origin/main`: **133 tracked files**, containing
`data/labels/` (the v2 labelled dataset, 53,615 rows), `apps/site/` (11 files) and
`services/ml/models/verifier_v2/` (including `model.joblib`, 48.5 MB), and **no**
`.env` and **no** `data/db/`.

**Order matters: populate the database before you start the API or run the tests.**
`numidia_core.db.connect()` creates `data/db/numidia.db` if it is missing, but it
does not create the schema, so a request that reaches the database before Route A
has run hits `sqlite3.OperationalError: no such table: detections` and returns
HTTP 500 rather than a truthful response. This is a known robustness gap in the
frozen API/DB layer, reported rather than fixed in this release. Route A below
resolves it in seconds.

The database gap is closed by the commands below. It requires no credentials and
no invented data.

The verifier is present but **inactive** until you point the API at it — see
[Enabling the AI verifier](#enabling-the-ai-verifier). Its provenance, the
attribution it requires and the licence uncertainty behind shipping it are in
[`MODEL_LICENSE.md`](../MODEL_LICENSE.md).

## Prerequisites

| Requirement | Version | Needed for |
|---|---|---|
| Python | `>=3.12,<3.14` (per `pyproject.toml`) | everything |
| [uv](https://docs.astral.sh/uv/) | recent | everything |
| Node.js | >= 18 | only the `apps/web` dashboard |
| NASA FIRMS MAP_KEY | optional | only live `LIVE`-state ingestion |

Install the Python environment from the repository root:

```
uv sync --extra api --extra ml --extra dev
```

`--extra ml` is required for the `numidia_ml` CLI and for rebuilding the model.
`--extra dev` is required for the test suite.

## Route A — real data with no credentials (works for everyone)

NASA publishes rolling global fire files that need no key. Populate a database
from them:

```
uv run python -m numidia_worker.cli --db data/db/numidia.db fetch --mode archive
```

**Note the argument order.** `--db` is a top-level option and must come *before*
the `fetch` subcommand. Written as `... fetch --mode archive --db ...`, argparse
rejects it with `unrecognized arguments: --db`.

Verified result of this command in this repository (2026-10-09):

```
status: ok
new: 888   total: 888
sources: VIIRS_NOAA21_C2, VIIRS_SNPP_C2, VIIRS_NOAA20_C2
database: 444 KB
```

It downloads three public files from `firms.modaps.eosdis.nasa.gov`
(`J2_VIIRS_C2_Global_24h.csv`, `SUOMI_VIIRS_C2_Global_24h.csv`,
`J1_VIIRS_C2_Global_24h.csv`) and writes real detections with full provenance.

**The row count will not match the number above.** These are rolling 24-hour global
files that change continuously, so every run sees different data. That is expected,
not a fault.

## Route B — live ingestion with a FIRMS key

Request a free key at <https://firms.modaps.eosdis.nasa.gov/api/map_key/>, then:

```
cp .env.example .env
# set FIRMS_MAP_KEY=<your key> in .env  -- never commit this file
uv run python -m numidia_worker.cli fetch
```

`.env` is gitignored. The key is read server-side only, is redacted from stored
URLs and responses, and is never sent to a browser. **Route A reaches `data_state=LIVE` too**, because the state is enforced by
acquisition and ingest-run freshness rather than by which endpoint served the data.
Measured from a clean clone on 2026-10-09:

```
firms=CONNECTED  ai=UNAVAILABLE  model=<none>  data_state=LIVE  detections=569  db=OK
"Live: 569 freshly acquired VIIRS detections via FIRMS public archive
 (VIIRS_NOAA21_C2, VIIRS_SNPP_C2, VIIRS_NOAA20_C2); pipeline healthy."
```

Note the count differs from the 888 the fetch reported above: the `24h` files
roll, and the API's scheduler ran a further ingest at startup. Both numbers are
correct for when they were measured.

You do not need Route B to evaluate the project.

## Start the API

```
uv run uvicorn numidia_api.app:app --host 0.0.0.0 --port 8010
```

**Port 8010, not 8000.** Port 8000 is occupied by another service on the reference
machine. Any free port works — the site is told which one to use (see below).
Interactive API docs: <http://127.0.0.1:8010/docs>

Health check: <http://127.0.0.1:8010/health>

## Start the map site

```
cd apps/site
python -m http.server 5500 --bind 0.0.0.0
```

Open <http://127.0.0.1:5500>.

The site is plain static files — no build step, no `npm install`, no external
network requests. It calls the API at port `8010` on whatever host the page itself
was served from, so opening it over a LAN address talks to the LAN address. To
point it somewhere else, without editing code:

```
http://127.0.0.1:5500/?api=8010                      # bare number = port on this host
http://127.0.0.1:5500/?api=http://192.168.1.10:8010  # or a full base URL
```

or set `window.NUMIDIA_API_BASE` before `site.js` loads.

### The other dashboard (`apps/web`)

The original React dashboard is still in the repository and is the one `README.md`
describes when it mentions EN/Arabic RTL.

```
cd apps/web
npm ci        # npm ci, not npm install - it consumes the committed lockfile
npm run dev
```

## Behaviour when something is missing

The project fails closed. A missing credential, artifact or dataset produces a
truthful unavailable state, never a placeholder value and never a fabricated one.

| Missing | What actually happens | Evidence |
|---|---|---|
| `FIRMS_MAP_KEY` | Scheduler records `skipped` runs; `/system/status` reports a non-`LIVE` data state. No detections are invented. | verified |
| `data/db/` (never cloned) | `/detections` returns an empty set; the site draws the 48 wilayas with no detections and labels the count accordingly. | verified |
| `NUMIDIA_ACTIVE_MODEL` unset (**the default**) | `/detections/{id}/ai` returns HTTP `503` with `status: "AI_UNAVAILABLE"`. Every model field is `null`, including `probability` — the key is present but explicitly null, never a number. The UI shows `AI verifier Unavailable`. This is the fail-closed path, and it is what you get until you enable the verifier below. | verified from a clean clone, 2026-10-09 |
| A tampered artifact | Verification refuses it and serves no probability. | verified — `UnavailableVerifier` |

## Enabling the AI verifier

The verifier ships in the clone but stays **inactive** by default. `NUMIDIA_ACTIVE_MODEL`
must point at it, deliberately, so that an unconfigured deployment fails closed
rather than silently serving predictions from a model nobody selected.

On Windows PowerShell:

```
$env:NUMIDIA_ACTIVE_MODEL = "services/ml/models/verifier_v2"
uv run uvicorn numidia_api.app:app --host 0.0.0.0 --port 8010
```

On bash/zsh:

```
export NUMIDIA_ACTIVE_MODEL=services/ml/models/verifier_v2
uv run uvicorn numidia_api.app:app --host 0.0.0.0 --port 8010
```

You can also put it in `.env`, which is gitignored.

The artifact is re-verified on **every** load — contract, dataset SHA and a metric
replay against `metrics.json`. A mismatched or tampered artifact is refused and no
probability is served. Because that replay reads the full 48.5 MB artifact and the
20,716-row test split, expect the first `/ai` call to take several seconds.

Confirm what you are getting from `/system/status`: `ai=READY` and
`model=verifier-v2` when it is active; `ai=UNAVAILABLE` with `model` absent when not.

### What the verifier is and is not

It is an **experimental** model over VIIRS structured satellite features. Its test
split (n=20,716) reports ROC-AUC 0.9496, PR-AUC 0.9568, precision 0.9361, recall
0.8085, F1 0.8676 at threshold 0.52. Those numbers are real but they are **not** a
claim about Algerian wildfire detection:

- The labels contain **no independently confirmed southern Algerian wildfire
  positive**. Southern performance is recorded `UNAVAILABLE`, not as a number.
- The negative class is predominantly catalogued **gas flare**, so this is closer to
  a flare-vs-wildfire discriminator than a general fire detector.
- It has not been validated nationwide and is not integrated with Civil Protection.

The authoritative statement is the `scope` field in
`services/ml/models/verifier_v2/manifest.json`, which the API returns verbatim with
every verdict.

## Rebuilding the model artifact locally

The shipped artifact is enough to run the demo. Rebuilding is an alternative — to
confirm provenance from source, or if you have excluded `model.joblib` using the
one-line switch in `.gitignore`.

`services/numidia_ml/verifier_train.py` exposes a library function and no CLI
entry point, so the rebuild is a Python call:

```
uv run --extra ml python -c "from numidia_ml.verifier_train import train; train('data/labels/firms_labels_v2.csv', 'services/ml/models/verifier_v2')"
```

> **Not executed in this release.** Retraining was out of scope, so this command is
> documented from its source signature
> (`train(dataset_path, out_dir, *, models=("hgb","rf","et"), calibrate=True)`)
> and has **not** been run to confirm it reproduces the committed
> `model_sha256`. Do not treat it as verified.

Byte-identical output would additionally depend on the scikit-learn version:
`pyproject.toml` floors it at `>=1.5` and does not pin an exact version, so the
rebuild is expected to reproduce the dataset linkage (`dataset_sha256`) but not
guaranteed to reproduce the model hash.

A no-CLI rebuild is deliberate here, not an oversight: the artifact manifest pins
`source_code_sha256` over `verifier_train.py`, `inference.py` and others, so
changing that module would invalidate the artifact's own verification contract.

## Verify a clone yourself

```
git clone https://github.com/homixidestayz/NUMIDIA-EYE.git
cd NUMIDIA-EYE
uv sync --extra api --extra ml --extra dev

# Populate the database BEFORE the tests: 5 tests exercise the API against real
# production detections and skip when there is no usable database.
uv run python -m numidia_worker.cli --db data/db/numidia.db fetch --mode archive

uv run pytest -q                       # 207 passed, 0 skipped
uv run uvicorn numidia_api.app:app --host 0.0.0.0 --port 8010
```

Without the archive fetch the suite reports **202 passed, 5 skipped** rather than
failing - the five tests that need a populated database skip with a stated reason.

`scripts/verify_clean_clone.ps1` automates exactly this sequence.

## What this project is not

- Not an official alert channel and not integrated with Civil Protection.
- Not validated across all Algerian wildfires. `verifier-v2`'s labels contain **no**
  independently confirmed southern Algerian wildfire positive, so southern
  performance is recorded `UNAVAILABLE` rather than as a number. See the `scope`
  field in `services/ml/models/verifier_v2/manifest.json`, quoted verbatim in
  `README.md`.
- Not a wildfire-vs-flare separator in general; its negative class is predominantly
  catalogued gas flare.