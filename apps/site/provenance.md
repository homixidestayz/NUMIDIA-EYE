# Provenance and terms

Every layer this app draws, its authority, and its terms. No site-wide data
licence is declared — check the layer before reuse.

## Layers

| Layer | Source | Authority | Built / retrieved | Terms |
|---|---|---|---|---|
| Detections | NASA FIRMS VIIRS + MODIS, NRT and historical | NASA | live via the NUMIDIA API | NASA data are open; attribution to NASA FIRMS required |
| Wilaya boundaries | bundled `data/gis/algeria_wilayas.geojson` | Algeria's current administrative division — **69 wilayas** | OpenStreetMap `admin_level=4` relations, via the GeoAlgeria dataset package; retrieved 2026-10-09; rounded copy in `data/wilayas.geojson` for display only | **ODbL 1.0, © OpenStreetMap contributors** — attribution required, derived databases share-alike |
| Verifier verdict | `verifier-v2` artifact over the live-v1 contract | this project | verified on every load | experimental, non-official |
| Incident clusters | derived from stored detections (`incident-v1`) | this project | computed on demand | deterministic; stable IDs |
| Incident priority | derived (`priority-v1`) | this project | computed on demand | rule-based, no model input |
| Incident report | derived (`report-v1`) | this project | computed on demand | prototype, non-official |
| Map rendering | blank style, no basemap tiles | this project | built in | none — nothing is fetched from a tile server |

### About the boundary layers

The map draws **69 wilayas**, Algeria's current administrative division:

- **48** original, under Law 84-09 (1984)
- **+10** southern delegated wilayas promoted in 2019 (Law 19-12)
- **+11** Hauts Plateaux delegated wilayas promoted in 2026 (Law 26-06)

Each feature carries `created` recording which of the three it is, so the 2019 and
2026 promotions stay visible rather than being flattened into an undifferentiated
set of 69.

This replaced an earlier 48-wilaya bundle built on the 1984 delineation, under
which every 2019 and 2026 wilaya resolved to its parent — including **In Salah,
Touggourt, Djanet and El M'Ghair**, all oil and gas fields, which were being
attributed to Tamanrasset, Ouargla, Illizi and El Oued respectively.

`data/wilayas.geojson` is **derived**, generated only for rendering: rings are
rounded to 5 decimals and simplified with Douglas-Peucker at 0.0008 degrees. The
source is already display-grade, so simplification is nearly a no-op — 69 features,
7,797 → 7,772 vertices (99.7% retained), 133 KB → 125 KB. The source file is never
modified. Because it is a display product, **do not use it for measurement or
containment tests** — use the backend's own polygon lookup for that.

## Provenance carried at runtime

- Detections: `source`, `product`, `satellite`, `instrument`, `fetched_at`, plus
  `confidence_raw` so the satellite's own confidence string is never silently
  reinterpreted.
- Wilaya lookup: the backend resolves a point against the bundled polygons and
  returns `wilaya_code` / `wilaya_name`. No other GIS layer is populated;
  settlement, road, elevation, slope and forest context are reported
  **UNAVAILABLE** with a reason rather than filled with a placeholder.
- Wilaya statistics on the page are counted from the detections loaded in the
  browser and are labelled as such.
- Priority: every factor carries its `value`, `normalized`, `weight` and a
  human-readable `evidence` string, so the score can be re-derived by hand.

## What this app will not do

- It will not invent a detection, a coordinate, a probability or a verdict.
- It will not substitute a value for a missing field; unavailability is shown
  as "Unavailable".
- It will not present an incident as a confirmed fire.
- It will not present rule-based priority as model output.
- It will not present a loaded-window count as a national total.
- It will not present itself as an official alert channel.
- It draws no basemap and no neighbouring country; the map is Algeria and its
  wilayas only, from the bundled boundaries.

## Reuse

**No project licence has been granted.** This repository ships no `LICENSE` file
and `pyproject.toml` declares no licence field. Do not assume reuse rights: check
[`docs/licensing.md`](../../docs/licensing.md) for the per-source terms and the open
questions, and [`MODEL_LICENSE.md`](../../MODEL_LICENSE.md) for the provenance and
attribution the model artifact requires.

The underlying detection data are other people's - NASA FIRMS, and for the trained
verifier, Copernicus EMS/EFFIS and EOG VIIRS Nightfire - each with its own terms and
attribution requirements, and the EOG position is unresolved. The derived layers
(clusters, priority, reports) are outputs of an experimental prototype and should not
be treated as authoritative.

Vendored third-party code: `vendor/maplibre-gl.js` and `vendor/maplibre-gl.css` are
MapLibre GL JS v4.7.1 under 3-Clause BSD; the licence text is in
`vendor/LICENSE-maplibre.txt`.
