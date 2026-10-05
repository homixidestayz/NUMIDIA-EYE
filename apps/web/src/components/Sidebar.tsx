import { Brain, ShieldAlert } from "lucide-react";
import type { AiResult, Detection, SystemStatus } from "../types";
import type { Dict } from "../i18n";
import { fmtDate } from "../api";
import { describeAi, describeFirms } from "./StatusHeader";
import AiVerification from "./AiVerification";
import type { DetailPhase } from "../App";

interface Props {
  status: SystemStatus | null;
  detections: Detection[];
  lang: "en" | "ar";
  dict: Dict;
  detail: Detection | null;
  detailPhase: DetailPhase;
  detailStale: boolean;
  /** Mirrors the real /ai result upward so the chain rail can reflect VERIFY. */
  onAiResult: (result: AiResult | null) => void;
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
  onAiResult,
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
          {/* UNDERSTAND: five labelled groups so a judge reads what/where/when/
              source/signal at a glance. Every value still comes straight from
              GET /detections/{id}; a null field shows "Unavailable", never a
              substituted zero or dash. */}
          <Field label={dict.what_label} hint={dict.detection_state}>
            <span className={detail.state === "LIVE" ? "live-tag" : ""}>
              {stateLabel(detail.state, dict)}
            </span>
          </Field>
          <Field label={dict.where_label} hint={dict.wilaya}>
            {wilayaText}
            <SubValue label={dict.latitude} value={numberOr(detail.lat, dict)} />
            <SubValue label={dict.longitude} value={numberOr(detail.lon, dict)} />
          </Field>
          <Field label={dict.when_label} hint={dict.acquired}>
            {fmtDate(detail.acq_datetime)}
          </Field>
          <Field label={dict.source_label} hint={dict.source}>
            {text(detail.source, dict)}
            <SubValue label={dict.satellite} value={text(detail.satellite, dict)} />
          </Field>
          <Field label={dict.signal_label} hint={dict.frp}>
            {frpText}
            <SubValue label={dict.confidence} value={confidenceText} />
            <SubValue
              label={dict.brightness_ti4}
              value={numberOr(detail.bright_ti4, dict)}
            />
            <SubValue
              label={dict.brightness_ti5}
              value={numberOr(detail.bright_ti5, dict)}
            />
          </Field>
          <div className="row small">
            <span>{dict.no_ai}</span>
          </div>
          {detailStale && <div className="row small"><span>{dict.detail_unavailable}</span></div>}
          <div className="popup-id">{detail.detection_id}</div>
        </div>
      )}
      {/* The AI panel is deliberately OUTSIDE .detail-card: that card renders only
          the detection record as returned by GET /detections/{id}. Verification is a
          separate, explicitly-triggered model call and must not be mistaken for a
          field of the detection. */}
      {detail && detailPhase === "ready" && (
        <AiVerification
          detectionId={detail.detection_id}
          dict={dict}
          onResult={onAiResult}
        />
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

/**
 * One labelled group of real detection fields. `label` is the UNDERSTAND
 * question (what / where / when / source / signal); `hint` names the primary
 * field inside it. Children are the real values.
 */
function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <div className="field">
      <div className="field-head">
        <span className="field-label">{label}</span>
        <span className="field-hint">{hint}</span>
      </div>
      <div className="field-body">{children}</div>
    </div>
  );
}

/**
 * A secondary labelled value inside a Field. The label is its own element so
 * it stays independently readable and translatable.
 */
function SubValue({ label, value }: { label: string; value: string }) {
  return (
    <span className="coords">
      <em>{label}</em>
      <span>{value}</span>
    </span>
  );
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