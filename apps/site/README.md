# NUMIDIA EYE

An open wildfire-intelligence surface for Algeria, served over the NUMIDIA API.

It has the shape of a national reference atlas — a live interactive map, a
per-wilaya drill-down, a machine-readable catalog, stated provenance — with one
addition: every fire on the map can be **verified by a real model** and **scored
by a transparent rule engine**, and every one of those steps is auditable.

## Run it

**If you have just cloned the repository, start with [`docs/SETUP.md`](../../docs/SETUP.md).**
It covers prerequisites, database initialisation and the credential-free FIRMS
archive route, none of which this page repeats.

```bash
# 0. one-time: populate a database from the public FIRMS archive (no key needed)
uv run python -m numidia_worker.cli --db data/db/numidia.db fetch --mode archive
#    note the argument order: --db comes BEFORE the `fetch` subcommand

# 1. backend (from the repo root). Port 8010 by default because 8000 is taken
#    by another service on this machine; any free port works.
uv run uvicorn numidia_api.app:app --host 0.0.0.0 --port 8010

# 2. this static app
cd apps/site
python -m http.server 5500
# open http://127.0.0.1:5500
```

No build step, no npm install. `vendor/maplibre-gl.*` is vendored and the map
style is blank, so the **only** runtime network call is the NUMIDIA API. There
is no tile or style server to depend on, so the map cannot half-load and works
offline.

Point it elsewhere with `window.NUMIDIA_API_BASE` before `site.js` loads, or
without touching the code at all:

```
http://127.0.0.1:5500/?api=8010        # bare number = port on this host
http://127.0.0.1:5500/?api=http://192.168.1.10:8010   # or a full base URL
```

## The map

- **Wilaya boundaries** from the project's own bundled polygons, simplified for
  display. Hover to highlight, click to focus.
- Focusing a wilaya filters the detections, updates the statistics panel and
  writes `?wilaya=<code>` to the URL, so a focused view is shareable.
- Click a detection point for its record and to run the verifier on it.
- Clusters expand on click; the scale bar is in metres.

## The five stages

| Stage | What it shows | Source |
|---|---|---|
| DETECT | live and historical FIRMS detections, clustered | `GET /detections` |
| VERIFY | FIRE / NON_FIRE / UNCERTAIN, probability, threshold, schema | `GET /detections/{id}/ai` |
| UNDERSTAND | what / where / when / source / signal for the selection | `GET /detections/{id}` |
| PRIORITIZE | rule-based level, score, per-factor weight and evidence | `GET /incidents` |
| RESPOND | incident report with its limitations | `GET /incidents/{id}/report` |

## Honesty rules this app is built on

- **A detection is not a fire.** An incident is a spatiotemporal cluster, also
  not a confirmed fire. The counting rule is stated on the page.
- **Satellite thermal anomalies are not confirmed fires**, and an absence of
  detections is not evidence of no fire.
- **Priority is not the model.** `priority-v1` is deterministic and rule-based
  and never consumes model output. The two are separated in copy and layout.
- **Fail closed.** If the verifier artifact cannot be verified, the API returns
  503 with no probability, no model and no verdict, and the panel shows the
  unavailable state instead of a number.
- **Unavailable is never zero.** A missing field renders as "Unavailable".
- **Wilaya counts are labelled as being from the loaded window**, not a
  national total.
- **Not an alert channel.** Protection Civile's numbers (14 / 1021) appear as
  reference information only.

## Files

| Path | Purpose |
|---|---|
| `index.html` | shell |
| `site.css` | styling |
| `site.js` | all application logic, no framework |
| `vendor/` | self-hosted MapLibre GL |
| `data/wilayas.geojson` | display-only wilaya boundaries, derived from `data/gis/algeria_wilayas.geojson` |
| `llms.txt` | machine-readable capability catalog |
| `index.md` | markdown twin of the page |
| `provenance.md` | sources, authorities and terms |

## Scope

The verifier is experimental, not a validated Algerian wildfire detector: the
training labels hold no independently confirmed southern wildfire positive and
the negative class is predominantly catalogued gas flare. Recall is 0.81.
Southern metrics are UNAVAILABLE for insufficient coverage. See `llms.txt`.
