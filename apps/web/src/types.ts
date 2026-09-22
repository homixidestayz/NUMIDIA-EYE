export type DataState = "LIVE" | "HISTORICAL" | "SAMPLE" | "DEMO" | "UNAVAILABLE";

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

export type Lang = "en" | "ar";