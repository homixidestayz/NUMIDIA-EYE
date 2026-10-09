# 🔥 NUMIDIA EYE

**AI-Powered Wildfire Intelligence for Algeria** — *independent prototype · non-official*.

> REAL FIRMS/VIIRS satellite data → REAL processing → REAL output.
> A trained verifier (`verifier-v2`) is registered and serves real FIRE /
> NON-FIRE / UNCERTAIN verdicts over live VIIRS features. No fabricated
> probabilities, no hard-coded AI, no mock presented as live. When no artifact
> is registered the API returns an explicit `503 AI_UNAVAILABLE` — never faked.
>
> **Experimental.** The verifier's labels contain no independently confirmed
> southern Algerian wildfire positive, so southern performance is recorded
> `UNAVAILABLE` rather than as a number. It is not validated nationwide and not
> integrated with Civil Protection. The authoritative scope statement is the
> `scope` field in `services/ml/models/verifier_v2/manifest.json`, returned
> verbatim with every verdict.

## Production architecture (built directly — no demo layer)

```
NASA FIRMS NRT API (server-side key) or public archive (no key)
        │  scheduled fetch (API service, default every 30 min) or worker CLI
        ▼
normalize → validate → feature extraction (7 real features)
        │  GIS enrichment (wilaya point-in-polygon, 48 units)
        ▼
application database (SQLite WAL): detections + ingest_runs
        │  freshness enforced: LIVE requires fresh acquisition AND fresh run
        ▼
FastAPI → React dashboard (EN/العربية RTL) + standalone static map (apps/site)
        │  verifier-v2 runs here; re-verified on every load
        ▼  (artifact absent → explicit 503 AI_UNAVAILABLE, never faked)
fire / non-fire / uncertain → incidents → reports → prototype alerts
```

| Layer | State |
|---|---|
| Real satellite ingestion (FIRMS NRT API + archive backfill) | ✅ `numidia_core` + `numidia_worker`, provenance + key redaction. The public archive route needs no API key. |
| Processing + GIS enrichment | ✅ 7 features + wilaya assignment, stored per detection |
| Application database + freshness | ✅ SQLite; LIVE / HISTORICAL / **STALE** / UNAVAILABLE enforced |
| API boundary | ✅ detections / status / provenance / incidents; `/ai` explicit `UNAVAILABLE` only when no artifact is registered |
| Dashboard scaffold (React + TS + maplibre, EN/العربية) | ✅ written; 98 tests, production build green |
| Standalone map site (`apps/site`, English-only) | ✅ plain static files, blank MapLibre style, **zero** external network requests |
| Trained AI verifier | ⚠️ **experimental** — `verifier-v2` registered, `/ai` serves real verdicts. Labelled data built and verified (v2, 53,615 rows). **Not** a validated Algerian wildfire detector: no southern positive in the labels, negative class predominantly catalogued gas flare. Artifact provenance and attribution: `MODEL_LICENSE.md`; registry and gates: `services/ml/MODELS.md` |

## Production setup

**Start here if you have just cloned the repository:
[`docs/SETUP.md`](docs/SETUP.md).** It is the authoritative run path and covers
prerequisites, database initialisation from the credential-free NASA FIRMS archive,
and what each missing credential, dataset or model artifact actually does. The block
below is the summary.

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

| Source | Role | Terms |
|---|---|---|
| NASA FIRMS NRT Area API (`VIIRS_*_NRT`, Algeria bbox) | live source of truth | open; attribution to NASA FIRMS required |
| NASA FIRMS public archives (`*_C2_Global_24h`) | keyless route, backfill, testing | open; attribution required |
| geoBoundaries Algeria ADM1 (48 units, bundled) | wilaya GIS enrichment | check upstream terms before redistribution |
| Copernicus EMS Rapid Mapping (EMSR533) + EFFIS | verifier positive ground truth | EU open data; attribution required |
| EOG VIIRS Nightfire annual flare files 2020-2024 | verifier negative ground truth | **licence position unresolved** — see `MODEL_LICENSE.md` |

Full licence inventory and the open questions: [`docs/licensing.md`](docs/licensing.md).
Model provenance and attribution: [`MODEL_LICENSE.md`](MODEL_LICENSE.md).

## Roadmap

Shipped: ingestion ✅ → processing+GIS ✅ → DB+freshness ✅ → dashboard ✅ →
labels ✅ (v2, 53,615 rows) → train verifier ✅ → wire `/ai` ✅ → incidents ✅ →
priority ✅ → reports ✅ → prototype alerts ✅ → map site ✅.

Blocking item:

- **Southern-fire validation — unresolved.** The labelled set contains no
  independently confirmed southern Algerian wildfire positive, so southern
  ROC-AUC / precision / recall / F1 are recorded `UNAVAILABLE` rather than as
  numbers. Every candidate southern source tested so far was eliminated by a
  propagation-vs-stationarity check. Until one survives, the verifier cannot be
  described as covering Algerian wildfires generally.

Planned, **not implemented**:

- Environmental intelligence (weather, fuel moisture, elevation, slope, forest
  context) — currently reported `UNAVAILABLE` with a reason, never filled with a
  placeholder.
- Safe-road routing and evacuation support.
- Affected-area / per-wilaya impact mapping beyond counts in the loaded window.
- Live alerting to operational users.

These are roadmap items. Nothing above should be read as a claim that they exist
today.