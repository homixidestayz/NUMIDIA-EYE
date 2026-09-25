import { useCallback, useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Detection, Lang } from "../types";
import type { Dict } from "../i18n";
import { fmtDate } from "../api";

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
    const src = m.getSource("detections") as maplibregl.GeoJSONSource | undefined;
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
      m.addSource("detections", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      m.addLayer({
        id: "live",
        type: "circle",
        source: "detections",
        filter: ["==", ["get", "state"], "LIVE"],
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
        id: "historical",
        type: "circle",
        source: "detections",
        filter: ["==", ["get", "state"], "HISTORICAL"],
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
        const feats = m.queryRenderedFeatures(e.point, {
          layers: ["live", "historical"],
        });
        if (!feats.length) return;
        const id = feats[0].properties?.["detection_id"];
        if (typeof id === "string" && id) onSelectRef.current(id);
      });
      m.on("mousemove", (e) => {
        const feats = m.queryRenderedFeatures(e.point, {
          layers: ["live", "historical"],
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
      .setHTML(popupHtml(detail, dict, lang, detailStale))
      .addTo(m);
  }, [detail, detailStale, dict, lang]);

  return <div ref={container} className="map" />;
}

function popupHtml(
  d: Detection,
  dict: Dict,
  lang: Lang,
  stale: boolean
): string {
  const conf =
    d.confidence != null
      ? `${Math.round(d.confidence * 100)}% (${d.confidence_raw ?? "?"})`
      : "—";
  const stateTag = d.state === "LIVE" ? "● LIVE" : `● ${dict.historical}`;
  const frp = typeof d.frp === "number" ? d.frp.toFixed(1) : "—";
  return `
    <div dir="${lang === "ar" ? "rtl" : "ltr"}" class="popup">
      <strong>${stateTag}</strong>
      <div>${dict.frp}: <b>${frp} MW</b></div>
      <div>${dict.confidence}: ${conf}</div>
      <div>${dict.acquired}: ${fmtDate(d.acq_datetime)}</div>
      <div>${dict.source}: ${d.source} · ${d.satellite ?? "?"}</div>
      <div class="popup-id">${d.detection_id}</div>
      ${stale ? `<div class="popup-id">${dict.detail_unavailable}</div>` : ""}
    </div>`;
}
