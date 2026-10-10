import type { Incident, LayerState } from "../types";

interface Props {
  layers: LayerState;
  onToggleLayer: (key: keyof LayerState) => void;
  incidents: Incident[];
  selectedIncidentId: string | null;
  onSelectIncident: (id: string) => void;
  loading: boolean;
  open: boolean;
}

const LAYERS: { key: keyof LayerState; label: string; color: string }[] = [
  { key: "wilayas", label: "Wilaya boundaries", color: "#1f7a58" },
  { key: "detections", label: "Fire detections", color: "#e2571f" },
  { key: "labels", label: "Wilaya labels", color: "#8fa79b" },
];

const stamp = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "Unavailable"
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
  return (
    <aside className={`left card${open ? " open" : ""}`}>
      <div className="scroll">
        <section className="group g-fires">
          <h2 className="group-h">Layers</h2>
          <div className="layer-list">
            {LAYERS.map((l) => (
              <button
                key={l.key}
                className={`layer ${layers[l.key] ? "on" : ""}`}
                onClick={() => onToggleLayer(l.key)}
                aria-pressed={layers[l.key]}
              >
                <span className="box">{layers[l.key] ? "✓" : ""}</span>
                <span className="lbl">{l.label}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="group g-prio">
          <h2 className="group-h">Incidents &amp; priority</h2>
          <p className="lede">
            Rule-based priority over grouped FIRMS detections. Not confirmed wildfires.
          </p>

          <div>
        {loading ? (
          /* An empty list here would read as "no incidents", which is a claim
             about Algeria rather than about our request. */
          <p className="note">Grouping incidents… this takes a few seconds.</p>
        ) : incidents.length === 0 ? (
          <p className="note">
            No incidents grouped from the stored detections. The pipeline is up but
            nothing is stored yet — that is different from an absence of fires.
          </p>
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
                      <span className={`badge ${level}`}>{p?.level ?? "Unavailable"}</span>
                      <span className="score" title="rule-based priority score">
                        <i style={{ width: `${pct}%` }} />
                        <b>{score === null ? "Unavailable" : score.toFixed(4)}</b>
                      </span>
                    </div>
                    <div className="inc-title">
                      <b>{inc.detection_count} detections</b>
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