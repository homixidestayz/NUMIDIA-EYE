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
  firms: string;
  firms_last_fetch?: string | null;
  ai: string;
  model?: string | null;
  db: string;
  data_state: DataState;
  detections_count: number;
  message: string;
}

export type AiPrediction = "FIRE" | "NON_FIRE" | "UNCERTAIN";

export interface AiResult {
  status: string;
  detection_id?: string | null;
  probability?: number | null;
  verified?: boolean | null;
  model?: string | null;
  /** Present only when a verified model served the request. */
  prediction?: AiPrediction | null;
  threshold?: number | null;
  non_fire_threshold?: number | null;
  features_schema?: string | null;
  calibrated?: boolean | null;
  /** Experimental-scope statement reported by the backend. */
  scope?: string | null;
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
  priority: PriorityResult;
}

/** One weighted input of the rule-based priority engine (real values only). */
export interface PriorityFactor {
  name: string;
  value: number;
  normalized: number;
  weight: number;
  evidence: string;
}

export interface PriorityResult {
  level: "LOW" | "MODERATE" | "HIGH" | "CRITICAL";
  score: number;
  factors: PriorityFactor[];
  unavailable_factors: string[];
  methodology: string;
  computed_at?: string;
}

export interface IncidentList {
  status: string;
  count: number;
  incidents: IncidentSummary[];
  methodology: Record<string, unknown>;
  note: string;
}

/** Real incident report assembled from stored data (RESPOND stage). */
export interface IncidentReport {
  incident_id: string;
  generated_at: string;
  detection_count: number;
  first_acq: string | null;
  last_acq: string | null;
  centroid_lat: number | null;
  centroid_lon: number | null;
  max_frp: number;
  frp_sum: number;
  satellites: string[];
  verification: { status: string; evaluated: boolean; model: string | null; message: string };
  priority: PriorityResult;
  sources: string[];
  limitations: string[];
  provenance: { methodology: string; incident_methodology: string; generator: string };
}

export type Lang = "en" | "ar";