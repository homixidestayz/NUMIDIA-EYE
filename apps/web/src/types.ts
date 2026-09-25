export type DataState = "LIVE" | "HISTORICAL" | "STALE" | "SAMPLE" | "DEMO" | "UNAVAILABLE";

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
  type?: string | null;
  source: string;
  source_url?: string | null;
  fetched_at: string;
  wilaya_code?: string | null;
  wilaya_name?: string | null;
  state: DataState;
  [feature: string]: unknown;
}

export interface SystemStatus {
  firms: "CONNECTED" | "STALE" | "DEGRADED" | "NOT_CONFIGURED" | "STARTING";
  firms_last_fetch?: string | null;
  ai: "READY" | "UNAVAILABLE";
  model?: string | null;
  db: string;
  data_state: DataState;
  detections_count: number;
  message: string;
}

export interface VerificationStatus {
  status: string;
  model?: string | null;
  message: string;
}

export interface IngestRun {
  run_id?: number;
  started_at?: string;
  finished_at?: string | null;
  mode: string;
  sources: string[];
  urls: string[];
  count_new: number;
  count_total: number;
  status: string;
  message: string;
}

export interface SystemData {
  data_state: DataState;
  ingest_fresh: boolean;
  detections: number;
  live: number;
  sources: string[];
  satellites: string[];
  max_acq?: string | null;
  last_ok_at?: string | null;
  bbox: {
    lon_min: number;
    lat_min: number;
    lon_max: number;
    lat_max: number;
  };
  recent_runs: IngestRun[];
  verification: VerificationStatus;
  live_window_hours: number;
  note: string;
}

export interface AiResult {
  status: string;
  detection_id?: string | null;
  probability?: number | null;
  verified?: boolean | null;
  model?: string | null;
  message: string;
}

export interface IncidentsResponse {
  status: string;
  incidents: Array<Record<string, unknown>>;
  message: string;
}

export type SystemBannerState = "LIVE" | "STALE" | "UNAVAILABLE";
