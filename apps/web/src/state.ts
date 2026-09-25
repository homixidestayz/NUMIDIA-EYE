import type { Detection, SystemBannerState, SystemStatus } from "./types";

export const UNAVAILABLE = "UNAVAILABLE";
export const NOT_YET_AVAILABLE = "NOT YET AVAILABLE";
export const DATA_UNAVAILABLE = "Data unavailable";

export function mapBannerState(status: SystemStatus | null): SystemBannerState {
  if (!status) return "UNAVAILABLE";
  if (status.data_state === "LIVE") return "LIVE";
  if (status.data_state === "STALE" || status.data_state === "HISTORICAL") return "STALE";
  return "UNAVAILABLE";
}

export function asText(value: unknown, fallback = UNAVAILABLE): string {
  if (value === null || value === undefined) return fallback;
  if (typeof value === "string" && value.trim().length === 0) return fallback;
  return String(value);
}

export function asNumber(value: unknown, digits = 3, fallback = UNAVAILABLE): string {
  if (typeof value !== "number" || Number.isNaN(value)) return fallback;
  return value.toFixed(digits);
}

export function calculateKpis(detections: Detection[]) {
  const now = Date.now();
  const oneDayMs = 24 * 60 * 60 * 1000;
  const active = detections.filter((d) => d.state === "LIVE").length;
  const recent = detections.filter((d) => {
    const t = new Date(d.acq_datetime).getTime();
    return !Number.isNaN(t) && now - t <= oneDayMs;
  }).length;
  const highFrp = detections.filter((d) => typeof d.frp === "number" && d.frp >= 50).length;
  const satellites = new Set(detections.map((d) => d.satellite).filter(Boolean)).size;

  return { active, recent, highFrp, satellites };
}

export function latestIngestionTime(detections: Detection[]): string {
  if (detections.length === 0) return UNAVAILABLE;
  let latest = 0;
  for (const d of detections) {
    const time = new Date(d.fetched_at).getTime();
    if (!Number.isNaN(time) && time > latest) latest = time;
  }
  return latest > 0 ? new Date(latest).toISOString() : UNAVAILABLE;
}
