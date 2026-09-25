# NUMIDIA EYE — backend API contract (for frontend integration)

Base URL: FastAPI service (dev `http://localhost:8000`). All responses are JSON.
Nothing here is mocked: every value comes from the SQLite database or states
explicitly that it is unavailable. Independent prototype, non-official.

## Global states

- Detection `state`: `LIVE` (fresh acquisition + fresh pipeline) |
  `HISTORICAL` (real data, aging/quiet) — never `LIVE` when stale.
- System `data_state`: `LIVE` | `HISTORICAL` | `STALE` | `UNAVAILABLE`.
- Incident `status`: `SINGLE_OBSERVATION` | `UNVERIFIED_CLUSTER`.
  There is deliberately NO "confirmed wildfire" status anywhere.
- Verification `status`: `UNAVAILABLE` (always, until a validated model registers).
- GIS layers: `{data_available, status: OK|UNAVAILABLE, value, source, reason}`.
  Only `wilaya` is real today.
- Alerts: `DRAFT → REVIEW_REQUIRED → APPROVED → SENT` (forward only).
  Every alert response carries `prototype_only: true`.

## Endpoints

### GET /health
`{status: "ok", time, service}`.

### GET /system/status
FIRMS/source health, `ai: UNAVAILABLE`, `data_state`, counts, human message.

### GET /system/data
Provenance: counts, sources, satellites, `max_acq`, bbox, recent ingest runs
(key-redacted), verification state, `live_window_hours`.

### GET /detections
Query params (all optional): `source`, `satellite`,
`state` (LIVE|HISTORICAL|STALE|SAMPLE|DEMO|UNAVAILABLE),
`since`/`until` (ISO datetime, compared against `acq_datetime`),
`min_confidence`/`max_confidence` (0..1),
`min_frp`/`max_frp` (MW),
`bbox` (`lon_min,lat_min,lon_max,lat_max`; 400 on malformed),
`limit` (1..1000, default 100).
Ordering: newest acquisition first. Filter semantic: filters apply to the most
recent `limit` rows (source/satellite pre-filtered in SQL). Item shape is the
stable `Detection` object (unchanged by this contract).

### GET /detections/recent
Same item shape. Newest first, `limit` default 50. Optional `source`,
`satellite`.

### GET /detections/{detection_id}
Stable `Detection` shape. 404 `{detail: "detection not found"}` when unknown.

### GET /detections/{detection_id}/ai
Always HTTP 503 `{status: "AI_UNAVAILABLE", probability: null, ...}` until a
validated model registers. 404 when the detection is unknown.

### GET /incidents
`{status: OK|EMPTY, count, incidents: [IncidentSummary...], methodology, note}`.
Deterministic grouping; stable IDs (`INC-<hash>`).

### GET /incidents/{incident_id}
Full detail: summary + `member_ids` + `gis_context` + `verification` +
`priority`. 404 when unknown.

### GET /incidents/{incident_id}/report
Structured report: id, timestamps, centroid, FRP (max/sum), satellites,
verification, GIS, priority (with factors + methodology), sources,
limitations (never empty), provenance. 404 when unknown.

### POST /alerts
Body `{incident_id (required), note?}` → 201 DRAFT alert. 400 without
`incident_id`, 404 for unknown incident.

### GET /alerts
`{count, alerts: [...], prototype_note}`.

### POST /alerts/{alert_id}/transition
Body `{to_state}`. Forward-only; 400 on illegal jump/unknown state.

### GET /assistant/tools
Retrieval-tool catalog (name, description, args). No language model here.

### POST /assistant/query
Body `{tool, args?}` → `{tool, ok: true, result}`. Unknown tool/args → 400.
Tools: `detections.search|get`, `incidents.list|get`, `system.status`,
`reports.get`, `gis.lookup`, `verification.get`. Retrieval only.

## Compatibility notes

- Existing shapes (`Detection`, `/system/*`, `/health`) are unchanged;
  only additive params/routes were introduced.
- `/incidents` previously returned `NOT_IMPLEMENTED`; it now returns real
  groupings (see statuses above).
- Sentinel-2 provider interface exists server-side only (no HTTP surface yet);
  status is UNAVAILABLE (no credentials).
