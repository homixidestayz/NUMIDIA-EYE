import { Brain, ShieldAlert } from "lucide-react";
import type { Detection, SystemStatus } from "../types";
import type { Dict } from "../i18n";
import { fmtDate } from "../api";
import { describeAi, describeFirms } from "./StatusHeader";
import type { DetailPhase } from "../App";

interface Props {
  status: SystemStatus | null;
  detections: Detection[];
  lang: "en" | "ar";
  dict: Dict;
  detail: Detection | null;
  detailPhase: DetailPhase;
  detailStale: boolean;
  onSelect: (id: string) => void;
  onCloseDetail: () => void;
}

export default function Sidebar({
  status,
  detections,
  lang,
  dict,
  detail,
  detailPhase,
  detailStale,
  onSelect,
  onCloseDetail,
}: Props) {
  const live = detections.filter((d) => d.state === "LIVE").length;
  const lastFetch = status?.firms_last_fetch ? fmtDate(status.firms_last_fetch) : "—";
  const sources = new Set(detections.map((d) => d.source));
  const sats = new Set(detections.map((d) => d.satellite).filter(Boolean));

  // Detail-card values. Every one of these comes from GET /detections/{id}.
  // A null/absent field renders the localized "Unavailable" - never a zero,
  // a dash placeholder, or any other substitute value.
  const wilayaText =
    detail?.wilaya_name == null
      ? dict.field_unavailable
      : detail.wilaya_code == null
        ? detail.wilaya_name
        : `${detail.wilaya_name} (${detail.wilaya_code})`;
  const frpText =
    detail && typeof detail.frp === "number" ? `${detail.frp.toFixed(1)} MW` : dict.field_unavailable;
  const confidenceText =
    detail?.confidence == null
      ? dict.field_unavailable
      : `${Math.round(detail.confidence * 100)}%${
          detail.confidence_raw != null ? ` (${detail.confidence_raw})` : ""
        }`;

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
          <span>{dict.firms}</span> <b>{describeFirms(status, dict)}</b>
        </div>
        <div>
          <span>{dict.db_status}</span> <b>{status?.db ?? dict.status_unknown}</b>
        </div>
        <div>
          <Brain size={14} /> {dict.ai_status}: <b>{describeAi(status, dict)}</b>
        </div>
        <div className="warn">
          <ShieldAlert size={14} /> {dict.alerts_prototype}
        </div>
      </div>

      <h2>{dict.list_title}</h2>
      {detailPhase === "loading" && (
        <div className="detail-card">
          <div className="row small"><span>{dict.detail_loading}</span></div>
        </div>
      )}
      {detailPhase === "missing" && (
        <div className="detail-card">
          <div className="row small"><span>{dict.detail_not_found}</span></div>
        </div>
      )}
      {detailPhase === "error" && (
        <div className="detail-card">
          <div className="row small"><span>{dict.detail_error}</span></div>
        </div>
      )}
      {detail && (
        <div className="detail-card">
          <div className="row">
            <b>{dict.details}</b>
            <button className="lang-btn" onClick={onCloseDetail}>
              {dict.close}
            </button>
          </div>
          <div className="row">
            <span>{dict.detection_state}</span>
            <span className={detail.state === "LIVE" ? "live-tag" : ""}>
              {stateLabel(detail.state, dict)}
            </span>
          </div>
          <div className="row">
            <span>{dict.wilaya}</span>
            <span>{wilayaText}</span>
          </div>
          <div className="row small">
            <span>{dict.latitude}</span>
            <span>{numberOr(detail.lat, dict)}</span>
          </div>
          <div className="row small">
            <span>{dict.longitude}</span>
            <span>{numberOr(detail.lon, dict)}</span>
          </div>
          <div className="row">
            <span>{dict.source}</span>
            <span>{text(detail.source, dict)}</span>
          </div>
          <div className="row small">
            <span>{dict.satellite}</span>
            <span>{text(detail.satellite, dict)}</span>
          </div>
          <div className="row">
            <span>{dict.frp}</span>
            <span>{frpText}</span>
          </div>
          <div className="row small">
            <span>{dict.confidence}</span>
            <span>{confidenceText}</span>
          </div>
          <div className="row small">
            <span>{dict.brightness_ti4}</span>
            <span>{numberOr(detail.bright_ti4, dict)}</span>
          </div>
          <div className="row small">
            <span>{dict.brightness_ti5}</span>
            <span>{numberOr(detail.bright_ti5, dict)}</span>
          </div>
          <div className="row">
            <span>{dict.acquired}</span>
            <span>{fmtDate(detail.acq_datetime)}</span>
          </div>
          <div className="row small">
            <span>{dict.no_ai}</span>
          </div>
          {detailStale && <div className="row small"><span>{dict.detail_unavailable}</span></div>}
          <div className="popup-id">{detail.detection_id}</div>
        </div>
      )}
      <ul className="det-list">
        {detections.slice(0, 40).map((d) => (
          <li
            key={d.detection_id}
            onClick={() => onSelect(d.detection_id)}
            className={detail?.detection_id === d.detection_id ? "selected" : ""}
          >
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

/** Nullable string field: render the value, or the localized unavailable state. */
function text(value: string | null | undefined, dict: Dict): string {
  return value == null || value === "" ? dict.field_unavailable : value;
}

/** Nullable numeric field: 5 decimals, never a fabricated 0. */
function numberOr(value: number | null | undefined, dict: Dict): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(5)
    : dict.field_unavailable;
}

/** Render whatever the backend called the state, localizing the two known ones. */
function stateLabel(state: string, dict: Dict): string {
  if (state === "LIVE") return dict.live;
  if (state === "HISTORICAL") return dict.historical;
  return state;
}

function Stat({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className="stat">
      <span className={accent ? "stat-value accent" : "stat-value"}>{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}