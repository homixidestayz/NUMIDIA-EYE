import { useCallback, useEffect, useMemo, useState } from "react";
import { api, loadAll, type Loaded } from "./api";
import type { Detection, Environment, LayerState, WorldCollection } from "./types";
import Header from "./components/Header";
import Timeline from "./components/Timeline";
import Sidebar from "./components/Sidebar";
import { wilayaCode } from "./geo";
import { BUCKET_COLORS, bucketLabel } from "./fire";
import { ATTRIBUTION } from "./attribution";
import { FlameIcon } from "./components/FlameIcon";
import { inRange, rangeStartUtc, type RangeId } from "./timeline";
import MapView from "./components/MapView";
import DetailPanel from "./components/DetailPanel";
import SearchModal from "./components/SearchModal";

export const DEFAULT_LAYERS: LayerState = {
  wilayas: true,
  detections: true,
  labels: true,
};

export type EnvPhase = "idle" | "loading" | "ready" | "unavailable";

export default function App() {
  const [world, setWorld] = useState<WorldCollection | null>(null);
  const [data, setData] = useState<Loaded | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [layers, setLayers] = useState<LayerState>(DEFAULT_LAYERS);

  /* Timeline. The window filters client-side over already-loaded detections;
     refetching per drag would cost seconds on every movement. */
  const [range, setRange] = useState<RangeId>("today");
  const [timeWindow, setTimeWindow] = useState<[Date, Date] | null>(null);
  const [replayT, setReplayT] = useState<number | null>(null);

  const [focusedWilaya, setFocusedWilaya] = useState<string | null>(null);
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);
  const [selectedDetection, setSelectedDetection] = useState<Detection | null>(null);

  const [environment, setEnvironment] = useState<Environment | null>(null);
  const [envPhase, setEnvPhase] = useState<EnvPhase>("idle");
  const [searchOpen, setSearchOpen] = useState(false);
  // Drawer state only matters below 900px, where the panels overlay the map.
  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);

  /* ── initial load ─────────────────────────────────────────── */
  useEffect(() => {
    let alive = true;
    setLoading(true);
    // World outlines are context, not data: a failure here must not hold up or
    // fail the whole app.
    api
      .world()
      .then((w) => alive && setWorld(w))
      .catch(() => alive && setWorld(null));
    loadAll()
      .then((d) => {
        if (alive) {
          setData(d);
          setLoadError(null);
        }
      })
      .catch((e: unknown) => {
        if (alive) setLoadError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  /* ── keyboard ─────────────────────────────────────────────── */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen((v) => !v);
      } else if (e.key === "Escape" && !typing) {
        setSearchOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  /* ── environment follows the selected incident ───────────── */
  const loadEnvironment = useCallback(async (incidentId: string | null) => {
    if (!incidentId) {
      setEnvironment(null);
      setEnvPhase("idle");
      return;
    }
    setEnvPhase("loading");
    try {
      const env = await api.environment(incidentId);
      setEnvironment(env);
      setEnvPhase(env.status === "AVAILABLE" ? "ready" : "unavailable");
    } catch (e) {
      setEnvironment(null);
      setEnvPhase("unavailable");
      void e;
    }
  }, []);

  const toggleLayer = useCallback((key: keyof LayerState) => {
    setLayers((l) => ({ ...l, [key]: !l[key] }));
  }, []);

  /* Picking a wilaya drops the incident selection: the panel was describing a
     different place and would otherwise keep claiming to describe this one. */
  const focusWilaya = useCallback((code: string | null) => {
    setFocusedWilaya((cur) => (cur && code && cur === code ? null : code));
    setSelectedIncidentId(null);
    setEnvironment(null);
    setEnvPhase("idle");
  }, []);

  const selectIncident = useCallback(
    (id: string) => {
      setSelectedIncidentId((cur) => (cur === id ? null : id));
    },
    [],
  );

  /* The incidents list carries wilaya NAMES ("Laghouat"); the boundary set and
     the detections carry codes ("03"). Without this translation, clicking an
     incident filters for a wilaya named "Laghouat" that no geometry matches and
     the map silently shows nothing. */
  const codeForWilayaName = useCallback(
    (name: string): string | null => {
      const f = data?.wilayas.features.find(
        (x) => x.properties.shapeName.toLowerCase() === name.trim().toLowerCase(),
      );
      return f ? wilayaCode(f) : null;
    },
    [data],
  );

  useEffect(() => {
    void loadEnvironment(selectedIncidentId);
  }, [selectedIncidentId, loadEnvironment]);

  /* Selecting an incident frames its wilaya. Resolved from the name the
     incidents API returns to the code the map is keyed by. */
  useEffect(() => {
    if (!selectedIncidentId || !data) return;
    const inc = data.incidents.find((i) => i.id === selectedIncidentId);
    const name = inc?.wilayas?.[0];
    if (!name) return;
    const code = codeForWilayaName(name);
    if (code) setFocusedWilaya(code);
  }, [selectedIncidentId, data, codeForWilayaName]);

  const detections = data?.detections ?? [];

  /* Real extent of what we actually hold, so the timeline can never offer a
     range wider than the data and silently show the same points. */
  const [spanStart, spanEnd] = useMemo(() => {
    if (!detections.length) {
      const now = new Date();
      return [new Date(now.getTime() - 24 * 3_600_000), now] as [Date, Date];
    }
    let lo = Infinity;
    let hi = -Infinity;
    for (const d of detections) {
      const t = Date.parse(d.acq_datetime);
      if (!Number.isFinite(t)) continue;
      if (t < lo) lo = t;
      if (t > hi) hi = t;
    }
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) {
      const now = new Date();
      return [new Date(now.getTime() - 24 * 3_600_000), now] as [Date, Date];
    }
    return [new Date(lo), new Date(hi)] as [Date, Date];
  }, [detections]);

  const effectiveWindow = useMemo<[Date, Date] | null>(() => {
    if (replayT !== null) return [spanStart, new Date(replayT)];
    if (timeWindow) return timeWindow;
    const s = rangeStartUtc(range, new Date(), spanStart, spanEnd);
    return s ? [s < spanStart ? spanStart : s, spanEnd] : null;
  }, [replayT, timeWindow, range, spanStart, spanEnd]);

  const inTime = useMemo(() => {
    const w = effectiveWindow;
    if (!w) return detections;
    return detections.filter((d) => inRange(d, w[0], w[1]));
  }, [detections, effectiveWindow]);

  const shown = useMemo(
    () =>
      focusedWilaya
        ? inTime.filter((d) => String(d.wilaya_code) === focusedWilaya)
        : inTime,
    [inTime, focusedWilaya],
  );

  const incident = useMemo(
    () => data?.incidents.find((i) => i.id === selectedIncidentId) ?? null,
    [data, selectedIncidentId],
  );

  const detailOpen = Boolean(incident || selectedDetection);
  const focusedWilayaName = focusedWilaya
    ? (data?.wilayas.features.find((f) => wilayaCode(f) === focusedWilaya)
        ?.properties.shapeName ?? null)
    : null;

  return (
    <div className={`app${detailOpen ? " has-detail" : ""}`}>
      <div className="stage">
        <MapView
          wilayas={data?.wilayas ?? null}
          world={world}
          detections={shown}
          layers={layers}
          focused={focusedWilaya}
          onFocusWilaya={focusWilaya}
          onSelectDetection={setSelectedDetection}
        />

        {/* Overlays live inside the map cell so they can never cover the rail. */}
        <div className="mapctl">
          {(
            [
              ["wilayas", "Wilayas"],
              ["detections", "Fires"],
              ["labels", "Labels"],
            ] as [keyof LayerState, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              className="mapbtn"
              aria-pressed={layers[key]}
              onClick={() => toggleLayer(key)}
            >
              {label}
            </button>
          ))}
          {/* Focusing a wilaya filters the detections to it. Without this the
              map quietly empties out and looks broken. */}
          {focusedWilaya && (
            <button
              className="mapbtn focus"
              onClick={() => focusWilaya(null)}
              title="Clear the wilaya filter"
            >
              Filtered to{" "}
              <b>
                {data?.wilayas.features.find((f) => wilayaCode(f) === focusedWilaya)
                  ?.properties.shapeName ?? focusedWilaya}
              </b>{" "}
              ✕
            </button>
          )}
        </div>

        {/* Only 8 of the 69 wilayas had detections today, so filtering to a
            wilaya most often yields nothing. An empty canvas reads as a broken
            map; say what is actually true instead. */}
        {!loading && shown.length === 0 && detections.length > 0 && (
          <div className="mapempty" role="status">
            <b>No detections in view</b>
            <span>
              {focusedWilaya
                ? `${focusedWilayaName ?? focusedWilaya} has none`
                : "None"}{" "}
              in the selected range. {detections.length.toLocaleString("en-GB")} are
              loaded — widen the range to see them.
            </span>
          </div>
        )}

        <div className="legend">
          <h3>Fire Radiative Power</h3>
          {BUCKET_COLORS.map((c, b) => (
            <div className="row" key={b}>
              <FlameIcon color={c} />
              <span>{bucketLabel(b)}</span>
            </div>
          ))}
          <div className="row">
            <i className="sq" />
            <span>Historical observation</span>
          </div>
        </div>

        <Timeline
          detections={detections}
          spanStart={spanStart}
          spanEnd={spanEnd}
          range={range}
          onRangeChange={setRange}
          window={timeWindow}
          onWindowChange={setTimeWindow}
          replayT={replayT}
          onReplayTick={setReplayT}
          loading={loading}
          onMapCount={shown.length}
        />
      </div>

      <Header
        status={data?.status ?? null}
        loading={loading}
        liveCount={shown.filter((d) => d.state === "LIVE").length}
        total={shown.length}
        onSearch={() => setSearchOpen(true)}
        onToggleLeft={() => setLeftOpen((v) => !v)}
        onToggleRight={() => setRightOpen((v) => !v)}
        leftOpen={leftOpen}
        rightOpen={rightOpen}
      />

      {(leftOpen || rightOpen) && (
        <div
          className="scrim"
          onClick={() => {
            setLeftOpen(false);
            setRightOpen(false);
          }}
        />
      )}

      <Sidebar
        open={leftOpen}
        layers={layers}
        onToggleLayer={toggleLayer}
        incidents={data?.incidents ?? []}
        selectedIncidentId={selectedIncidentId}
        onSelectIncident={selectIncident}
        loading={loading}
      />

      {/* No permanent right-hand slab. An always-present panel showing one
          sentence wasted 372px and read as a broken layout; it now appears only
          when there is a detection or incident to describe. */}
      {(incident || selectedDetection) && (
        <DetailPanel
          open={rightOpen}
          detection={selectedDetection}
          incident={incident}
          environment={environment}
          envPhase={envPhase}
          onVerify={api.verify}
          onRefreshEnv={() => loadEnvironment(selectedIncidentId)}
          onClose={() => {
            setSelectedDetection(null);
            setSelectedIncidentId(null);
            setEnvironment(null);
            setEnvPhase("idle");
          }}
        />
      )}

      <div className="attrib" aria-label="Data attribution">
        {ATTRIBUTION.map((c) => (
          <span key={c.label} title={c.detail}>
            <b>{c.label}</b>
            {c.detail}
          </span>
        ))}
        <span className="indep">
          Independent research prototype. Not affiliated with or endorsed by any government
          body. Not a fire-spread model.
        </span>
      </div>

      <footer className="foot">
        Independent research prototype. Not affiliated with any government body. Not a
        fire-spread model. Data: NASA FIRMS/VIIRS · Open-Meteo · GeoAlgeria (ODbL).
      </footer>

      {searchOpen && (
        <SearchModal
          wilayas={data?.wilayas ?? null}
          detections={detections}
          onClose={() => setSearchOpen(false)}
          onPick={(code) => {
            focusWilaya(code);
            setSearchOpen(false);
          }}
        />
      )}

      {loadError && (
        <div className="banner" role="alert">
          <b>Cannot reach the API.</b> {loadError} — start it with
          <code>uv run uvicorn numidia_api.app:app --port 8010</code> and reload.
        </div>
      )}
    </div>
  );
}