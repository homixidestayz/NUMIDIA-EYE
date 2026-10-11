import type { SystemStatus } from "../types";
import { useI18n } from "../i18n";

interface Props {
  status: SystemStatus | null;
  loading: boolean;
  liveCount: number;
  total: number;
  onSearch: () => void;
  onToggleLeft: () => void;
  onToggleRight: () => void;
  leftOpen: boolean;
  rightOpen: boolean;
}

/* firms states are CONNECTED / STALE / DEGRADED / NOT_CONFIGURED / STARTING.
   Anything unrecognised reads as unknown rather than assumed good. */
function firmsTone(v: string | undefined): "ok" | "warn" | "bad" | "" {
  if (v === "CONNECTED") return "ok";
  if (v === "STALE" || v === "DEGRADED" || v === "STARTING") return "warn";
  if (v === "NOT_CONFIGURED") return "bad";
  return "";
}

export default function Header({
  status,
  loading,
  liveCount,
  total,
  onSearch,
  onToggleLeft,
  onToggleRight,
  leftOpen,
  rightOpen,
}: Props) {
  const { t, lang, dir, toggle } = useI18n();
  const s = status;
  /* "Unavailable" is a claim about the world: the upstream was asked and
     declined. While the request is in flight the honest word is "Loading". */
  const pending = loading && !s;
  const val = (v: string | undefined) => (pending ? t.loading : (v ?? t.unavailable));

  return (
    <header className="topbar panel" dir={dir}>
      <div className="brand">
        <EyeMark />
        <div className="brandtext">
          <h1>NUMIDIA EYE</h1>
          <p>{t.tagline}</p>
        </div>
      </div>

      <button className="searchbtn" onClick={onSearch} aria-label={t.openSearch}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <line x1="21" y1="21" x2="16.5" y2="16.5" />
        </svg>
        <span>{pending ? t.loading : t.jump}</span>
        <kbd>Ctrl K</kbd>
      </button>

      <div className="chips" role="status" aria-live="polite">
        <span className={`chip ${pending ? "" : firmsTone(s?.firms)}`}>
          <i className="dot" />
          FIRMS <b>{val(s?.firms)}</b>
        </span>
        <span className={`chip ${pending ? "" : s?.ai === "READY" ? "ok" : "bad"}`}>
          <i className="dot" />
          AI <b>{s?.ai === "READY" && s.model ? s.model : val(s?.ai)}</b>
        </span>
        <span className="chip">
          <b>
            {pending
              ? t.loading
              : `${liveCount.toLocaleString("en-GB")} ${t.liveOf} / ${total.toLocaleString("en-GB")}`}
          </b>
        </span>
      </div>

      <button
        className="btn lang-btn"
        onClick={toggle}
        aria-label={t.langLabel}
        lang={lang === "en" ? "ar" : "en"}
      >
        {t.langName}
      </button>
      <button className="btn drawer-toggle" aria-pressed={leftOpen} onClick={onToggleLeft}>
        {t.layers}
      </button>
      <button className="btn drawer-toggle" aria-pressed={rightOpen} onClick={onToggleRight}>
        {t.detail}
      </button>
    </header>
  );
}

/* The mark: an eye whose pupil is the Tifinagh letter yaz, the Amazigh symbol.
   NUMIDIA is the ancient Amazigh kingdom, so this is an identity rather than a
   decoration. The iris uses the fire colour, not the UI green. */
function EyeMark() {
  return (
    <svg className="mark" width="30" height="30" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <path
        d="M2 16C6 9.5 10.5 6.5 16 6.5S26 9.5 30 16c-4 6.5-8.5 9.5-14 9.5S6 22.5 2 16Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <circle cx="16" cy="16" r="6.2" fill="var(--fire)" />
      {/* yaz ⵣ: two uprights joined by a horizontal bar. */}
      <path
        d="M12.5 12.8v6.4M19.5 12.8v6.4M12.5 16h7"
        stroke="#1a0d05"
        strokeWidth="1.7"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}