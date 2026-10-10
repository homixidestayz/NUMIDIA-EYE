import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  RANGES,
  bucketByHour,
  formatLocalClock,
  formatLocalDay,
  humanSpan,
  inRange,
  rangeStartUtc,
  type HasTime,
  type RangeId,
} from "../timeline";

interface Props {
  detections: HasTime[];
  spanStart: Date;
  spanEnd: Date;
  range: RangeId;
  onRangeChange: (r: RangeId) => void;
  /** [start, end] currently shown, UTC. Parent filters the map from these. */
  window: [Date, Date] | null;
  onWindowChange: (w: [Date, Date] | null) => void;
  /** Bumped by the replay clock; the parent re-filters on it. */
  replayT: number | null;
  onReplayTick: (t: number | null) => void;
  loading: boolean;
  /** Detections actually on the map, which may be fewer than the time window
   *  holds once a wilaya filter applies. */
  onMapCount: number;
}

const HOUR = 3_600_000;

/* Everything is filtered client-side. The detections endpoint costs seconds, and
   a scrub control that awaits a round trip per drag would feel broken. */
export default function Timeline({
  detections,
  spanStart,
  spanEnd,
  range,
  onRangeChange,
  window: win,
  onWindowChange,
  replayT,
  onReplayTick,
  loading,
  onMapCount,
}: Props) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState<null | "start" | "end" | "pan">(null);
  const dragRef = useRef<{ mode: string; grabOffset: number } | null>(null);

  const spanMs = Math.max(HOUR, spanEnd.getTime() - spanStart.getTime());

  /* When nothing has been dragged, the displayed window must follow the active
     pill. Falling straight back to the full span made every pill read the same,
     so the control looked wired up and did nothing. */
  const derived = rangeStartUtc(range, new Date(), spanStart, spanEnd);
  const from = win ? win[0] : derived && derived > spanStart ? derived : spanStart;
  const to = win ? win[1] : spanEnd;

  const bars = useMemo(
    () => bucketByHour(detections, spanStart, spanEnd),
    [detections, spanStart, spanEnd],
  );
  const peak = useMemo(() => Math.max(1, ...bars.map((b) => b.count)), [bars]);

  const visible = useMemo(
    () => detections.filter((d) => inRange(d, from, to)),
    [detections, from, to],
  );

  const spanToX = useCallback(
    (t: number) => ((t - spanStart.getTime()) / spanMs) * 100,
    [spanStart, spanMs],
  );
  const xToSpan = useCallback(
    (pct: number) => spanStart.getTime() + (Math.max(0, Math.min(100, pct)) / 100) * spanMs,
    [spanStart, spanMs],
  );

  /* ── dragging ─────────────────────────────────────────────── */
  useEffect(() => {
    if (!dragging) return;
    const move = (ev: PointerEvent) => {
      const el = trackRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const pct = ((ev.clientX - r.left) / r.width) * 100;
      const t = xToSpan(pct);
      const mode = dragRef.current?.mode ?? dragging;
      if (mode === "start") {
        onWindowChange([new Date(Math.min(t, to.getTime())), to]);
      } else if (mode === "end") {
        onWindowChange([from, new Date(Math.max(t, from.getTime()))]);
      } else if (mode === "pan" && dragRef.current) {
        const delta = t - dragRef.current.grabOffset;
        const width = to.getTime() - from.getTime();
        let s = from.getTime() + delta;
        s = Math.max(spanStart.getTime(), Math.min(spanEnd.getTime() - width, s));
        onWindowChange([new Date(s), new Date(s + width)]);
      }
    };
    const up = () => {
      setDragging(null);
      dragRef.current = null;
      // A manual window is no longer the same thing as a preset, so clear it
      // rather than leaving a highlighted pill that no longer matches.
      if (dragging !== "pan") onRangeChange("all");
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, [dragging, from, to, xToSpan, onWindowChange, onRangeChange, spanStart, spanEnd]);

  const startDrag = (mode: "start" | "end" | "pan", ev: React.PointerEvent) => {
    ev.preventDefault();
    dragRef.current = { mode, grabOffset: xToSpan(0) };
    setDragging(mode);
  };

  /* ── replay ───────────────────────────────────────────────── */
  useEffect(() => {
    if (replayT === null) return;
    const id = window.setInterval(() => {
      const next = replayT + HOUR;
      if (next > to.getTime()) {
        onReplayTick(null);
        return;
      }
      onReplayTick(next);
    }, 420);
    return () => window.clearInterval(id);
  }, [replayT, to, onReplayTick]);

  /* Replay starts at the earliest detection we actually hold, not at local
     midnight — the loaded set usually begins hours after midnight, so starting
     there opened on an empty map. */
  const replayFrom = spanStart;
  const atReplayEnd = replayT !== null;

  const pick = (id: RangeId) => {
    onRangeChange(id);
    onReplayTick(null);
    onWindowChange(null);
  };

  /* A range wider than the data we hold cannot show anything extra, so the
     button would be a control that lies by doing nothing. Disable it and say
     how much history actually exists. */
  const loadedSpan = rangeStartUtc("all", spanEnd, spanStart, spanEnd) ?? spanStart;
  const heldFor = spanEnd.getTime() - loadedSpan.getTime();
  const unavailable = (id: RangeId) => {
    if (id === "all") return null;
    const s = rangeStartUtc(id, spanEnd, spanStart, spanEnd);
    if (!s) return null;
    if (s.getTime() >= spanStart.getTime()) return null;
    return `Only ${humanSpan(heldFor)} of detections are loaded, so this range would show the same points.`;
  };

  const leftPct = spanToX(from.getTime());
  const rightPct = spanToX(to.getTime());

  return (
    <section className="tl" aria-label="Timeline">
      <div className="tl-head">
        <div className="tl-ranges" role="group" aria-label="Time range">
          {RANGES.map((r) => {
            const why = unavailable(r.id);
            return (
              <button
                key={r.id}
                className="tl-pill"
                aria-pressed={range === r.id}
                disabled={Boolean(why)}
                title={why ?? r.title}
                onClick={() => pick(r.id)}
              >
                {r.label}
              </button>
            );
          })}
          <button
            className="tl-pill tl-play"
            aria-pressed={atReplayEnd}
            title="Replay recorded detections through time. This is playback of stored data, not a forecast."
            onClick={() =>
              onReplayTick(atReplayEnd ? null : replayFrom.getTime())
            }
          >
            {atReplayEnd ? "❚❚ Stop" : "▶ Replay"}
          </button>
        </div>

        <div className="tl-read">
          {/* Two counts, because they differ whenever a wilaya filter is on and
              showing one number contradicted the header. */}
          <b>
            {onMapCount.toLocaleString("en-GB")} on map
          </b>
          <span>
            {visible.length.toLocaleString("en-GB")} in range
          </span>
          <span>
            {loading ? "Loading…" : `${formatLocalDay(from)} ${formatLocalClock(from)} → ${formatLocalClock(to)}`}
          </span>
          <span className="tl-span">
            {humanSpan(to.getTime() - from.getTime())} shown ·{" "}
            {humanSpan(heldFor)} loaded
          </span>
        </div>
      </div>

      <div className="tl-track" ref={trackRef}>
        <div className="tl-bars" aria-hidden="true">
          {bars.map((b, i) => {
            const x = spanToX(b.t.getTime());
            const inWin = b.t.getTime() >= from.getTime() - HOUR && b.t.getTime() <= to.getTime();
            // Give each bar the width of its own bucket. Fixed 2px pins on a
            // 1500px track rendered as an almost empty strip.
            const w = bars.length ? 100 / bars.length : 1;
            return (
              <i
                key={b.t.toISOString()}
                className={inWin ? "in" : ""}
                title={`${b.count} detection${b.count === 1 ? "" : "s"} at ${formatLocalClock(b.t)}`}
                style={{
                  left: `${x}%`,
                  /* Cap the width so a dozen hourly buckets reads as a
                     histogram rather than a row of red blocks. */
                  width: `max(2px, min(14px, calc(${w}% - 1px)))`,
                  height: b.count === 0 ? "2px" : `${Math.max(8, (b.count / peak) * 100)}%`,
                  opacity: i % 2 ? 0.55 : 0.8,
                }}
              />
            );
          })}
        </div>

        <div
          className="tl-sel"
          style={{ left: `${leftPct}%`, width: `${Math.max(0.6, rightPct - leftPct)}%` }}
        >
          <button
            className="tl-handle l"
            aria-label="Move window start"
            onPointerDown={(e) => startDrag("start", e)}
          />
          <button
            className="tl-handle r"
            aria-label="Move window end"
            onPointerDown={(e) => startDrag("end", e)}
          />
        </div>
        <button
          className="tl-pan"
          aria-label="Pan the time window"
          onPointerDown={(e) => {
            const el = trackRef.current;
            if (!el) return;
            const r = el.getBoundingClientRect();
            const pct = ((e.clientX - r.left) / r.width) * 100;
            dragRef.current = { mode: "pan", grabOffset: xToSpan(pct) };
            setDragging("pan");
          }}
        />

        {replayT !== null && (
          <div className="tl-cursor" style={{ left: `${spanToX(replayT)}%` }} />
        )}
      </div>

      <p className="tl-foot">
        Replay steps through recorded detections. Times are Algeria local (UTC+1). Not a
        fire-spread model and not a forecast.
      </p>
    </section>
  );
}