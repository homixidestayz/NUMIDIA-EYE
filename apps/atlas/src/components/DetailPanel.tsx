import { useState } from "react";
import type { AiResult, Detection, Environment, Incident } from "../types";
import { useI18n } from "../i18n";
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

const stampBase = (iso: string | null | undefined, u: string) => {
  if (!iso) return u;
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? u
    : d.toLocaleString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
};

const nBase = (v: number | null | undefined, digits: number, unit: string, u: string) =>
  typeof v === "number" && Number.isFinite(v) ? `${v.toFixed(digits)}${unit}` : u;

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
  unavailable,
}: {
  label: string;
  value: number | null;
  text: string | undefined;
  note: string;
  invert?: boolean;
  unavailable: string;
}) {
  const have = typeof value === "number" && Number.isFinite(value);
  const pct = have ? Math.max(0, Math.min(1, invert ? 1 - value : value)) * 100 : 0;
  return (
    <div className="band">
      <div className="band-h">
        <span>{label}</span>
        <b>{have ? (text ?? unavailable) : unavailable}</b>
      </div>
      <div className="band-t">
        <div className="band-f" style={{ width: `${pct.toFixed(1)}%` }} />
      </div>
      <div className="band-n">{have ? note : unavailable}</div>
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
  const { t, dir } = useI18n();
  const stamp = (iso: string | null | undefined) => stampBase(iso, t.unavailable);
  const n = (v: number | null | undefined, digits: number, unit = "") =>
    nBase(v, digits, unit, t.unavailable);
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
    <aside dir={dir} className={`right card${open ? " open" : ""}`}>
      <button className="close" onClick={onClose} aria-label={t.closePanel}>
        ✕
      </button>
      {!detection && !incident && (
        <p className="empty">
          {t.pickPrefix} <kbd>Ctrl</kbd>+<kbd>K</kbd> {t.pickSuffix}
        </p>
      )}

      {incident && (
        <div className="card-b">
          <div className="inc-top">
            <span className={`prio-badge ${lvl}`}>{incident.priority?.level ?? t.unavailable}</span>
            <span className="score" title={t.priorityTitle}>
              <i style={{ width: `${score === null ? 0 : Math.min(100, score * 100)}%` }} />
              <b>{score === null ? t.unavailable : score.toFixed(4)}</b>
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
                : t.unavailable}
            </span>
            <span>
              {incident.satellites?.length
                ? incident.satellites.join(" · ")
                : t.unavailable}
            </span>
          </div>
          <div className="kv">
            <em>{t.groupingStatus}</em>
            <span lang="en" dir="ltr">{incident.status}</span>
          </div>

          <h3>{t.priorityRule}</h3>
          {incident.priority?.factors.map((f) => {
            const c = (f.normalized ?? 0) * f.weight;
            return (
              <div className="factor" key={f.name}>
                <div className="row">
                  {/* factor names and evidence are pipeline data, English by design */}
                  <span lang="en" dir="ltr">{f.name}</span>
                  <span>
                    w {f.weight} → {c.toFixed(4)}
                  </span>
                </div>
                <div className="bar">
                  <i style={{ width: `${Math.min(100, Math.max(0, c * 100))}%` }} />
                </div>
                <div className="ev" lang="en" dir="ltr">{f.evidence}</div>
              </div>
            );
          })}
          {incident.priority?.unavailable_factors?.length ? (
            <p className="note">
              {t.noDataset}{" "}
              <span lang="en" dir="ltr">
                {incident.priority.unavailable_factors.join(", ")}
              </span>
            </p>
          ) : null}
          <p className="note" lang="en" dir="ltr">{incident.priority?.methodology}</p>
          <p className="note strong">{t.priorityNote}</p>
        </div>
      )}

      {incident?.verification && (
        <div className="card-b">
          <h3>{t.verification}</h3>
          <div className="kv">
            <em>{t.status}</em>
            <span lang="en" dir="ltr">{incident.verification.status}</span>
          </div>
          <div className="kv">
            <em>{t.evaluated}</em>
            <span>{incident.verification.evaluated ? t.yes : t.no}</span>
          </div>
          {/* the scope statement is the project's own honesty guarantee — it is
              English pipeline text and must not be paraphrased */}
          <p className="note" lang="en" dir="ltr">{incident.verification.message}</p>
        </div>
      )}

      {detection && (
        <div className="card-b">
          <h3>{t.detection}</h3>
          <div className="kv">
            <em>{t.wilaya}</em>
            <span>{detection.wilaya_name ?? t.unavailable}</span>
          </div>
          <div className="kv">
            <em>{t.coordinates}</em>
            <span dir="ltr">
              {detection.lat.toFixed(5)}, {detection.lon.toFixed(5)}
            </span>
          </div>
          <div className="kv">
            <em>{t.acquired}</em>
            <span>{stamp(detection.acq_datetime)}</span>
          </div>
          <div className="kv">
            <em>{t.satellite}</em>
            <span>
              {detection.satellite || t.unavailable} ·{" "}
              {detection.instrument || t.unavailable}
            </span>
          </div>
          <div className="kv">
            <em>FRP</em>
            <span>{n(detection.frp, 2, " MW")}</span>
          </div>
          <div className="kv">
            <em>{t.brightness}</em>
            <span>{n(detection.bright_ti4, 2, " K")}</span>
          </div>
          <div className="kv">
            <em>{t.firmsConfidence}</em>
            <span>
              {detection.confidence == null
                ? t.unavailable
                : (detection.confidence_raw ?? String(detection.confidence))}
            </span>
          </div>
          <div className="kv">
            <em>{t.state}</em>
            <span className="ok" lang="en" dir="ltr">{detection.state}</span>
          </div>

          <button className="mapbtn wide" onClick={runVerify} disabled={aiBusy}>
            {aiBusy ? t.verifying : t.runAi}
          </button>

          {ai && (
            <div className="sub">
              <div className="kv">
                <em>{t.result}</em>
                <span lang="en" dir="ltr">{ai.prediction ?? t.unavailable}</span>
              </div>
              <div className="kv">
                <em>{t.probability}</em>
                <span>{ai.probability == null ? t.unavailable : ai.probability.toFixed(6)}</span>
              </div>
              <div className="kv">
                <em>{t.model}</em>
                <span lang="en" dir="ltr">{ai.model ?? t.unavailable}</span>
              </div>
              <div className="kv">
                <em>{t.threshold}</em>
                <span>{ai.threshold ?? t.unavailable}</span>
              </div>
              <div className="kv">
                <em>{t.calibrated}</em>
                <span>
                  {ai.calibrated === null
                    ? t.unavailable
                    : ai.calibrated
                      ? t.yes
                      : t.no}
                </span>
              </div>
              {ai.calibrated === false && (
                <p className="note warn">{t.notCalibrated}</p>
              )}
              <p className="note strong" lang="en" dir="ltr">{ai.scope ?? ""}</p>
              {ai.message && (
                <p className="note" lang="en" dir="ltr">{ai.message}</p>
              )}
            </div>
          )}
          {aiErr && <p className="note warn" lang="en" dir="ltr">{aiErr}</p>}
        </div>
      )}

      {envPhase !== "idle" && (
        <div className="card-b">
          <h3>{t.envTitle}</h3>
          {envPhase === "loading" && <p className="note">{t.envLoading}</p>}

          {envPhase !== "loading" && !envOk && (
            <>
              <p className="note warn">{t.envUnavailable}</p>
              {env?.reason && <p className="note" lang="en" dir="ltr">{env.reason}</p>}
            </>
          )}

          {envOk && env && (
            <>
              <div className="env-top">
                <WindDial deg={env.wind_direction_10m_deg} speed={env.wind_speed_10m_ms} />
                <div className="env-metrics">
                  <div className="kv">
                    <em>{t.wind}</em>
                    <span>{n(env.wind_speed_10m_ms, 2, " m/s")}</span>
                  </div>
                  <div className="kv">
                    <em>{t.gusts}</em>
                    <span>{n(env.wind_gusts_10m_ms, 2, " m/s")}</span>
                  </div>
                  <div className="kv">
                    <em>{t.temp}</em>
                    <span>{n(env.temperature_2m_c, 1, " °C")}</span>
                  </div>
                  <div className="kv">
                    <em>{t.humidity}</em>
                    <span>{n(env.relative_humidity_2m_pct, 0, "%")}</span>
                  </div>
                  <div className="kv">
                    <em>{t.soil01}</em>
                    <span>{n(env.soil_moisture_0_1_m3_m3, 3)}</span>
                  </div>
                  <div className="kv">
                    <em>{t.soil39}</em>
                    <span>{n(env.soil_moisture_3_9_m3_m3, 3)}</span>
                  </div>
                  <div className="kv">
                    <em>{t.soilTemp}</em>
                    <span>{n(env.soil_temperature_0_7_c, 1, " °C")}</span>
                  </div>
                  <div className="kv">
                    <em>{t.elevation}</em>
                    <span>{n(env.elevation_m, 0, " m")}</span>
                  </div>
                </div>
              </div>
              <p className="note">
                {t.windCapPre} <em>{t.windTo}</em>
                {t.windCapPost}
              </p>
              {env.precision?.centroid_spread_m != null && (
                <p className="note">
                  {t.clusterSpread} {Math.round(env.precision.centroid_spread_m).toLocaleString("en-GB")} m.{" "}
                  <span lang="en" dir="ltr">{env.precision.note}</span>
                </p>
              )}
              <Band
                unavailable={t.unavailable}
                label={t.humidity}
                value={
                  typeof env.relative_humidity_2m_pct === "number"
                    ? env.relative_humidity_2m_pct / 100
                    : null
                }
                text={`${env.relative_humidity_2m_pct?.toFixed(0)}%`}
                note={t.noteHumidity}
                invert
              />
              <Band
                unavailable={t.unavailable}
                label={t.soilMoisture}
                value={
                  typeof env.soil_moisture_0_1_m3_m3 === "number"
                    ? env.soil_moisture_0_1_m3_m3 / 0.5
                    : null
                }
                text={env.soil_moisture_0_1_m3_m3?.toFixed(3)}
                note={t.noteSoil}
                invert
              />
              <Band
                unavailable={t.unavailable}
                label={t.wind}
                value={
                  typeof env.wind_speed_10m_ms === "number" ? env.wind_speed_10m_ms / 15 : null
                }
                text={`${env.wind_speed_10m_ms?.toFixed(2)} m/s`}
                note={t.noteWind}
              />
              <p className="note strong">{t.bandsOnly}</p>
              <p className="note">
                <span lang="en" dir="ltr">{env.source}</span> · {t.envCentroid} ·{" "}
                {t.envObserved} {stamp(env.observed_at)}
              </p>
            </>
          )}

          <button className="mapbtn wide" onClick={onRefreshEnv} disabled={envPhase === "loading"}>
            {t.refreshEnv}
          </button>
        </div>
      )}
    </aside>
  );
}