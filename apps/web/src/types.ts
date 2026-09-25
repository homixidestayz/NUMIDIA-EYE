export type DataState =
  | "LIVE"
  | "HISTORICAL"
  | "STALE"
  | "SAMPLE"
  | "DEMO"
  | "UNAVAILABLE";

export interface Detection {
  detection_id: string;
  lat: number;
  lon: number;
  acq_datetime: string;
  acq_date: string;
  acq_time: string;
  satellite?: string | null;
  instrument?: string | null;
  confidence?: number | null;
  confidence_raw?: string | null;
  bright_ti4?: number | null;
  bright_ti5?: number | null;
  scan?: number | null;
  track?: number | null;
  frp: number;
  daynight?: string | null;
  version?: string | null;
  source: string;
  source_url?: string | null;
  fetched_at: string;
  state: DataState;
  [feature: string]: unknown;
}

export interface SystemStatus {
  firms: string;
  firms_last_fetch?: string | null;
  ai: string;
  model?: string | null;
  db: string;
  data_state: DataState;
  detections_count: number;
  message: string;
}

export interface AiResult {
  status: string;
  detection_id?: string | null;
  probability?: number | null;
  verified?: boolean | null;
  model?: string | null;
  message: string;
}

export interface SystemData {
  data_state: DataState;
  ingest_fresh: boolean;
  detections: number;
  live: number;
  sources: string[];
  satellites: string[];
  max_acq: string | null;
  last_ok_at: string | null;
  bbox: { lon_min: number; lat_min: number; lon_max: number; lat_max: number };
  recent_runs: Array<Record<string, unknown>>;
  verification: { status: string; model: string | null; message: string };
  live_window_hours: number;
  note: string;
}

export interface IncidentSummary {
  id: string;
  status: string;
  detection_count: number;
  first_acq: string | null;
  last_acq: string | null;
  persistence_hours: number;
  centroid_lat: number | null;
  centroid_lon: number | null;
  max_frp: number;
  satellites: string[];
  wilayas: string[];
  verification: { status: string; evaluated: boolean; model: string | null; message: string };
  priority: Record<string, unknown>;
}

export interface IncidentList {
  status: string;
  count: number;
  incidents: IncidentSummary[];
  methodology: Record<string, unknown>;
  note: string;
}

export type Lang = "en" | "ar";