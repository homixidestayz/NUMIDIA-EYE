import type {
  AiResult,
  Detection,
  IncidentsResponse,
  SystemData,
  SystemStatus,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function readJson<T>(res: Response): Promise<T> {
  const body = (await res.json()) as T;
  return body;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    throw new ApiError(res.status, `API ${res.status} ${res.statusText}`);
  }
  return readJson<T>(res);
}

export const api = {
  baseUrl: BASE,
  status: () => get<SystemStatus>("/system/status"),
  systemData: () => get<SystemData>("/system/data"),
  detections: (limit = 500) => get<Detection[]>(`/detections?limit=${limit}`),
  detection: (id: string) => get<Detection>(`/detections/${id}`),
  incidents: () => get<IncidentsResponse>("/incidents"),
  ai: async (id: string): Promise<AiResult> => {
    const res = await fetch(`${BASE}/detections/${id}/ai`);
    // Backend intentionally returns structured body even when 503 (AI unavailable).
    return readJson<AiResult>(res);
  },
};

export function fmtDate(iso?: string | null): string {
  if (!iso) return "UNAVAILABLE";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "UNAVAILABLE";
  return date.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

export function isApiError(err: unknown): err is ApiError {
  return err instanceof ApiError;
}
