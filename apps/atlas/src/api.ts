import type {
  AiResult,
  Detection,
  Environment,
  Incident,
  SystemStatus,
  WilayaCollection,
  WorldCollection,
} from "./types";

/* The API is addressed relative to wherever the page was served from, so opening
   the app over a LAN address talks to that host rather than the visitor's own
   localhost. Override with ?api= (a bare number is read as a port). */
const DEFAULT_PORT = 8010;

function resolveApiBase(): string {
  const q = new URLSearchParams(window.location.search).get("api");
  if (q) {
    return /^\d+$/.test(q)
      ? `${location.protocol}//${location.hostname || "127.0.0.1"}:${q}`
      : q;
  }
  return `${location.protocol}//${location.hostname || "127.0.0.1"}:${DEFAULT_PORT}`;
}

export const API = resolveApiBase().replace(/\/$/, "");

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`API ${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

/* The verifier answers 503 *with* a populated AiResult body when no model can be
   registered — the status code carries the failure, the body carries the reason
   and the scope statement we are required to display. Treating it as a transport
   failure and throwing would throw that honest explanation away and replace it
   with "HTTP 503 Service Unavailable", which is less truthful, not more. */
async function getVerdict(path: string): Promise<AiResult> {
  const res = await fetch(`${API}${path}`);
  const body = (await res.json()) as AiResult;
  return { ...body, status: body.status || (res.ok ? "available" : "unavailable") };
}

export const api = {
  status: () => get<SystemStatus>("/system/status"),
  detections: (limit = 200) => get<Detection[]>(`/detections?limit=${limit}`),
  detection: (id: string) => get<Detection>(`/detections/${encodeURIComponent(id)}`),
  verify: (id: string) => getVerdict(`/detections/${encodeURIComponent(id)}/ai`),
  incidents: (limit = 60) =>
    get<{ status: string; count: number; incidents: Incident[]; methodology: string; note: string }>(
      `/incidents?limit=${limit}`,
    ).then((r) => r.incidents),
  incident: (id: string) => get<Incident>(`/incidents/${encodeURIComponent(id)}`),
  incidentReport: (id: string) =>
    get<Record<string, unknown>>(`/incidents/${encodeURIComponent(id)}/report`),
  environment: (id: string) => get<Environment>(`/incidents/${encodeURIComponent(id)}/environment`),
  wilayas: () => fetch("/wilayas.geojson").then((r) => r.json() as Promise<WilayaCollection>),
  /** World outlines. Local file, so the map still draws with no network. */
  world: () => fetch("/world.geojson").then((r) => r.json() as Promise<WorldCollection>),
};

export interface Loaded {
  status: SystemStatus;
  detections: Detection[];
  incidents: Incident[];
  wilayas: WilayaCollection;
}

/* React StrictMode runs mount effects twice in development. These endpoints are
   slow — /system/status alone measured 4.2s and /incidents 4.1s — so doubling
   them stacks eight concurrent requests onto one worker and the first paint
   moves out by tens of seconds. Share one in-flight batch instead.

   This dedupes concurrency only; the reference is dropped once the batch
   settles, so a later retry or a remount genuinely re-requests rather than
   replaying a stale success. */
let inflight: Promise<Loaded> | null = null;

export function loadAll(): Promise<Loaded> {
  if (inflight) return inflight;
  inflight = (async () => {
    const [status, wilayas, detections, incidents] = await Promise.all([
      api.status(),
      api.wilayas(),
      api.detections(200),
      api.incidents(60),
    ]);
    return { status, detections, incidents, wilayas };
  })();
  const clear = () => {
    inflight = null;
  };
  inflight.then(clear, clear);
  return inflight;
}