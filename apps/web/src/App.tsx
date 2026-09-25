import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Database,
  Map,
  Radar,
  Settings,
} from "lucide-react";
import { api, fmtDate, isApiError } from "./api";
import DetectionMap from "./components/DetectionMap";
import { asNumber, asText, calculateKpis, DATA_UNAVAILABLE, latestIngestionTime, mapBannerState, NOT_YET_AVAILABLE, UNAVAILABLE } from "./state";
import type {
  AiResult,
  Detection,
  IncidentsResponse,
  SystemBannerState,
  SystemData,
  SystemStatus,
} from "./types";

type NavItemKey = "Dashboard" | "Incidents" | "Map" | "Reports" | "Alerts" | "Data Sources" | "Settings";

interface NavItem {
  key: NavItemKey;
  icon: typeof Activity;
}

const NAV_ITEMS: NavItem[] = [
  { key: "Dashboard", icon: Activity },
  { key: "Incidents", icon: AlertTriangle },
  { key: "Map", icon: Map },
  { key: "Reports", icon: BarChart3 },
  { key: "Alerts", icon: Radar },
  { key: "Data Sources", icon: Database },
  { key: "Settings", icon: Settings },
];

export default function App() {
  const [active, setActive] = useState<NavItemKey>("Dashboard");
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [systemData, setSystemData] = useState<SystemData | null>(null);
  const [detections, setDetections] = useState<Detection[]>([]);
  const [incidents, setIncidents] = useState<IncidentsResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [aiResult, setAiResult] = useState<AiResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const selectedDetection = useMemo(
    () => detections.find((d) => d.detection_id === selectedId) ?? null,
    [detections, selectedId],
  );

  const bannerState = mapBannerState(status);
  const kpis = calculateKpis(detections);
  const latestIngestion = latestIngestionTime(detections);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      try {
        const [nextStatus, nextData, nextDetections, nextIncidents] = await Promise.all([
          api.status(),
          api.systemData(),
          api.detections(500),
          api.incidents(),
        ]);
        if (cancelled) return;
        setStatus(nextStatus);
        setSystemData(nextData);
        setDetections(nextDetections);
        setIncidents(nextIncidents);
        setError(null);
        setLastUpdated(new Date().toISOString());
      } catch (err: unknown) {
        if (cancelled) return;
        setStatus(null);
        setSystemData(null);
        setDetections([]);
        setIncidents(null);
        if (isApiError(err)) {
          setError(`${err.message}. Backend unavailable.`);
        } else {
          setError("API unreachable — system state unavailable.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedDetection) {
      setAiResult(null);
      return;
    }
    const detectionId = selectedDetection.detection_id;
    let cancelled = false;

    async function loadAi() {
      try {
        const next = await api.ai(detectionId);
        if (!cancelled) setAiResult(next);
      } catch {
        if (!cancelled) {
          setAiResult({
            status: "AI_UNAVAILABLE",
            detection_id: detectionId,
            message: "No validated production model is currently registered.",
          });
        }
      }
    }

    void loadAi();

    return () => {
      cancelled = true;
    };
  }, [selectedDetection]);

  const recentDetections = detections.slice(0, 10);

  return (
    <div className="command-center">
      <aside className="app-sidebar">
        <div className="brand-block">
          <h1>NUMIDIA EYE</h1>
          <p>AI-Powered Wildfire Intelligence</p>
        </div>
        <nav>
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.key}
                className={`nav-item ${active === item.key ? "active" : ""}`}
                onClick={() => setActive(item.key)}
              >
                <Icon size={16} />
                <span>{item.key}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      <div className="app-main">
        <header className="app-header">
          <div>
            <h2>NUMIDIA EYE</h2>
            <p>AI-Powered Wildfire Intelligence</p>
          </div>
          <div className="header-chips">
            <StatusChip label="System" value={bannerState} state={bannerState} />
            <StatusChip label="FIRMS" value={status?.firms ?? UNAVAILABLE} state={bannerState} />
            <StatusChip label="AI" value={status?.ai ?? UNAVAILABLE} state={status?.ai === "READY" ? "LIVE" : "UNAVAILABLE"} />
            <StatusChip label="Last update" value={fmtDate(lastUpdated)} state="STALE" />
          </div>
        </header>

        {error && <div className="alert-row">{error}</div>}

        <main className="content-area">
          {active === "Dashboard" && (
            <>
              <section className="kpi-grid">
                <KpiCard title="Active detections" value={kpis.active} />
                <KpiCard title="Recent detections (24h)" value={kpis.recent} />
                <KpiCard title="High-FRP detections (>=50 MW)" value={kpis.highFrp} />
                <KpiCard title="Satellites reporting" value={kpis.satellites} />
                <KpiCard title="Latest ingestion time" value={fmtDate(latestIngestion)} />
              </section>

              <section className="dashboard-grid">
                <DetectionMap
                  detections={detections}
                  selectedDetectionId={selectedId}
                  onSelectDetection={setSelectedId}
                  state={bannerState}
                  loading={loading}
                  error={error}
                />
                <div className="stack-col">
                  <Panel title="Recent Incidents">
                    <p className="muted">Status: {asText(incidents?.status)}</p>
                    <p className="muted">{asText(incidents?.message, DATA_UNAVAILABLE)}</p>
                    {incidents?.incidents.length ? (
                      <ul className="simple-list">
                        {incidents.incidents.map((incident, idx) => (
                          <li key={String(incident.id ?? idx)}>{asText(incident.id, "Incident")}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="muted">No real incidents available from backend.</p>
                    )}
                  </Panel>
                  <Panel title="Recent Detections">
                    {recentDetections.length === 0 && <p className="muted">No detections available.</p>}
                    {recentDetections.map((d) => (
                      <button
                        key={d.detection_id}
                        className={`detection-row ${selectedId === d.detection_id ? "selected" : ""}`}
                        onClick={() => setSelectedId(d.detection_id)}
                      >
                        <strong>{asText(d.detection_id)}</strong>
                        <span>{asNumber(d.lat)} , {asNumber(d.lon)}</span>
                        <span>{fmtDate(d.acq_datetime)}</span>
                      </button>
                    ))}
                  </Panel>
                </div>
              </section>

              <section className="detail-grid">
                <Panel title="Detection Details">
                  {selectedDetection ? <DetectionDetails detection={selectedDetection} /> : <p className="muted">Select a real detection on the map.</p>}
                </Panel>
                <Panel title="AI Verification">
                  {selectedDetection ? (
                    <AiPanel aiResult={aiResult} />
                  ) : (
                    <p className="muted">Select a detection to request backend AI state.</p>
                  )}
                </Panel>
                <Panel title="GIS + Environment">
                  <p>Wilaya: <strong>{asText(selectedDetection?.wilaya_name, DATA_UNAVAILABLE)}</strong></p>
                  <p>Terrain: <strong>{DATA_UNAVAILABLE}</strong></p>
                  <p>Vegetation: <strong>{DATA_UNAVAILABLE}</strong></p>
                  <p>Roads/accessibility: <strong>{DATA_UNAVAILABLE}</strong></p>
                  <p>Settlements: <strong>{DATA_UNAVAILABLE}</strong></p>
                  <p>Protected areas: <strong>{DATA_UNAVAILABLE}</strong></p>
                  <p>Weather: <strong>{DATA_UNAVAILABLE}</strong></p>
                </Panel>
                <Panel title="Priority">
                  <p>Priority assessment unavailable</p>
                </Panel>
              </section>
            </>
          )}

          {active === "Map" && (
            <section className="single-page-map">
              <DetectionMap
                detections={detections}
                selectedDetectionId={selectedId}
                onSelectDetection={setSelectedId}
                state={bannerState}
                loading={loading}
                error={error}
              />
              <Panel title="Detection Details">
                {selectedDetection ? <DetectionDetails detection={selectedDetection} /> : <p className="muted">Select a detection marker.</p>}
              </Panel>
            </section>
          )}

          {active === "Incidents" && (
            <Panel title="Incidents">
              <p>Status: <strong>{asText(incidents?.status, NOT_YET_AVAILABLE)}</strong></p>
              <p>{asText(incidents?.message, DATA_UNAVAILABLE)}</p>
            </Panel>
          )}

          {active === "Reports" && (
            <Panel title="Reports">
              <p>Reports are generated from real incident data when available.</p>
              <p>Current backend incidents status: <strong>{asText(incidents?.status, NOT_YET_AVAILABLE)}</strong></p>
              <p>Available report data: <strong>{incidents?.incidents.length ? "Incident-backed records available" : DATA_UNAVAILABLE}</strong></p>
            </Panel>
          )}

          {active === "Alerts" && (
            <Panel title="Alerts">
              <p><strong>PROTOTYPE ONLY</strong></p>
              <p>No authorized Algerian Civil Protection integration is exposed by current backend routes.</p>
              <p>Backend AI status: <strong>{status?.ai ?? UNAVAILABLE}</strong></p>
            </Panel>
          )}

          {active === "Data Sources" && (
            <section className="panel-grid">
              <Panel title="LIVE">
                <p>NASA FIRMS / VIIRS NRT</p>
                <p>Connection: <strong>{status?.firms ?? UNAVAILABLE}</strong></p>
              </Panel>
              <Panel title="EXPERIMENTAL">
                <p>geoBoundaries Wilaya enrichment</p>
                <p>Current value availability: <strong>{selectedDetection?.wilaya_name ? "Available on selected detection" : DATA_UNAVAILABLE}</strong></p>
              </Panel>
              <Panel title="PLANNED">
                <p>Validated AI verification model registration</p>
                <p>Status: <strong>{status?.ai === "READY" ? "Activated" : NOT_YET_AVAILABLE}</strong></p>
              </Panel>
            </section>
          )}

          {active === "Settings" && (
            <section className="panel-grid">
              <Panel title="Runtime Configuration">
                <p>Frontend API base: <strong>{api.baseUrl}</strong></p>
                <p>System state: <strong>{status?.data_state ?? UNAVAILABLE}</strong></p>
                <p>Backend database: <strong>{status?.db ?? UNAVAILABLE}</strong></p>
              </Panel>
              <Panel title="Backend Freshness">
                <p>Last successful ingestion: <strong>{fmtDate(systemData?.last_ok_at)}</strong></p>
                <p>Live window hours: <strong>{asText(systemData?.live_window_hours, UNAVAILABLE)}</strong></p>
                <p>Latest acquisition: <strong>{fmtDate(systemData?.max_acq)}</strong></p>
              </Panel>
            </section>
          )}
        </main>
      </div>
    </div>
  );
}

function KpiCard({ title, value }: { title: string; value: number | string }) {
  return (
    <article className="kpi-card">
      <span>{title}</span>
      <strong>{value}</strong>
    </article>
  );
}

function StatusChip({ label, value, state }: { label: string; value: string; state: SystemBannerState }) {
  return (
    <div className={`status-chip ${state.toLowerCase()}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="panel">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function DetectionDetails({ detection }: { detection: Detection }) {
  return (
    <div className="details-grid">
      <Detail label="Detection ID" value={asText(detection.detection_id)} />
      <Detail label="Latitude" value={asNumber(detection.lat)} />
      <Detail label="Longitude" value={asNumber(detection.lon)} />
      <Detail label="Satellite" value={asText(detection.satellite)} />
      <Detail label="Instrument" value={asText(detection.instrument)} />
      <Detail label="Acquisition time" value={fmtDate(detection.acq_datetime)} />
      <Detail label="FRP" value={typeof detection.frp === "number" ? `${detection.frp.toFixed(1)} MW` : UNAVAILABLE} />
      <Detail label="Brightness temperature" value={typeof detection.bright_ti4 === "number" ? `${detection.bright_ti4.toFixed(1)} K` : UNAVAILABLE} />
      <Detail label="Confidence" value={detection.confidence != null ? String(detection.confidence) : UNAVAILABLE} />
      <Detail label="Day/Night" value={asText(detection.daynight)} />
      <Detail label="Source" value={asText(detection.source)} />
      <Detail label="Data freshness" value={asText(detection.state)} />
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="detail-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function AiPanel({ aiResult }: { aiResult: AiResult | null }) {
  if (!aiResult) {
    return <p className="muted">Checking backend AI status…</p>;
  }

  if (aiResult.status === "AI_UNAVAILABLE") {
    return (
      <div>
        <p><strong>AI VERIFICATION</strong></p>
        <p>Production verification unavailable</p>
        <p>Reason: No validated production model is currently registered.</p>
      </div>
    );
  }

  return (
    <div>
      <p>Status: <strong>{asText(aiResult.status)}</strong></p>
      <p>Model: <strong>{asText(aiResult.model, NOT_YET_AVAILABLE)}</strong></p>
      <p>Message: <strong>{asText(aiResult.message, NOT_YET_AVAILABLE)}</strong></p>
    </div>
  );
}
