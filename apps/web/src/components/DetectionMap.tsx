import { useCallback, useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Detection, Lang } from "../types";
import type { Dict } from "../i18n";
import { fmtDate } from "../api";
import MapLegend from "./MapLegend";

interface Props {
  detections: Detection[];
  lang: Lang;
  dict: Dict;
  detail: Detection | null;
  detailStale: boolean;
  onSelect: (id: string) => void;
}

const ALGERIA_BOUNDS: [[number, number], [number, number]] = [
  [-9, 18],
  [12, 38],
];

export const SOURCE_ID = "detections";
export const CLUSTER_LAYER_ID = "clusters";
export const CLUSTER_COUNT_LAYER_ID = "cluster-count";
export const LIVE_LAYER_ID = "live";
export const HISTORICAL_LAYER_ID = "historical";

/** Layers whose features are individual detections (selectable). */
export const SELECTABLE_LAYER_IDS = [LIVE_LAYER_ID, HISTORICAL_LAYER_ID];
/** Layers that represent grouped detections. */
export const CLUSTER_LAYER_IDS = [CLUSTER_LAYER_ID, CLUSTER_COUNT_LAYER_ID];

/**
 * Native MapLibre clustering over the real detection coordinates returned by
 * the API. No cluster state is invented in React - MapLibre derives it from
 * the same lat/lon the backend served.
 */
export const CLUSTER_OPTIONS = {
  cluster: true,
  clusterMaxZoom: 11,
  clusterRadius: 45,
} as const;

/** A feature is a cluster exactly when it carries a point_count. */
export const CLUSTER_FILTER: maplibregl.FilterSpecification = ["has", "point_count"];
export const UNCLUSTERED_FILTER: maplibregl.FilterSpecification = [
  "!",
  ["has", "point_count"],
];

/** Individual-detection filter: not a cluster, and in the given backend state. */
export function unclusteredStateFilter(state: string): maplibregl.FilterSpecification {
  // Written inline rather than composed from UNCLUSTERED_FILTER: maplibre's
  // FilterSpecification is a recursive union that rejects a nested literal
  // built from an already-widened member.
  return [
    "all",
    ["!", ["has", "point_count"]],
    ["==", ["get", "state"], state],
  ] as unknown as maplibregl.FilterSpecification;
}

/** The label is a count of detections - never a count of fires or incidents. */
export const CLUSTER_COUNT_FIELD: maplibregl.ExpressionSpecification = [
  "get",
  "point_count_abbreviated",
];

const CLUSTER_COLOR_STOPS: maplibregl.ExpressionSpecification = [
  "step",
  ["get", "point_count"],
  "#5ac8fa",
  25,
  "#ff9f0a",
  100,
  "#ff3b30",
];

const CLUSTER_RADIUS_STOPS: maplibregl.ExpressionSpecification = [
  "step",
  ["get", "point_count"],
  15,
  25,
  20,
  100,
  26,
];

export default function DetectionMap({
  detections,
  lang,
  dict,
  detail,
  detailStale,
  onSelect,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const popup = useRef<maplibregl.Popup | null>(null);
  const detectionsRef = useRef<Detection[]>(detections);
  detectionsRef.current = detections;
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  // Pushes the latest detections into the source. Returns false when the map
  // or style is not ready yet, so callers can defer to the load event instead
  // of dropping data that arrived before the style finished loading.
  const applyData = useCallback((): boolean => {
    const m = map.current;
    if (!m || !m.isStyleLoaded()) return false;
    const src = m.getSource(SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    if (!src) return false;
    src.setData({
      type: "FeatureCollection",
      features: detectionsRef.current.map((d) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [d.lon, d.lat] },
        properties: { ...d },
      })),
    });
    return true;
  }, []);

  useEffect(() => {
    if (!container.current || map.current) return;
    map.current = new maplibregl.Map({
      container: container.current,
      style: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
      center: [2.6, 28.5],
      zoom: 5,
    });
    map.current.on("load", () => {
      const m = map.current;
      if (!m) return;
      m.addSource(SOURCE_ID, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
        ...CLUSTER_OPTIONS,
      });

      // Grouped detections.
      m.addLayer({
        id: CLUSTER_LAYER_ID,
        type: "circle",
        source: SOURCE_ID,
        filter: CLUSTER_FILTER,
        paint: {
          "circle-color": CLUSTER_COLOR_STOPS,
          "circle-radius": CLUSTER_RADIUS_STOPS,
          "circle-opacity": 0.85,
          "circle-stroke-color": "#0b0e11",
          "circle-stroke-width": 1,
        },
      });
      m.addLayer({
        id: CLUSTER_COUNT_LAYER_ID,
        type: "symbol",
        source: SOURCE_ID,
        filter: CLUSTER_FILTER,
        layout: {
          "text-field": CLUSTER_COUNT_FIELD,
          "text-font": ["Open Sans Regular"],
          "text-size": 12,
        },
        paint: { "text-color": "#0b0e11" },
      });

      // Individual detections. Excluded from clusters above, split by state.
      m.addLayer({
        id: LIVE_LAYER_ID,
        type: "circle",
        source: SOURCE_ID,
        filter: unclusteredStateFilter("LIVE"),
        paint: {
          "circle-color": "#ff3b30",
          "circle-radius": [
            "interpolate", ["linear"], ["sqrt", ["coalesce", ["get", "frp"], 0]],
            0, 5, 6, 14,
          ],
          "circle-opacity": 0.8,
          "circle-stroke-color": "#0b0e11",
          "circle-stroke-width": 1,
        },
      });
      m.addLayer({
        id: HISTORICAL_LAYER_ID,
        type: "circle",
        source: SOURCE_ID,
        filter: unclusteredStateFilter("HISTORICAL"),
        paint: {
          "circle-color": "#ff9f0a",
          "circle-radius": [
            "interpolate", ["linear"], ["sqrt", ["coalesce", ["get", "frp"], 0]],
            0, 4, 6, 12,
          ],
          "circle-opacity": 0.7,
          "circle-stroke-color": "#0b0e11",
          "circle-stroke-width": 1,
        },
      });

      m.fitBounds(ALGERIA_BOUNDS, { padding: 24 });
      popup.current = new maplibregl.Popup({ closeButton: false, maxWidth: "260px" });

      m.on("click", (e) => {
        // A cluster expands to reveal the individual detections inside it.
        const clusters = m.queryRenderedFeatures(e.point, {
          layers: CLUSTER_LAYER_IDS,
        });
        if (clusters.length) {
          const clusterId = clusters[0].properties?.["cluster_id"];
          const geometry = clusters[0].geometry;
          const coordinates =
            geometry && geometry.type === "Point" ? geometry.coordinates : null;
          if (typeof clusterId === "number" && coordinates) {
            const center: [number, number] = [coordinates[0], coordinates[1]];
            const src = m.getSource(SOURCE_ID) as maplibregl.GeoJSONSource;
            void src
              .getClusterExpansionZoom(clusterId)
              .then((zoom) => m.easeTo({ center, zoom }))
              .catch(() => {
                /* expansion unavailable - leave the viewport unchanged */
              });
          }
          return;
        }

        const feats = m.queryRenderedFeatures(e.point, { layers: SELECTABLE_LAYER_IDS });
        if (!feats.length) return;
        const id = feats[0].properties?.["detection_id"];
        if (typeof id === "string" && id) onSelectRef.current(id);
      });

      m.on("mousemove", (e) => {
        const feats = m.queryRenderedFeatures(e.point, {
          layers: [...CLUSTER_LAYER_IDS, ...SELECTABLE_LAYER_IDS],
        });
        m.getCanvas().style.cursor = feats.length ? "pointer" : "";
      });

      // Data may have arrived before the style finished loading.
      applyData();
    });
    return () => {
      map.current?.remove();
      map.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dict, lang]);

  useEffect(() => {
    if (applyData()) return;
    // Style not ready: retry exactly once when it finishes loading.
    const m = map.current;
    if (!m) return;
    const retry = () => {
      applyData();
    };
    m.off("load", retry);
    m.once("load", retry);
  }, [detections, applyData]);

  // Authoritative detail drives the popup: fly to the detection and show the
  // GET /detections/{id} values, never stale list copies.
  useEffect(() => {
    const m = map.current;
    if (!m || !popup.current) return;
    if (!detail) {
      popup.current.remove();
      return;
    }
    m.flyTo({ center: [detail.lon, detail.lat], zoom: Math.max(m.getZoom(), 7) });
    popup.current
      .setLngLat([detail.lon, detail.lat])
      .setDOMContent(buildPopupNode(detail, dict, lang, detailStale))
      .addTo(m);
  }, [detail, detailStale, dict, lang]);

  return (
    <div className="map-wrap">
      <div ref={container} className="map" />
      <MapLegend dict={dict} />
    </div>
  );
}

/**
 * Build the popup as real DOM nodes.
 *
 * Detection fields are untrusted external data (they originate from FIRMS
 * CSV parsing). Every value is assigned through `textContent`, so markup in
 * a detection field is displayed literally and can never become an element
 * or an event handler. This replaces the previous setHTML() string build.
 */
export function buildPopupNode(
  d: Detection,
  dict: Dict,
  lang: Lang,
  stale: boolean
): HTMLElement {
  const root = document.createElement("div");
  root.className = "popup";
  root.setAttribute("dir", lang === "ar" ? "rtl" : "ltr");

  const heading = document.createElement("strong");
  heading.textContent =
    d.state === "LIVE" ? `● ${dict.live}` : `● ${dict.historical}`;
  root.appendChild(heading);

  const addRow = (label: string, value: string) => {
    const row = document.createElement("div");
    const name = document.createElement("span");
    name.textContent = label;
    const content = document.createElement("b");
    content.textContent = value;
    row.append(name, content);
    root.appendChild(row);
  };

  const orUnavailable = (v: string | null | undefined) =>
    v == null || v === "" ? dict.field_unavailable : v;

  addRow(
    dict.frp,
    typeof d.frp === "number" ? `${d.frp.toFixed(1)} MW` : dict.field_unavailable
  );
  addRow(
    dict.confidence,
    d.confidence == null
      ? dict.field_unavailable
      : `${Math.round(d.confidence * 100)}%${d.confidence_raw != null ? ` (${d.confidence_raw})` : ""}`
  );
  addRow(dict.wilaya, orUnavailable(d.wilaya_name ?? undefined));
  addRow(dict.acquired, fmtDate(d.acq_datetime, lang));
  addRow(dict.source, orUnavailable(d.source));
  addRow(dict.satellite, orUnavailable(d.satellite ?? undefined));

  const coords = document.createElement("div");
  coords.className = "popup-id";
  coords.textContent = `${d.lat.toFixed(3)}, ${d.lon.toFixed(3)}`;
  root.appendChild(coords);

  const id = document.createElement("div");
  id.className = "popup-id";
  id.textContent = d.detection_id;
  root.appendChild(id);

  if (stale) {
    const note = document.createElement("div");
    note.className = "popup-id";
    note.textContent = dict.detail_unavailable;
    root.appendChild(note);
  }

  return root;
}