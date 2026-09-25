import { useEffect, useMemo, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Detection, SystemBannerState } from "../types";

interface Props {
  detections: Detection[];
  selectedDetectionId: string | null;
  onSelectDetection: (id: string) => void;
  state: SystemBannerState;
  loading: boolean;
  error: string | null;
}

const ALGERIA_CENTER: [number, number] = [2.6, 28.5];
const ALGERIA_BOUNDS: [[number, number], [number, number]] = [[-9, 18], [12, 38]];

export default function DetectionMap({
  detections,
  selectedDetectionId,
  onSelectDetection,
  state,
  loading,
  error,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);

  const geojson = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: detections.map((d) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [d.lon, d.lat] },
        properties: {
          detection_id: d.detection_id,
          state: d.state,
          frp: d.frp,
        },
      })),
    }),
    [detections],
  );

  useEffect(() => {
    if (!container.current || map.current) return;

    const instance = new maplibregl.Map({
      container: container.current,
      style: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
      center: ALGERIA_CENTER,
      zoom: 5,
    });

    map.current = instance;

    instance.on("load", () => {
      instance.addSource("detections", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
        cluster: true,
        clusterRadius: 50,
        clusterMaxZoom: 8,
      });

      instance.addLayer({
        id: "clusters",
        type: "circle",
        source: "detections",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#0d7a47",
          "circle-radius": ["step", ["get", "point_count"], 14, 25, 18, 75, 22],
          "circle-opacity": 0.85,
          "circle-stroke-width": 1,
          "circle-stroke-color": "#b0f8cc",
        },
      });

      instance.addLayer({
        id: "cluster-count",
        type: "symbol",
        source: "detections",
        filter: ["has", "point_count"],
        layout: {
          "text-field": ["get", "point_count_abbreviated"],
          "text-size": 12,
        },
        paint: {
          "text-color": "#e8f7ef",
        },
      });

      instance.addLayer({
        id: "unclustered",
        type: "circle",
        source: "detections",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": [
            "case",
            ["==", ["get", "state"], "LIVE"],
            "#17c964",
            "#8ce99a",
          ],
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["sqrt", ["coalesce", ["get", "frp"], 0]],
            0,
            4,
            8,
            12,
          ],
          "circle-stroke-color": "#04140b",
          "circle-stroke-width": 1,
        },
      });

      instance.addLayer({
        id: "selected",
        type: "circle",
        source: "detections",
        filter: ["==", ["get", "detection_id"], ""],
        paint: {
          "circle-color": "rgba(0,0,0,0)",
          "circle-radius": 14,
          "circle-stroke-color": "#f8fffb",
          "circle-stroke-width": 2,
        },
      });

      instance.fitBounds(ALGERIA_BOUNDS, { padding: 28 });

      instance.on("click", "clusters", (event) => {
        const features = instance.queryRenderedFeatures(event.point, { layers: ["clusters"] });
        const cluster = features[0];
        const source = instance.getSource("detections") as maplibregl.GeoJSONSource;
        const clusterId = cluster.properties?.cluster_id as number | undefined;
        if (clusterId === undefined) return;
        void source.getClusterExpansionZoom(clusterId).then((zoom) => {
          if (!cluster.geometry || cluster.geometry.type !== "Point") return;
          instance.easeTo({
            center: cluster.geometry.coordinates as [number, number],
            zoom,
          });
        });
      });

      instance.on("click", "unclustered", (event) => {
        const feature = event.features?.[0];
        const detectionId = feature?.properties?.detection_id as string | undefined;
        if (detectionId) onSelectDetection(detectionId);
      });

      instance.on("mousemove", (event) => {
        const features = instance.queryRenderedFeatures(event.point, { layers: ["clusters", "unclustered"] });
        instance.getCanvas().style.cursor = features.length > 0 ? "pointer" : "";
      });
    });

    return () => {
      instance.remove();
      map.current = null;
    };
  }, [onSelectDetection]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !instance.isStyleLoaded()) return;
    const source = instance.getSource("detections") as maplibregl.GeoJSONSource | undefined;
    if (!source) return;
    source.setData(geojson);
  }, [geojson]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !instance.isStyleLoaded() || !instance.getLayer("selected")) return;
    instance.setFilter("selected", ["==", ["get", "detection_id"], selectedDetectionId ?? ""]);
  }, [selectedDetectionId]);

  return (
    <section className="map-panel">
      <div ref={container} className="map-canvas" />
      <div className="map-status">
        {loading && <span>Loading detections…</span>}
        {!loading && error && <span>{error}</span>}
        {!loading && !error && detections.length === 0 && <span>{state}: no detections available.</span>}
      </div>
    </section>
  );
}
