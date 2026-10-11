import type { Incident, LayerState } from "../types";
import { useI18n } from "../i18n";

interface Props {
  layers: LayerState;
  onToggleLayer: (key: keyof LayerState) => void;
  incidents: Incident[];
  selectedIncidentId: string | null;
  onSelectIncident: (id: string) => void;
  loading: boolean;
  open: boolean;
}

const LAYERS: {
  key: keyof LayerState;
  label: "layerWilayas" | "layerDetections" | "layerLabels";
  color: string;
}[] = [
  { key: "wilayas", label: "layerWilayas", color: "#1f7a58" },
  { key: "detections", label: "layerDetections", color: "#e2571f" },
  { key: "labels", label: "layerLabels", color: "#8fa79b" },
];

const stampBase = (iso: string, u: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? u
    : d.toLocaleString("en-GB", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      });
};

export default function Sidebar({
  layers,
  onToggleLayer,
  incidents,
  selectedIncidentId,
  onSelectIncident,
  loading,
  open,
}: Props) {
  const { t, dir } = useI18n();
  const stamp = (iso: string) => stampBase(iso, t.unavailable);
  return (
    <aside dir={dir} className={`left card${open ? " open" : ""}`}>
      <div className="scroll">
        <section className="group g-fires">
          <h2 className="group-h">{t.layers}</h2>
          <div className="layer-list">
            {LAYERS.map((l) => (
              <button
                key={l.key}
                className={`layer ${layers[l.key] ? "on" : ""}`}
                onClick={() => onToggleLayer(l.key)}
                aria-pressed={layers[l.key]}
              >
                <span className="box">{layers[l.key] ? "✓" : ""}</span>
                <span className="lbl">{t[l.label]}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="group g-prio">
          <h2 className="group-h">{t.incidents}</h2>
          <p className="lede">{t.incidentsLede}</p>

          <div>
        {loading ? (
          /* An empty list here would read as "no incidents", which is a claim
             about Algeria rather than about our request. */
          <p className="note">{t.grouping}</p>
        ) : incidents.length === 0 ? (
          <p className="note">{t.noIncidents}</p>
        ) : (
          <ul className="inc-list">
            {incidents.map((inc) => {
              const p = inc.priority;
              const level = String(p?.level ?? "").toLowerCase();
              const score = typeof p?.score === "number" ? p.score : null;
              const pct = score === null ? 0 : Math.max(0, Math.min(100, score * 100));
              return (
                <li key={inc.id}>
                  <button
                    className={`inc ${level}${selectedIncidentId === inc.id ? " sel" : ""}`}
                    onClick={() => onSelectIncident(inc.id)}
                    aria-pressed={selectedIncidentId === inc.id}
                  >
                    <div className="inc-top">
                      <span className={`badge ${level}`}>{p?.level ?? t.unavailable}</span>
                      <span className="score" title={t.priorityTitle}>
                        <i style={{ width: `${pct}%` }} />
                        <b>{score === null ? t.unavailable : score.toFixed(4)}</b>
                      </span>
                    </div>
                    <div className="inc-title">
                      <b>{inc.detection_count} {t.detections}</b>
                      {inc.wilayas?.length ? (
                        <span className="wilas">{inc.wilayas.slice(0, 2).join(", ")}</span>
                      ) : null}
                    </div>
                    <div className="inc-meta">
                      <span>{stamp(inc.last_acq)}</span>
                      <span>FRP {inc.max_frp} MW</span>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
          </div>
        </section>
      </div>
    </aside>
  );
}