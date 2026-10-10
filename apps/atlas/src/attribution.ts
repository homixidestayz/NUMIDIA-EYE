/* Attribution for bundled and rendered data.
 *
 * Every entry here must correspond to something this app actually loads. An
 * attribution is a factual claim about provenance, so adding a credit for a
 * source we do not use is as wrong as omitting one we do — CARTO in
 * particular was never used: there is no tile server, and every basemap
 * outline is local GeoJSON.
 */

export interface Credit {
  label: string;
  detail: string;
}

export const ATTRIBUTION: Credit[] = [
  { label: "Fire detections", detail: "NASA FIRMS / VIIRS" },
  {
    label: "Wilaya boundaries",
    detail: "© OpenStreetMap contributors · ODbL 1.0, via the GeoAlgeria dataset",
  },
  {
    label: "World outlines",
    detail: "Natural Earth 110m Admin-0, public domain",
  },
  { label: "Weather", detail: "Open-Meteo" },
  { label: "Map renderer", detail: "MapLibre GL JS" },
];

/** One-line form, for the map's compact attribution control. */
export const ATTRIBUTION_LINE = ATTRIBUTION.map((c) => c.detail).join(" · ");