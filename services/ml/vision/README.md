# NUMIDIA EYE — Sentinel-2 vision experiment (FUTURE, NOT INTEGRATED)

**Status: placeholder. No Sentinel-2 data has been downloaded, no chip dataset
exists, no vision code is written, and nothing in the serving path knows about
this directory.**

## Intended direction (proposal only)

Learn fire-vs-nonfire appearance from Sentinel-2 L2A imagery chips centered on
V2-labeled FIRMS detections: chip the detection coordinate (±~2 km) at 10–20 m
bands, attach the V2 row label, train a small CNN on a GPU runtime (this is
the step that actually needs cloud GPUs — the tabular baseline does not).

## Hard requirements before any vision work starts

- Chips generated only from V2-labeled rows (same ground-truth provenance;
  no new labels invented for pixels).
- Temporal alignment: chip acquisition date must fall inside the row's label
  window (daytime overpass, low cloud) — misaligned chips are excluded, not
  relabeled.
- Same bans apply: no coordinate/leakage features; chip IDs must not leak
  across train/val/test (group by V2 `event_id`).
- No LLM-generated labels or captions anywhere in the loop.

## Non-goals

Downloading the Sentinel-2 archive, building chip pipelines, or wiring any
`/ai` vision path — none of that exists yet, and none is implied by this file.

Future files (when approved): `chips/` manifest builder, `dataset_vision_v1`
spec, `train_vision.py`, `docs/vision-experiment-v1.md`.
