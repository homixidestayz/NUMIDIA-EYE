import { Brain, ShieldAlert } from "lucide-react";
import type { Detection, SystemStatus } from "../types";
import type { Dict } from "../i18n";
import { fmtDate } from "../api";

interface Props {
  status: SystemStatus | null;
  detections: Detection[];
  lang: "en" | "ar";
  dict: Dict;
}

export default function Sidebar({ status, detections, lang, dict }: Props) {
  const live = detections.filter((d) => d.state === "LIVE").length;
  const lastFetch = status?.firms_last_fetch ? fmtDate(status.firms_last_fetch) : "—";
  const sources = new Set(detections.map((d) => d.source));
  const sats = new Set(detections.map((d) => d.satellite).filter(Boolean));

  return (
    <aside className="sidebar">
      <div className="stats">
        <Stat label={dict.detections} value={detections.length} />
        <Stat label={dict.live_now} value={live} accent={live > 0} />
        <Stat label={dict.sources} value={sources.size} />
        <Stat label={dict.satellites} value={sats.size} />
      </div>

      <div className="meta">
        <div><span>{dict.last_fetch}</span> <b>{lastFetch}</b></div>
        <div>
          <Brain size={14} /> {dict.ai_status}: <b>{dict.ai_unavailable}</b>
        </div>
        <div className="warn">
          <ShieldAlert size={14} /> {dict.alerts_prototype}
        </div>
        <div className="warn">{dict.incidents}</div>
      </div>

      <h2>{dict.list_title}</h2>
      <ul className="det-list">
        {detections.slice(0, 40).map((d) => (
          <li key={d.detection_id}>
            <span className={`dot ${d.state === "LIVE" ? "dot-live" : "dot-hist"}`} />
            <div className="row">
              <b>{d.frp.toFixed(1)} MW</b>
              <span>{d.satellite ?? "?"} · {fmtDate(d.acq_datetime)}</span>
            </div>
            <div className="row small">
              <span>{d.lat.toFixed(3)}, {d.lon.toFixed(3)}</span>
              <span className={d.state === "LIVE" ? "live-tag" : ""}>
                {d.state === "LIVE" ? dict.live : dict.historical}
              </span>
            </div>
          </li>
        ))}
        {detections.length === 0 && <li className="empty">—</li>}
      </ul>

      <p className="lang-hint">{lang === "ar" ? "العرض بالعربية (RTL)" : "English (LTR)"}</p>
    </aside>
  );
}

function Stat({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className="stat">
      <span className={accent ? "stat-value accent" : "stat-value"}>{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}