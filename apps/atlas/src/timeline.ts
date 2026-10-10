/* Timeline arithmetic.
 *
 *  "Today" here means the Algeria civil day (UTC+1, no DST), because that is
 *  what a viewer in Algiers means by it. Every stored timestamp is UTC, so the
 *  offset is applied explicitly rather than relying on the browser's locale —
 *  otherwise the TODAY pill silently rolls over at 23:00 UTC and shows a day
 *  that ended seven hours before the user last looked.
 */

export const ALGERIA_OFFSET_MINUTES = 60;

export type RangeId = "today" | "24h" | "7d" | "all";

export interface Range {
  id: RangeId;
  label: string;
  title: string;
}

/** TODAY first: it is the range a viewer opens on. */
export const RANGES: Range[] = [
  { id: "today", label: "Today", title: "00:00 Algeria time to now" },
  { id: "24h", label: "24H", title: "Rolling 24 hours to now" },
  { id: "7d", label: "7D", title: "Rolling 7 days to now" },
  { id: "all", label: "All", title: "Everything currently loaded" },
];

const HOUR = 3_600_000;

/** Midnight Algeria time on the day containing `at`, as a UTC instant. */
export function localDayStartUtc(at: Date): Date {
  const localMs = at.getTime() + ALGERIA_OFFSET_MINUTES * 60_000;
  const localDayMs = Math.floor(localMs / (24 * HOUR)) * 24 * HOUR;
  return new Date(localDayMs - ALGERIA_OFFSET_MINUTES * 60_000);
}

export function rangeStartUtc(
  id: RangeId,
  now: Date,
  spanStart: Date,
  spanEnd: Date,
): Date | null {
  switch (id) {
    case "today":
      return localDayStartUtc(now);
    case "24h":
      return new Date(now.getTime() - 24 * HOUR);
    case "7d":
      return new Date(now.getTime() - 7 * 24 * HOUR);
    case "all":
      return spanStart ?? spanEnd;
    default:
      return null;
  }
}

export function rangeLabel(id: RangeId): string {
  return RANGES.find((r) => r.id === id)?.label ?? "Today";
}

export interface HasTime {
  acq_datetime: string | Date;
}

function timeOf(d: HasTime): number {
  return typeof d.acq_datetime === "string"
    ? Date.parse(d.acq_datetime)
    : d.acq_datetime.getTime();
}

export function inRange(d: HasTime, start: Date, end: Date): boolean {
  const t = timeOf(d);
  return t >= start.getTime() && t <= end.getTime();
}

export interface Bucket {
  /** UTC instant at the top of the hour. */
  t: Date;
  count: number;
}

/** Detections per hour across [start, end], zero-filled.
 *
 *  Zero-filling matters: a gap in the data is not the same as no bars, and a
 *  histogram that omits empty hours implies continuous coverage we do not have. */
export function bucketByHour(dets: HasTime[], start: Date, end: Date): Bucket[] {
  const s = Math.floor(start.getTime() / HOUR) * HOUR;
  const e = end.getTime();
  if (e < s) return [];
  const out: Bucket[] = [];
  for (let t = s; t <= e; t += HOUR) {
    out.push({ t: new Date(t), count: 0 });
  }
  if (!out.length) return out;
  const first = out[0].t.getTime();
  const last = out[out.length - 1].t.getTime();
  for (const d of dets) {
    const t = timeOf(d);
    if (t < first || t > last + HOUR - 1) continue;
    const i = Math.floor((t - first) / HOUR);
    const b = out[i];
    if (b) b.count += 1;
  }
  return out;
}

function local(d: Date): Date {
  return new Date(d.getTime() + ALGERIA_OFFSET_MINUTES * 60_000);
}

/** "14:33" in Algeria time. The suffix is added by the caller, since the
 *  control that shows it already says the clock is local. */
export function formatLocalClock(d: Date): string {
  const l = local(d);
  return `${String(l.getUTCHours()).padStart(2, "0")}:${String(l.getUTCMinutes()).padStart(2, "0")}`;
}

export function formatLocalDay(d: Date): string {
  const l = local(d);
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${l.getUTCDate()} ${months[l.getUTCMonth()]}`;
}

export function formatLocalDayFull(d: Date): string {
  const l = local(d);
  return `${formatLocalDay(d)} ${l.getUTCFullYear()}`;
}

/** "2 d 4 h" / "4 h 12 m" / "18 m" — span length, coarse on purpose. */
export function humanSpan(ms: number): string {
  if (ms <= 0) return "0 m";
  const mins = Math.floor(ms / 60_000);
  if (mins < 60) return `${mins} m`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) {
    const rem = mins % 60;
    return rem ? `${hours} h ${rem} m` : `${hours} h`;
  }
  const days = Math.floor(hours / 24);
  const remH = hours % 24;
  return remH ? `${days} d ${remH} h` : `${days} d`;
}