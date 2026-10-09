# NUMIDIA EYE — wildfire intelligence for Algeria

Independent research prototype · non-official. Real satellite data only.

## How to read these numbers

A **detection** is one raw FIRMS thermal pixel. An **incident** is a
spatiotemporal cluster of detections and is **not** a confirmed fire. **Priority**
is rule-based and never uses model output. **Verification** is a live-v1
structured-data model call; when it cannot be served, no probability and no
verdict are shown.

Wilaya counts on this page are counted from the detections currently loaded in
the browser, not from a national total.

Protection Civile emergency: **14** (or **1021**). Reference information only —
this is never a dispatch service.

## Endpoints

`GET /system/status` · `GET /detections?limit=` · `GET /detections/{id}` ·
`GET /detections/{id}/ai` · `GET /incidents?limit=` ·
`GET /incidents/{id}/report`

Focus one wilaya with `?wilaya=<wilaya_code>`. The map draws Algeria and its
wilayas only, from the project's own boundary file, with no external basemap.

## Scope

The verifier is experimental and is not a validated Algerian wildfire detector.
Its training labels contain no independently confirmed southern Algerian
wildfire positive, and the negative class is predominantly catalogued gas
flare. Recall is 0.81 (1,977 of 10,323 fire detections missed). Southern test
metrics are UNAVAILABLE for insufficient class coverage, not zero. Do not read
this as national validation.

Sources and terms: [provenance.md](provenance.md). Capability catalog:
[llms.txt](llms.txt).
