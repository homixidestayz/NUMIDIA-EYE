import { useState } from "react";
import type { AiResult, Detection, Environment, Incident } from "../types";
import type { EnvPhase } from "../App";

interface Props {
  open: boolean;
  detection: Detection | null;
  incident: Incident | null;
  environment: Environment | null;
  envPhase: EnvPhase;
  onVerify: (id: string) => Promise<AiResult>;
  onRefreshEnv: () => void;
  onClose: () => void;
}

const stamp = (iso: string | null | undefined) => {
  if (!iso) return "Unavailable";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "Unavailable"
    : d.toLocaleString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
};

const n = (v: number | null | undefined, digits: number, unit = "") =>
  typeof v === "number" && Number.isFinite(v) ? `${v.toFixed(digits)}${unit}` : "Unavailable";

/** Bearing the wind blows TOWARD, from the "wind is FROM" convention Open-Meteo
 *  reports. A calm reading still gets a bearing; it is only drawn muted. */
function WindDial({ deg, speed }: { deg: number | null; speed: number | null }) {
  const from = typeof deg === "number" && Number.isFinite(deg) ? ((deg % 360) + 360) % 360 : 0;
  const to = (from + 180) % 360;
  const calm = !(typeof speed === "number" && speed > 0.05);
  const len = calm ? 6 : 12 + Math.min(20, ((speed ?? 0) / 12) * 20);
  return (
    <svg
      className="dial"
      viewBox="0 0 64 64"
      role="img"
      aria-label={`wind bearing ${Math.round(to)} degrees${
        typeof speed === "number" ? `, ${speed.toFixed(2)} metres per second` : ""
      }`}
    >
      <circle cx="32" cy="32" r="29" className="dial-ring" />
      {[0, 90, 180, 270].map((a) => {
        const r = (a * Math.PI) / 180;
        return (
          <line
            key={a}
            x1={(32 + Math.sin(r) * 24).toFixed(1)}
            y1={(32 - Math.cos(r) * 24).toFixed(1)}
            x2={(32 + Math.sin(r) * 28).toFixed(1)}
            y2={(32 - Math.cos(r) * 28).toFixed(1)}
            className="dial-tick"
          />
        );
      })}
      <text x="32" y="11" className="dial-n">
        N
      </text>
      <g transform={`rotate(${to.toFixed(1)} 32 32)`}>
        <path
          d={`M32 ${(32 - len).toFixed(1)} L${(32 + 5).toFixed(1)} 34 L32 ${(
            32 -
            len +
            9
          ).toFixed(1)} L${(32 - 5).toFixed(1)} 34 Z`}
          className={calm ? "dial-arrow calm" : "dial-arrow"}
        />
      </g>
      <circle cx="32" cy="32" r="2.5" className="dial-hub" />
    </svg>
  );
}

function Band({
  label,
  value,
  text,
  note,
  invert,
}: {
  label: string;
  value: number | null;
  text: string | undefined;
  note: string;
  invert?: boolean;
}) {
  const have = typeof value === "number" && Number.isFinite(value);
  const pct = have ? Math.max(0, Math.min(1, invert ? 1 - value : value)) * 100 : 0;
  return (
    <div className="band">
      <div className="band-h">
        <span>{label}</span>
        <b>{have ? (text ?? "Unavailable") : "Unavailable"}</b>
      </div>
      <div className="band-t">
        <div className="band-f" style={{ width: `${pct.toFixed(1)}%` }} />
      </div>
      <div className="band-n">{have ? note : "Unavailable"}</div>
    </div>
  );
}

export default function DetailPanel({
  open,
  detection,
  incident,
  environment,
  envPhase,
  onVerify,
  onRefreshEnv,
  onClose,
}: Props) {
  const [ai, setAi] = useState<AiResult | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiErr, setAiErr] = useState<string | null>(null);

  const runVerify = async () => {
    if (!detection) return;
    setAiBusy(true);
    setAiErr(null);
    try {
      setAi(await onVerify(detection.detection_id));
    } catch (e) {
      setAiErr(e instanceof Error ? e.message : String(e));
    } finally {
      setAiBusy(false);
    }
  };

  const env = environment;
  const envOk = env?.status === "AVAILABLE";
  const lvl = String(incident?.priority?.level ?? "").toLowerCase();
  const score = typeof incident?.priority?.score === "number" ? incident.priority.score : null;

  return (
    <aside className={`right card${open ? " open" : ""}`}>
      <button className="close" onClick={onClose} aria-label="Close detail panel">
        ✕
      </button>
      {!detection && !incident && (
        <p className="empty">
          Pick a detection on the map, an incident from the list, or press{" "}
          <kbd>Ctrl</kbd>+<kbd>K</kbd> to jump to a wilaya.
        </p>
      )}

      {incident && (
        <div className="card-b">
          <div className="inc-top">
            <span className={`prio-badge ${lvl}`}>{incident.priority?.level ?? "Unavailable"}</span>
            <span className="score" title="rule-based priority score">
              <i style={{ width: `${score === null ? 0 : Math.min(100, score * 100)}%` }} />
              <b>{score === null ? "Unavailable" : score.toFixed(4)}</b>
            </span>
          </div>
          <div className="inc-title">
            <b>{incident.detection_count} detections</b>
            {incident.wilayas?.length ? <span className="wilas">{incident.wilayas.join(", ")}</span> : null}
          </div>
          <div className="inc-meta">
            <span>{stamp(incident.last_acq)}</span>
            <span>FRP {incident.max_frp} MW</span>
          </div>
          <div className="inc-meta">
            <span>
              persistence{" "}
              {incident.persistence_hours != null
                ? `${Number(incident.persistence_hours).toFixed(1)} h`
                : "Unavailable"}
            </span>
            <span>{incident.satellites?.length ? incident.satellites.join(" · ") : "Unavailable"}</span>
          </div>
          <div className="kv">
            <em>Grouping status</em>
            <span>{incident.status}</span>
          </div>

          <h3>Priority — rule-based</h3>
          {incident.priority?.factors.map((f) => {
            const c = (f.normalized ?? 0) * f.weight;
            return (
              <div className="factor" key={f.name}>
                <div className="row">
                  <span>{f.name}</span>
                  <span>
                    w {f.weight} → {c.toFixed(4)}
                  </span>
                </div>
                <div className="bar">
                  <i style={{ width: `${Math.min(100, Math.max(0, c * 100))}%` }} />
                </div>
                <div className="ev">{f.evidence}</div>
              </div>
            );
          })}
          {incident.priority?.unavailable_factors?.length ? (
            <p className="note">No dataset, contributes nothing: {incident.priority.unavailable_factors.join(", ")}</p>
          ) : null}
          <p className="note">{incident.priority?.methodology}</p>
          <p className="note strong">
            priority-v1 is deterministic and rule-based. It is not the AI verifier and
            never uses model output.
          </p>
        </div>
      )}

      {incident?.verification && (
        <div className="card-b">
          <h3>Verification state</h3>
          <div className="kv">
            <em>Status</em>
            <span>{incident.verification.status}</span>
          </div>
          <div className="kv">
            <em>Evaluated</em>
            <span>{incident.verification.evaluated ? "yes" : "no"}</span>
          </div>
          <p className="note">{incident.verification.message}</p>
        </div>
      )}

      {detection && (
        <div className="card-b">
          <h3>Detection</h3>
          <div className="kv">
            <em>Wilaya</em>
            <span>{detection.wilaya_name ?? "Unavailable"}</span>
          </div>
          <div className="kv">
            <em>Coordinates</em>
            <span>
              {detection.lat.toFixed(5)}, {detection.lon.toFixed(5)}
            </span>
          </div>
          <div className="kv">
            <em>Acquired</em>
            <span>{stamp(detection.acq_datetime)}</span>
          </div>
          <div className="kv">
            <em>Satellite</em>
            <span>
              {detection.satellite} · {detection.instrument || "Unavailable"}
            </span>
          </div>
          <div className="kv">
            <em>FRP</em>
            <span>{n(detection.frp, 2, " MW")}</span>
          </div>
          <div className="kv">
            <em>Brightness Ti4</em>
            <span>{n(detection.bright_ti4, 2, " K")}</span>
          </div>
          <div className="kv">
            <em>FIRMS confidence</em>
            <span>{detection.confidence == null ? "Unavailable" : detection.confidence_raw ?? String(detection.confidence)}</span>
          </div>
          <div className="kv">
            <em>State</em>
            <span className="ok">{detection.state}</span>
          </div>

          <button className="mapbtn wide" onClick={runVerify} disabled={aiBusy}>
            {aiBusy ? "Verifying…" : "Run AI verification"}
          </button>

          {ai && (
            <div className="sub">
              <div className="kv">
                <em>Result</em>
                <span>{ai.prediction ?? "Unavailable"}</span>
              </div>
              <div className="kv">
                <em>Probability</em>
                <span>{ai.probability == null ? "Unavailable" : ai.probability.toFixed(6)}</span>
              </div>
              <div className="kv">
                <em>Model</em>
                <span>{ai.model ?? "Unavailable"}</span>
              </div>
              <div className="kv">
                <em>Threshold</em>
                <span>{ai.threshold ?? "Unavailable"}</span>
              </div>
              <div className="kv">
                <em>Calibrated</em>
                <span>{ai.calibrated === null ? "Unavailable" : ai.calibrated ? "yes" : "no"}</span>
              </div>
              {ai.calibrated === false && (
                <p className="note warn">
                  Not calibrated — this is a model score, not a literal probability of fire.
                </p>
              )}
              <p className="note strong">{ai.scope ?? ""}</p>
              {ai.message && <p className="note">{ai.message}</p>}
            </div>
          )}
          {aiErr && <p className="note warn">{aiErr}</p>}
        </div>
      )}

      {envPhase !== "idle" && (
        <div className="card-b">
          <h3>Environment at incident</h3>
          {envPhase === "loading" && <p className="note">Loading environmental context…</p>}

          {envPhase !== "loading" && !envOk && (
            <>
              <p className="note warn">Environmental context unavailable.</p>
              {env?.reason && <p className="note">{env.reason}</p>}
            </>
          )}

          {envOk && env && (
            <>
              <div className="env-top">
                <WindDial deg={env.wind_direction_10m_deg} speed={env.wind_speed_10m_ms} />
                <div className="env-metrics">
                  <div className="kv">
                    <em>Wind</em>
                    <span>{n(env.wind_speed_10m_ms, 2, " m/s")}</span>
                  </div>
                  <div className="kv">
                    <em>Gusts</em>
                    <span>{n(env.wind_gusts_10m_ms, 2, " m/s")}</span>
                  </div>
                  <div className="kv">
                    <em>Temp</em>
                    <span>{n(env.temperature_2m_c, 1, " °C")}</span>
                  </div>
                  <div className="kv">
                    <em>Humidity</em>
                    <span>{n(env.relative_humidity_2m_pct, 0, "%")}</span>
                  </div>
                  <div className="kv">
                    <em>Soil 0–1</em>
                    <span>{n(env.soil_moisture_0_1_m3_m3, 3)}</span>
                  </div>
                  <div className="kv">
                    <em>Soil 3–9</em>
                    <span>{n(env.soil_moisture_3_9_m3_m3, 3)}</span>
                  </div>
                  <div className="kv">
                    <em>Soil temp</em>
                    <span>{n(env.soil_temperature_0_7_c, 1, " °C")}</span>
                  </div>
                  <div className="kv">
                    <em>Elevation</em>
                    <span>{n(env.elevation_m, 0, " m")}</span>
                  </div>
                </div>
              </div>
              <p className="note">
                The arrow points the way the wind blows <em>to</em>; Open-Meteo reports
                bearing from. Not a fire-spread model.
              </p>
              {env.precision?.centroid_spread_m != null && (
                <p className="note">
                  Cluster spread {Math.round(env.precision.centroid_spread_m).toLocaleString("en-GB")} m.
                  {env.precision.note}
                </p>
              )}
              <Band
                label="Humidity"
                value={
                  typeof env.relative_humidity_2m_pct === "number"
                    ? env.relative_humidity_2m_pct / 100
                    : null
                }
                text={`${env.relative_humidity_2m_pct?.toFixed(0)}%`}
                note="Moist ← · → Drying"
                invert
              />
              <Band
                label="Soil moisture"
                value={
                  typeof env.soil_moisture_0_1_m3_m3 === "number"
                    ? env.soil_moisture_0_1_m3_m3 / 0.5
                    : null
                }
                text={env.soil_moisture_0_1_m3_m3?.toFixed(3)}
                note="Deep ← · → Shallow fuel"
                invert
              />
              <Band
                label="Wind"
                value={
                  typeof env.wind_speed_10m_ms === "number" ? env.wind_speed_10m_ms / 15 : null
                }
                text={`${env.wind_speed_10m_ms?.toFixed(2)} m/s`}
                note="Calm ← · → Strong"
              />
              <p className="note strong">
                Bands describe measured conditions only. No fire-risk score, no verdict.
              </p>
              <p className="note">
                {env.source} · incident centroid · observed {stamp(env.observed_at)}
              </p>
            </>
          )}

          <button className="mapbtn wide" onClick={onRefreshEnv} disabled={envPhase === "loading"}>
            Refresh environment
          </button>
        </div>
      )}
    </aside>
  );
}