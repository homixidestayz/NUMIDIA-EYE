import type { SystemStatus } from "../types";

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
  const s = status;
  /* "Unavailable" is a claim about the world: the upstream was asked and
     declined. While the request is in flight the honest word is "Loading". */
  const pending = loading && !s;
  const val = (v: string | undefined) => (pending ? "Loading…" : (v ?? "Unavailable"));

  return (
    <header className="topbar">
      <div className="brand">
        <span className="mark" aria-hidden="true" />
        <div className="brandtext">
          <h1>NUMIDIA EYE</h1>
          <p>Wildfire intelligence for Algeria</p>
        </div>
      </div>

      <button className="searchbtn" onClick={onSearch} aria-label="Open wilaya search">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <line x1="21" y1="21" x2="16.5" y2="16.5" />
        </svg>
        <span>{pending ? "Loading…" : "Jump to a wilaya…"}</span>
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
              ? "Loading…"
              : `${liveCount.toLocaleString("en-GB")} live / ${total.toLocaleString("en-GB")}`}
          </b>
        </span>
      </div>

      <button className="btn drawer-toggle" aria-pressed={leftOpen} onClick={onToggleLeft}>
        Layers
      </button>
      <button className="btn drawer-toggle" aria-pressed={rightOpen} onClick={onToggleRight}>
        Detail
      </button>
    </header>
  );
}