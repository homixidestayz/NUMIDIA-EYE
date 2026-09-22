# 🔥 NUMIDIA EYE

**AI-Powered Wildfire Intelligence for Algeria** — *independent prototype · non-official*.

> REAL FIRMS/VIIRS satellite data → REAL processing → REAL trained AI → REAL output.
> No fabricated data, no hard-coded AI, no mock presented as live.

## Production architecture (built directly — no demo layer)

```
NASA FIRMS NRT API (server-side key)
        │  scheduled fetch (API service, default every 30 min) or worker CLI
        ▼
normalize → validate → feature extraction (7 real features)
        │  GIS enrichment (wilaya point-in-polygon, 48 units)
        ▼
application database (SQLite WAL): detections + ingest_runs
        │  freshness enforced: LIVE requires fresh acquisition AND fresh run
        ▼
FastAPI → React dashboard (EN/العربية RTL)
        │  ML hook: trained verifier runs here once it exists
        ▼  (today: explicit 503 AI_UNAVAILABLE — never faked)
fire / non-fire / uncertain → incidents → reports → prototype alerts
```

| Layer | State |
|---|---|
| Real satellite ingestion (FIRMS NRT API + archive backfill) | ✅ `numidia_core` + `numidia_worker`, provenance + key redaction |
| Processing + GIS enrichment | ✅ 7 features + wilaya assignment, stored per detection |
| Application database + freshness | ✅ SQLite; LIVE / HISTORICAL / **STALE** / UNAVAILABLE enforced |
| API boundary | ✅ detections / status / provenance; AI + incidents explicit `UNAVAILABLE` |
| Dashboard scaffold (React + TS + maplibre, EN/العربية) | 🚧 written; build unverified here (no Node toolchain in this env) |
| Trained AI verifier | ⛔ blocked on labels — see `docs/labeling-proposal.md` (decision needed) |

## Production setup

```bash
cp .env.example .env
# edit .env: set FIRMS_MAP_KEY (free key, server-side only — never committed,
# never sent to clients; it is redacted from every stored URL and response)
uv sync --extra api --extra dev

# one production ingestion run (NRT API; needs the key)
uv run python -m numidia_worker.cli fetch
# explicit archive backfill (no key; provenance recorded as "archive")
uv run python -m numidia_worker.cli fetch --mode archive

# run the API (starts the scheduler: ingestion every NUMIDIA_INGEST_INTERVAL_MIN)
uv run uvicorn numidia_api.app:app --host 0.0.0.0 --port 8000
# → http://localhost:8000/docs

# frontend
cd apps/web && npm install && npm run dev   # Node >= 18 (not in this build env)
```

Without `FIRMS_MAP_KEY` the scheduler records `skipped` runs and the API
honestly reports STALE/UNAVAILABLE — it never invents data.

## Data states (never blurred)

| State | Meaning |
|---|---|
| LIVE | freshly acquired detection AND fresh successful ingest run |
| HISTORICAL | real data, healthy pipeline, nothing freshly acquired (e.g. quiet period) |
| STALE | ingestion too old to trust — served as history, never as live |
| UNAVAILABLE | empty database / unreachable source / no AI model |
| SAMPLE / DEMO | reserved for explicitly labelled non-production views |

Test fixtures live in `tests/fixtures/` and are used **only** by automated
tests. `data/raw/firms/` holds gitignored audit snapshots; nothing under
`data/` is ever served as production data.

## Data & AI integrity (non-negotiable)

- Every served value traces to FIRMS/VIIRS + ingest-run provenance.
- AI output comes only from a trained, evaluated model registered via
  `NUMIDIA_ACTIVE_MODEL` — otherwise API and UI return `AI_UNAVAILABLE`.
- No LLM substitutes for the verifier (LLMs may later explain results, only
  after a real model verdict exists).
- Prototype alerts are never presented as Civil Protection integration.

## Sources

| Source | Role |
|---|---|
| NASA FIRMS NRT Area API (`VIIRS_*_NRT`, Algeria bbox) | production source of truth |
| NASA FIRMS public archives | explicit backfill/testing only |
| geoBoundaries Algeria ADM1 (48 units, bundled) | wilaya GIS enrichment |
| Label candidates for the verifier | `docs/labeling-proposal.md` |

## Roadmap

ingestion ✅ → processing+GIS ✅ → DB+freshness ✅ → dashboard 🚧 →
**labels decision** ⏳ → train verifier → wire `/ai` → incidents → weather →
reports → prototype alerts → affected-area mapping.