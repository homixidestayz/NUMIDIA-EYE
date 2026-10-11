/* Attribution for bundled and rendered data.
 *
 * Every entry here must correspond to something this app actually loads. An
 * attribution is a factual claim about provenance, so adding a credit for a
 * source we do not use is as wrong as omitting one we do — CARTO in
 * particular was never used: there is no tile server, and every basemap
 * outline is local GeoJSON.
 */

import type { Dict } from "./i18n";

export interface Credit {
  /** English label, kept for provenance records and tests. */
  label: string;
  /** Dictionary key for the UI-visible label. */
  key: keyof Dict;
  /** Legal text. Never translated — a licence notice is not copy. */
  detail: string;
}

export const ATTRIBUTION: Credit[] = [
  { label: "Fire detections", key: "attrDetections", detail: "NASA FIRMS / VIIRS" },
  {
    label: "Wilaya boundaries",
    key: "attrBoundaries",
    detail: "© OpenStreetMap contributors · ODbL 1.0, via the GeoAlgeria dataset",
  },
  {
    label: "World outlines",
    key: "attrWorld",
    detail: "Natural Earth 110m Admin-0, public domain",
  },
  { label: "Weather", key: "attrWeather", detail: "Open-Meteo" },
  { label: "Map renderer", key: "attrRenderer", detail: "MapLibre GL JS" },
];

/** One-line form, for the map's compact attribution control. */
export const ATTRIBUTION_LINE = ATTRIBUTION.map((c) => c.detail).join(" · ");