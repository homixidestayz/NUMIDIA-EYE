# Licensing

This document records the licence position of everything in this repository:
data sources, dependencies, vendored code, and the model artifact. It states what
is known, what is unresolved, and what still has to be decided by the project
owner. It is not legal advice.

**No project `LICENSE` file exists and none is proposed here.** The reason is set
out in [Why no project licence is proposed](#why-no-project-licence-is-proposed).

---

## 1. Data sources

| Source | Role | Terms | Evidence |
|---|---|---|---|
| NASA FIRMS NRT Area API | live detections | Open; attribution to NASA FIRMS required | `apps/site/provenance.md`; [firms.modaps.eosdis.nasa.gov](https://firms.modaps.eosdis.nasa.gov/) |
| NASA FIRMS public archives (`*_C2_Global_24h`) | keyless detections, backfill, tests | Open; attribution required | same |
| geoBoundaries Algeria ADM1 (48 units) | wilaya boundaries, bundled | **Check upstream before redistribution** | `apps/site/provenance.md` already flags this; not independently confirmed here |
| Copernicus EMS Rapid Mapping, activation **EMSR533** | verifier positive ground truth (4 products, 253 records) | EU open data; attribution to the Copernicus Emergency Management Service with the activation ID | `data/labels/manifest_v2.json` → `ground_truth[0..3]`, each with URL + SHA-256 |
| EFFIS Rapid Damage Assessment burnt-area DB | verifier positive ground truth (4,554 Algeria features used of 107,428 source records) | EU open data; attribution required | `ground_truth[9]`, WFS `ms:modis.ba.poly`, URL + SHA-256 recorded; count from `effis_dz_features` |
| EOG VIIRS Nightfire annual flare files, 2020-2024 | verifier negative ground truth (1,124 site records) | **UNRESOLVED — see below** | `ground_truth[4..8]`; EOG licensing pages |
| The project's own FIRMS-derived labels, incidents, priority, reports | derived outputs | outputs of this project | — |

### The EOG VIIRS Nightfire question

Two things are publicly stated by the data producer and they do not fully
resolve each other:

- EOG's licensing page states that **effective 10 January 2025, all VIIRS
  Nightfire data is available only under a VIIRS Nightfire Data Use License** —
  academic (no-cost one-year, signed), commercial (paid one-year subscription),
  non-profit (annual subscription).
- An EOG licensing document places **select subsets** of VNF under
  **Creative Commons Attribution 4.0 International**, which permits copying,
  modification and distribution in any format including commercially, with
  attribution.

The five annual flare files this project used are from **2020-2024** and so
predate the January 2025 change. **What is not established** is whether that is
sufficient to place a *model derived from* those files — rather than the files
themselves — under CC BY 4.0.

This is a legal determination. The project has not made it. The founder has
accepted the residual risk for redistribution inside this repository, on the
record, and `MODEL_LICENSE.md` carries the attribution statements and the full
reasoning. Anyone redistributing further, or using the model commercially, should
resolve it directly with EOG (`eog@mines.edu`) rather than relying on this file.

Note also that `data/labels/firms_labels_v2.csv` — carrying the same
VNF-derived labels — has been in this repository's history since 2026-10-01. That
exposure predates the decision to ship the model.

---

## 2. Python dependencies

Read from the installed distribution metadata on 2026-10-09, not from memory.

| Package | Declared licence |
|---|---|
| numpy | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| pandas | BSD 3-Clause |
| pydantic | MIT |
| requests | Apache-2.0 |
| python-dotenv | BSD-3-Clause |
| pyarrow | Apache-2.0 |
| shapely | BSD 3-Clause |
| fastapi | MIT |
| uvicorn | BSD-3-Clause |
| httpx | BSD-3-Clause |
| scikit-learn | BSD-3-Clause |
| joblib | BSD-3-Clause |
| geopandas | BSD-3-Clause |
| pyogrio | MIT |
| openpyxl | MIT |
| pytest | MIT |

All permissive. No copyleft. `pyproject.toml` uses version floors only
(`>=`), so a fresh `uv sync` may resolve to newer versions than those audited
here; the licences above are stable across the majors in use.

## 3. Node dependencies

Read from each installed `package.json` on 2026-10-09.

| Package | Licence | Version |
|---|---|---|
| lucide-react | ISC | 0.454.0 |
| maplibre-gl | BSD-3-Clause | 4.7.1 |
| react | MIT | 18.3.1 |
| react-dom | MIT | 18.3.1 |
| vite | MIT | 5.4.21 |
| vitest | MIT | 2.1.9 |
| typescript | Apache-2.0 | 5.6.3 |
| jsdom | MIT | 25.0.1 |
| @vitejs/plugin-react | MIT | 4.7.0 |
| @testing-library/react | MIT | 16.3.3 |
| @types/react | MIT | 18.3.31 |
| @types/react-dom | MIT | 18.3.7 |

Swept across the whole installed tree (217 packages, lockfile v3 with 256
entries): **9 distinct licences — MIT 166, ISC 21, undeclared 11, BSD-3-Clause 7,
Apache-2.0 5, BSD-2-Clause 4, MIT-0 1, CC-BY-4.0 1 (caniuse-lite), BlueOak-1.0.0
1 (isexe). No GPL, LGPL, AGPL or MPL was declared anywhere in the tree.**

The 11 packages with no machine-readable `license` field are `gl-matrix` type and
sub-module packages; `maplibre-gl` appeared in that set in one automated pass but
declares BSD-3-Clause when read directly, and its own bundle header and
`apps/site/vendor/LICENSE-maplibre.txt` confirm it.

`apps/web/package-lock.json` is deliberately tracked. It is how a fresh clone
resolves identical versions, and `npm ci` requires it.

## 4. Vendored code

`apps/site/vendor/maplibre-gl.js` and `maplibre-gl.css` are **MapLibre GL JS
v4.7.1**, redistributed under 3-Clause BSD. The full licence text, fetched from
the pinned `v4.7.1` tag, is in `apps/site/vendor/LICENSE-maplibre.txt`. It
contains four upstream notices: MapLibre contributors, Mapbox (code from
mapbox-gl-js v1.13 and earlier), Evan Wallace (glfx.js, MIT) and Mike Bostock
(d3-color, BSD-3-Clause).

This file was previously missing, which was a redistribution defect. It is
present now.

---

## 5. Why no project licence is proposed

A licence is a grant of rights by the copyright holder. Choosing one here would
mean asserting ownership and granting permissions that have not been established
in the materials this release inspected:

- there is no `LICENSE` file in the repository;
- `pyproject.toml` declares no `license` field;
- `apps/site/provenance.md` previously asserted "Application code: MIT" — a claim
  with no grant behind it. **That assertion has been removed**, because repeating
  it would be inventing licensing rights rather than documenting them.

The founder has confirmed they hold the project's copyright, so a licence *can* be
chosen. It has not been. That decision is recorded here rather than made
silently, and no `LICENSE` file is added by this release.

### What the owner needs to decide

1. **Which licence**, if any, for the project code. The dependencies permit
   essentially any choice; the data sources, not the code, are what constrain it.
2. **Whether the committed labels CSV stays in history.**
   `data/labels/firms_labels_v2.csv` encodes VNF-derived negative labels. It has
   been committed since 2026-10-01. Removing it would require a history rewrite.
3. **Whether `model.joblib` may be redistributed** — decided on 2026-10-09 to
   ship it, with the residual EOG risk accepted and documented. Revisit if the
   project seeks commercial use.
4. **What attribution the wilaya boundaries require.** The bundled geoBoundaries
   ADM1 data has not had its terms confirmed.

---

## 6. Compliance is the user's responsibility

Nothing here is legal advice, and nothing here grants rights. If you use this
repository, the model, or the labels, you are responsible for:

- complying with the terms of every source in section 1;
- determining whether your use is permitted, especially commercially;
- carrying the attribution statements in `MODEL_LICENSE.md` with any publication
  or derivative product;
- accepting that this project makes no representation about the licence status of
  data from sources it does not control.