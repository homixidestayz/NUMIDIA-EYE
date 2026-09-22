import type { AiResult, Detection, SystemStatus } from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API ${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export const api = {
  status: () => get<SystemStatus>("/system/status"),
  detections: (limit = 500) => get<Detection[]>(`/detections?limit=${limit}`),
  detection: (id: string) => get<Detection>(`/detections/${id}`),
  ai: async (id: string): Promise<AiResult> => {
    const res = await fetch(`${BASE}/detections/${id}/ai`);
    // AI is served as an explicit 503 with a structured body.
    const body = (await res.json()) as AiResult;
    return body;
  },
};

export function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });
}