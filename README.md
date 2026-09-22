# 🔥 NUMIDIA EYE

**AI-Powered Wildfire Intelligence for Algeria** — *independent prototype · non-official*.

> REAL FIRMS/VIIRS satellite data → REAL processing → REAL trained AI → REAL output.
> No fabricated data, no hard-coded AI, no mock presented as live.

## Status

| Layer | State |
|---|---|
| Real satellite ingestion (FIRMS/VIIRS) | ✅ worker + core — verified live: **1231 real detections** pulled from NASA's public archives (no key), Algeria bbox |
| Real processing features | ✅ 7 derived features (`f_bt_diff`, `f_frp`, ...) over 1231 detections |
| API boundary (FastAPI) | ✅ detections / status / provenance; AI & incidents return explicit `UNAVAILABLE` |
| Frontend (React + TS + maplibre, EN/العربية) | 🚧 scaffold written (`apps/web`) — build not verified here (no Node toolchain in this env) |
| Trained AI verifier | ⛔ not yet — needs a labelled dataset (see services/ml/README.md) |

## Monorepo layout

```
apps/web            React + TypeScript + Vite + maplibre-gl (EN/AR RTL)
services/core       numidia_core — schemas, FIRMS ingestion, processing, storage
services/worker     numidia_worker — ingestion CLI (runs in CI or locally)
services/api        numidia_api — FastAPI boundary
services/ml         numidia_ml — training + inference (next phase)
data/raw/firms      real FIRMS/VIIRS snapshots (sample committed)
data/processed      canonical detections + derived features (regenerated)
data/gis            Algeria wilaya polygons (geoBoundaries, CC-BY-4.0)
data/evaluation     model evaluation artifacts (later)
```

## Quick start

```bash
uv sync --extra api --extra dev

# ingest the latest live detections (API mode needs FIRMS_MAP_KEY in .env;
# without a key the worker falls back to NASA public archives — no key needed)
uv run python -m numidia_worker.cli fetch

# process features (works offline on the committed sample, or on fetched snapshots)
uv run python -m numidia_worker.cli process --input data/raw/firms/<snapshot>.csv

# run the API
uv run uvicorn numidia_api.app:app --reload
# → http://localhost:8000/docs

# frontend (React + Vite + maplibre, EN/العربية RTL)
cd apps/web
npm install
npm run dev
# → http://localhost:5173  (Node >= 18 required; not present in the build env,
# so the scaffold is committed unverified for now)
```

## Data & AI integrity (non-negotiable)

- Every value displayed has a source + timestamp where applicable.
- **LIVE** / **HISTORICAL** / **SAMPLE** / **DEMO** / **UNAVAILABLE** states are never blurred.
- AI output comes only from an actual trained model evaluated on real data — otherwise the UI and API return `AI_UNAVAILABLE`.
- The prototype alert workflow is never presented as an official Civil Protection integration.

## Data sources

| Source | Purpose | Access |
|---|---|---|
| NASA FIRMS NRT API | VIIRS active-fire detections, Algeria bbox `(-9,18,12,38)` | free `FIRMS_MAP_KEY` |
| NASA FIRMS public archives | 24h/48h/7d global CSVs (fallback) | none |
| geoBoundaries (DZA ADM1) | 58 wilayas — boundaries for GIS context | bundled GeoJSON |

## Roadmap (priority order)

real satellite data ✅ → real AI model → AI integration → Algeria map/GIS → incident page → weather/environment → report → prototype alert workflow → affected-area mapping → extras.