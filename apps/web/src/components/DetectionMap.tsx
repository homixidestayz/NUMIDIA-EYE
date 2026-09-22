import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Detection, Lang } from "../types";
import type { Dict } from "../i18n";
import { fmtDate } from "../api";

interface Props {
  detections: Detection[];
  lang: Lang;
  dict: Dict;
}

const ALGERIA_BOUNDS: [[number, number], [number, number]] = [
  [-9, 18],
  [12, 38],
];

export default function DetectionMap({ detections, lang, dict }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const popup = useRef<maplibregl.Popup | null>(null);

  useEffect(() => {
    if (!container.current || map.current) return;
    map.current = new maplibregl.Map({
      container: container.current,
      style: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
      center: [2.6, 28.5],
      zoom: 5,
    });
    map.current.on("load", () => {
      map.current!.addSource("detections", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.current!.addLayer({
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
      map.current!.addLayer({
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
      map.current!.fitBounds(ALGERIA_BOUNDS, { padding: 24 });
      popup.current = new maplibregl.Popup({ closeButton: false, maxWidth: "260px" });
      map.current!.on("click", (e) => {
        const feats = map.current!.queryRenderedFeatures(e.point, {
          layers: ["live", "historical"],
        });
        if (!feats.length) return;
        const f = feats[0].properties as unknown as Detection & {
          frp: number;
          confidence: number | null;
        };
        popup.current!.setLngLat([f.lon, f.lat]).setHTML(
          popupHtml(f, dict, lang)
        ).addTo(map.current!);
      });
      map.current!.on("mousemove", (e) => {
        const feats = map.current!.queryRenderedFeatures(e.point, {
          layers: ["live", "historical"],
        });
        map.current!.getCanvas().style.cursor = feats.length ? "pointer" : "";
      });
    });
    return () => {
      map.current?.remove();
      map.current = null;
    };
  }, [dict, lang]);

  useEffect(() => {
    const m = map.current;
    if (!m || !m.isStyleLoaded()) return;
    const src = m.getSource("detections") as maplibregl.GeoJSONSource | undefined;
    if (!src) return;
    src.setData({
      type: "FeatureCollection",
      features: detections.map((d) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [d.lon, d.lat] },
        properties: { ...d },
      })),
    });
  }, [detections]);

  return <div ref={container} className="map" />;
}

function popupHtml(d: Detection & { frp: number; confidence: number | null }, dict: Dict, lang: Lang): string {
  const conf =
    d.confidence != null
      ? `${Math.round(d.confidence * 100)}% (${d.confidence_raw ?? "?"})`
      : "—";
  const stateTag = d.state === "LIVE" ? "● LIVE" : `● ${dict.historical}`;
  return `
    <div dir="${lang === "ar" ? "rtl" : "ltr"}" class="popup">
      <strong>${stateTag}</strong>
      <div>${dict.frp}: <b>${d.frp.toFixed(1)} MW</b></div>
      <div>${dict.confidence}: ${conf}</div>
      <div>${dict.acquired}: ${fmtDate(d.acq_datetime)}</div>
      <div>${dict.source}: ${d.source} · ${d.satellite ?? "?"}</div>
      <div class="popup-id">${d.detection_id}</div>
    </div>`;
}