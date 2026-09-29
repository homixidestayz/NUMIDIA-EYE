import type { AiResult, Detection, IncidentList, SystemData, SystemStatus } from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

/**
 * Transport/HTTP failure with the real reason attached, so the UI can say
 * what actually went wrong instead of a single generic "unreachable" string.
 */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { signal });
  } catch (err) {
    if (isAbort(err)) throw err;
    throw new ApiError(err instanceof Error ? err.message : "network error", 0);
  }
  if (!res.ok) throw new ApiError(`API ${res.status} ${res.statusText}`, res.status);
  return (await res.json()) as T;
}

export const api = {
  status: (signal?: AbortSignal) => get<SystemStatus>("/system/status", signal),
  systemData: (signal?: AbortSignal) => get<SystemData>("/system/data", signal),
  detections: (limit = 500, signal?: AbortSignal) =>
    get<Detection[]>(`/detections?limit=${limit}`, signal),
  recent: (limit = 50, signal?: AbortSignal) =>
    get<Detection[]>(`/detections/recent?limit=${limit}`, signal),
  detection: (id: string, signal?: AbortSignal) =>
    get<Detection>(`/detections/${encodeURIComponent(id)}`, signal),
  incidents: (limit = 100, signal?: AbortSignal) =>
    get<IncidentList>(`/incidents?limit=${limit}`, signal),
  ai: async (id: string, signal?: AbortSignal): Promise<AiResult> => {
    // AI is served as an explicit 503 with a structured body, so res.ok is
    // deliberately not checked here.
    const res = await fetch(`${BASE}/detections/${encodeURIComponent(id)}/ai`, { signal });
    return (await res.json()) as AiResult;
  },
};

export function fmtDate(iso: string, lang?: string): string {
  return new Date(iso).toLocaleString(lang, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });
}
