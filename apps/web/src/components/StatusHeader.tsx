import { Flame } from "lucide-react";
import type { SystemStatus } from "../types";
import type { Dict } from "../i18n";

interface Props {
  status: SystemStatus | null;
  dict: Dict;
  onToggleLang: () => void;
}

/**
 * AI verifier label, derived strictly from GET /system/status.
 *
 * `ai` and `model` are whatever the backend reported. No status is inferred,
 * no model name is invented, and "unavailable" is never softened into an
 * implication that verification is running. Satellite detections being LIVE
 * is a separate fact and is shown separately.
 */
export function describeAi(status: SystemStatus | null, dict: Dict): string {
  if (!status) return dict.status_unknown;
  if (status.ai === "UNAVAILABLE") return dict.ai_unavailable;
  return status.model ? `${status.ai} (${status.model})` : status.ai;
}

/** FIRMS connectivity label, straight from the backend. */
export function describeFirms(status: SystemStatus | null, dict: Dict): string {
  return status?.firms ?? dict.status_unknown;
}

export default function StatusHeader({ status, dict, onToggleLang }: Props) {
  const state = status?.data_state ?? "UNAVAILABLE";
  const stateLabel =
    state === "LIVE" ? dict.live
    : state === "HISTORICAL" ? dict.historical
    : state === "STALE" ? dict.stale
    : dict.unavailable;

  return (
    <header className="header">
      <div className="brand">
        <Flame size={22} className="brand-icon" />
        <div>
          <h1>{dict.title}</h1>
          <p className="subtitle">{dict.subtitle}</p>
          <p className="fine">{dict.independent}</p>
        </div>
      </div>

      <div className="badges">
        {/* data_state is the backend's own verdict, never computed here. */}
        <span className={`chip chip-${state.toLowerCase()}`}>{stateLabel}</span>
        <span className="chip chip-ai">{dict.firms}: {describeFirms(status, dict)}</span>
        <span className="chip chip-ai">
          {dict.ai_status}: {describeAi(status, dict)}
        </span>
        <button className="lang-btn" onClick={onToggleLang}>
          {dict.lang}
        </button>
      </div>
    </header>
  );
}