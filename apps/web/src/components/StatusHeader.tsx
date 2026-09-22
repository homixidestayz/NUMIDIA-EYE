import { Flame } from "lucide-react";
import type { Lang, SystemStatus } from "../types";
import type { Dict } from "../i18n";

interface Props {
  status: SystemStatus | null;
  lang: Lang;
  dict: Dict;
  onToggleLang: () => void;
}

export default function StatusHeader({ status, lang, dict, onToggleLang }: Props) {
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
        <span className={`chip chip-${state.toLowerCase()}`}>
          {stateLabel}
        </span>
        <span className="chip chip-ai" title={dict.ai_unavailable}>
          {dict.ai_status}: {dict.ai_unavailable}
        </span>
        <button className="lang-btn" onClick={onToggleLang}>
          {dict.lang}
        </button>
      </div>
    </header>
  );
}