import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import type { Detection, WilayaCollection, WorldCollection } from "../types";
import type { LayerState } from "../types";
import { anchorOf, areaOf, boundsOf, wilayaCode } from "../geo";
import { BUCKET_COUNT, bucketFor, flameImageData, matchExpression } from "../fire";

export { anchorOf, exteriorRing, wilayaCode } from "../geo";

interface Props {
  wilayas: WilayaCollection | null;
  /** World outlines for context, so the map can be zoomed out to a globe view
   *  with Algeria still readable. Local GeoJSON — no tile server. */
  world: WorldCollection | null;
  detections: Detection[];
  layers: LayerState;
  focused: string | null;
  onFocusWilaya: (code: string | null) => void;
  onSelectDetection: (d: Detection) => void;
}

/* An explicit, visible style background. A blank style with no background
   leaves the canvas transparent, so the map inherits the page colour and the
   whole thing reads as "nothing loaded". */
const BLANK_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {},
  layers: [
    {
      id: "bg",
      type: "background",
      paint: { "background-color": "#010101" },
    },
  ],
};

/* Land had to be lifted well clear of the page background: fill #12201a over
   #070b09 is a 3-point lightness difference, which renders as an empty page
   rather than a map. */
/* Land must stay clearly lighter than the #010101 backdrop. At #232323 on
   #0a0a0a the country read as a void with a faint outline, which looks like a
   failed load rather than a map. */
const FILL = "#1c1c1c";
const LINE = "#3f3f46";

export default function MapView({
  wilayas,
  world,
  detections,
  layers,
  focused,
  onFocusWilaya,
  onSelectDetection,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Quantised so a drag re-runs the declutter on whole zoom steps instead of
  // every frame: rebuilding 69 DOM markers per frame is visible jank.
  const [zoom, setZoom] = useState(4);

  // Effects below must wait for the style to load. A plain ref would not
  // re-render, so setData would fire before the sources existed and be dropped
  // on the floor, leaving an empty map with no error to show for it.
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({
        container: containerRef.current,
        style: BLANK_STYLE,
        center: [3.2, 27.5],
        zoom: 4.9,
        /* Low enough to pull back to a globe view, as the reference atlas allows. */
        minZoom: 1.1,
        maxZoom: 12,
        attributionControl: false,
        dragRotate: false,
      });
    } catch (e) {
      // Most often WebGL is unavailable. Without this the panel is just an
      // empty box and "no map" is indistinguishable from "no data".
      setError(
        `Map could not start: ${e instanceof Error ? e.message : String(e)}. ` +
          `This view needs WebGL.`,
      );
      return;
    }

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");

    // The container is sized by flexbox; if MapLibre measures it before layout
    // settles it can end up 0x0 and paint nothing until resized. Guarded
    // because ResizeObserver is absent in jsdom and in older Safari.
    const ro =
      typeof ResizeObserver === "function"
        ? new ResizeObserver(() => map.resize())
        : null;
    if (ro && containerRef.current) ro.observe(containerRef.current);

    map.on("error", (e) => {
      // Style/tile errors are recoverable per-feature; surface them rather
      // than letting the map sit there half-drawn.
      setError((prev) => prev ?? `Map error: ${e?.error?.message ?? "unknown"}`);
    });

    map.on("load", () => {
      /* World outlines first, so Algeria draws over them. Deliberately faint:
         they are context, not content. */
      map.addSource("world", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "world-fill",
        type: "fill",
        source: "world",
        paint: { "fill-color": "#15151a", "fill-opacity": 1 },
      });
      map.addLayer({
        id: "world-line",
        type: "line",
        source: "world",
        paint: { "line-color": "#2b2b33", "line-width": 0.6, "line-opacity": 1 },
      });

      map.addSource("wilayas", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "wil-fill",
        type: "fill",
        source: "wilayas",
        paint: { "fill-color": FILL, "fill-opacity": 0.95 },
      });
      map.addLayer({
        id: "wil-line",
        type: "line",
        source: "wilayas",
        paint: { "line-color": LINE, "line-width": 1.2, "line-opacity": 1 },
      });
      map.addLayer({
        id: "wil-active",
        type: "fill",
        source: "wilayas",
        filter: ["==", ["get", "on"], true],
        paint: { "fill-color": "#333333", "fill-opacity": 1 },
      });
      map.addLayer({
        id: "wil-active-line",
        type: "line",
        source: "wilayas",
        filter: ["==", ["get", "on"], true],
        paint: { "line-color": "#22c55e", "line-width": 2.5, "line-opacity": 1 },
      });

      map.addSource("detections", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
        // No clustering, by request: an aggregate circle is not a fire. Every
        // stored detection draws its own flame so what is on screen maps
        // one-to-one onto what the API returned.
      });

      for (let b = 0; b < BUCKET_COUNT; b++) {
        map.addImage(`flame-${b}`, flameImageData(b, 64), { pixelRatio: 2 });
      }

      map.addLayer({
        id: "det",
        type: "symbol",
        source: "detections",
        layout: {
          "icon-image": matchExpression() as never,
          "icon-size": ["interpolate", ["linear"], ["get", "frp"], 0, 0.32, 10, 0.4, 100, 0.55, 500, 0.75, 2000, 1.05],
          "icon-anchor": "bottom",
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        },
        paint: {
          // Historical observations stay legible but unmistakably not-current.
          "icon-opacity": ["case", ["==", ["get", "state"], "HISTORICAL"], 0.45, 1],
        },
      });

      const open = (d: Detection) => onSelectDetection(d);

      map.on("click", "wil-fill", (e) => {
        const code = e.features?.[0]?.properties?.code;
        if (code != null) onFocusWilaya(String(code));
      });

      const toDetection = (f: GeoJSON.Feature): Detection => {
        const p = f.properties ?? {};
        const coords = (f.geometry as GeoJSON.Point).coordinates as [number, number];
        const num = (v: unknown): number | null =>
          typeof v === "number" && Number.isFinite(v) ? v : null;
        const str = (v: unknown): string | null => (v == null ? null : String(v));
        return {
          detection_id: String(p.id ?? ""),
          lat: coords[1],
          lon: coords[0],
          acq_datetime: String(p.acq_datetime ?? ""),
          satellite: String(p.satellite ?? "Unavailable"),
          instrument: "",
          confidence: num(p.confidence),
          confidence_raw: str(p.confidence_raw),
          bright_ti4: num(p.bright_ti4),
          bright_ti5: num(p.bright_ti5),
          frp: num(p.frp),
          daynight: str(p.daynight),
          state: (str(p.state) ?? "UNAVAILABLE") as Detection["state"],
          source: String(p.source ?? ""),
          source_url: str(p.source_url),
          fetched_at: String(p.fetched_at ?? ""),
          wilaya_code: str(p.wilaya_code),
          wilaya_name: str(p.wilaya_name),
        };
      };

      map.on("click", "det", (e) => {
        const f = e.features?.[0];
        if (f) open(toDetection(f as GeoJSON.Feature));
      });

      for (const id of ["wil-fill", "det"]) {
        map.on("mouseenter", id, () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", id, () => {
          map.getCanvas().style.cursor = "";
        });
      }

      // Every effect below reads mapRef.current and returns early when it is
      // null. It has to be assigned before setReady, or they all bail and the
      // map stays empty while the UI happily reports the loaded counts.
      mapRef.current = map;
      // Dev-only handle so the map's own state can be inspected from a console
      // or a CDP probe. Strips from the production bundle.
      if (import.meta.env.DEV) {
        (window as unknown as { __atlasMap?: maplibregl.Map }).__atlasMap = map;
      }
      map.on("zoomend", () => setZoom(Math.round(map.getZoom())));
      setReady(true);
    });

    return () => {
      ro?.disconnect();
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      mapRef.current = null;
      setReady(false);
      map.remove();
    };
    // onFocusWilaya/onSelectDetection are read through stable callbacks.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ── world outlines ───────────────────────────────────────── */
  useEffect(() => {
    if (!ready || !world) return;
    const src = mapRef.current?.getSource("world") as maplibregl.GeoJSONSource | undefined;
    if (!src) return;
    src.setData({
      type: "FeatureCollection",
      features: world.features.map((f) => ({
        type: "Feature" as const,
        geometry: f.geometry,
        properties: { admin: f.properties.ADMIN ?? f.properties.NAME ?? "" },
      })),
    });
  }, [world, ready]);

  /* ── wilayas ──────────────────────────────────────────────── */
  useEffect(() => {
    if (!ready) return;
    const src = mapRef.current?.getSource("wilayas") as maplibregl.GeoJSONSource | undefined;
    if (!src) return;
    src.setData({
      type: "FeatureCollection",
      features: (wilayas?.features ?? []).map((f) => ({
        type: "Feature" as const,
        geometry: f.geometry,
        properties: {
          code: wilayaCode(f),
          name: f.properties.shapeName,
          on: wilayaCode(f) === focused,
        },
      })),
    });
  }, [wilayas, focused, ready]);

  /* ── detections ───────────────────────────────────────────── */
  useEffect(() => {
    if (!ready) return;
    const src = mapRef.current?.getSource("detections") as maplibregl.GeoJSONSource | undefined;
    if (!src) return;
    src.setData({
      type: "FeatureCollection",
      features: detections.map((d) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [d.lon, d.lat] as [number, number] },
        properties: {
          id: d.detection_id,
          state: d.state,
          frp: d.frp ?? 0,
          frpBucket: bucketFor(d.frp),
          acq_datetime: d.acq_datetime,
          satellite: d.satellite,
          confidence: d.confidence ?? -1,
          wilaya_code: d.wilaya_code,
          wilaya_name: d.wilaya_name,
        },
      })),
    });
  }, [detections, ready]);

  /* ── layer visibility ────────────────────────────────────── */
  useEffect(() => {
    if (!ready) return;
    const map = mapRef.current;
    if (!map) return;
    const set = (id: string, visible: boolean) => {
      if (map.getLayer(id)) {
        map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
      }
    };
    set("wil-fill", layers.wilayas);
    set("wil-line", layers.wilayas);
    set("wil-active", layers.wilayas);
    set("wil-active-line", layers.wilayas);
    set("det", layers.detections);
  }, [layers, ready]);

  /* ── labels ──────────────────────────────────────────────── */
  useEffect(() => {
    if (!ready) return;
    const map = mapRef.current;
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];
    if (!map || !layers.labels || !wilayas) return;

    /* Northern Algeria packs a dozen wilayas into a few hundred pixels, so
       placing all 69 produces an unreadable smear. Place greedily by area, and
       drop any label whose box would collide with one already placed. */
    const entries = wilayas.features
      .map((f) => ({
        code: wilayaCode(f),
        name: f.properties.shapeName,
        anchor: anchorOf(f.geometry),
        area: areaOf(f.geometry),
      }))
      .filter((e) => e.anchor !== null)
      .sort((a, b) => b.area - a.area);

    const placed: DOMRect[] = [];

    /* Two passes, deliberately. Appending a marker and immediately reading its
       box interleaves writes with reads, so the browser is forced to re-run
       layout once per label — 69 synchronous layouts on every zoom change.
       Append everything first, then measure, then decide. */
    const nodes: { el: HTMLElement; code: string }[] = [];
    for (const e of entries) {
      const el = document.createElement("button");
      el.type = "button";
      el.className = "wlabel";
      el.textContent = e.name;
      el.title = `${e.name} (DZ-${e.code})`;
      el.dataset.code = e.code;
      if (e.code === focused) el.classList.add("on");
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        onFocusWilaya(e.code);
      });
      markersRef.current.push(
        new maplibregl.Marker({ element: el, anchor: "center" })
          .setLngLat(e.anchor!)
          .addTo(map),
      );
      nodes.push({ el, code: e.code });
    }

    for (const n of nodes) n.el.style.visibility = "hidden";
    for (const { el, code } of nodes) {
      const rect = el.getBoundingClientRect();
      const isFocused = code === focused;
      const hit = placed.some(
        (p) =>
          rect.left < p.right &&
          rect.right > p.left &&
          rect.top < p.bottom &&
          rect.bottom > p.top,
      );
      if (hit && !isFocused) {
        // Keep the node so the label can reappear when zoomed in.
        el.style.display = "none";
      } else {
        el.style.visibility = "visible";
        placed.push(rect);
      }
    }
    // onFocusWilaya is stable from App.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wilayas, layers.labels, focused, ready, zoom]);

  /* ── frame the focused wilaya ────────────────────────────── */
  useEffect(() => {
    if (!ready || !focused || !wilayas) return;
    const map = mapRef.current;
    if (!map) return;
    const feat = wilayas.features.find((f) => wilayaCode(f) === focused);
    if (!feat) return;
    const b = boundsOf(feat.geometry);
    if (!b) return;
    /* Cap the zoom. Fitting a whole wilaya filled the screen with it, and a
       quiet wilaya then rendered as an empty dark field — which reads as the
       map having crashed rather than as "two fires here". */
    map.fitBounds(b, { padding: 90, maxZoom: 5.8, duration: 600 });
  }, [focused, wilayas, ready]);

  /* ── painted ─────────────────────────────────────────────── */
  // What the map has actually drawn, as opposed to what React was handed.
  // Reporting prop counts is how the earlier "map is blank" bug stayed hidden:
  // the badge read "69 wilayas" while the canvas held nothing.
  const [painted, setPainted] = useState(0);
  useEffect(() => {
    if (!ready) return;
    const map = mapRef.current;
    if (!map) return;

    /* "render" fires once per animation frame. Calling queryRenderedFeatures
       and pushing it into state on every frame forces a full React reconcile
       per frame during any pan or zoom. Throttle: the badge only needs to be
       roughly current, not frame-accurate. */
    let timer = 0;
    const sample = () => {
      timer = 0;
      try {
        setPainted(map.queryRenderedFeatures().length);
      } catch {
        /* map torn down mid-sample */
      }
    };
    const onRender = () => {
      if (timer) return;
      timer = window.setTimeout(sample, 250);
    };
    sample();
    map.on("render", onRender);
    map.on("moveend", sample);
    map.on("idle", sample);
    return () => {
      if (timer) window.clearTimeout(timer);
      map.off("render", onRender);
      map.off("moveend", sample);
      map.off("idle", sample);
    };
  }, [ready, zoom, focused]);

  return (
    <>
      <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />
      {/* Provenance readout. Doubles as the answer to "is anything actually
          on this map" without needing devtools. */}
      <div className="mapstat">
        {error
          ? "failed"
          : !ready
            ? "starting map…"
            : painted === 0
              ? `loading ${wilayas?.features.length ?? 0} wilayas…`
              : `${painted} features drawn · ${wilayas?.features.length ?? 0} wilayas · ${detections.length} detections`}
      </div>
      {error && (
        <div className="mapfail" role="alert">
          <b>Map unavailable.</b> {error}
        </div>
      )}
    </>
  );
}