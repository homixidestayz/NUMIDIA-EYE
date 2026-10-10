export type DataState = "LIVE" | "HISTORICAL" | "STALE" | "UNAVAILABLE";

export interface SystemStatus {
  firms: string;
  firms_last_fetch?: string | null;
  ai: string;
  model: string | null;
  data_state: DataState;
  detections_count: number;
  db: string;
  message?: string;
}

export interface Detection {
  detection_id: string;
  lat: number;
  lon: number;
  acq_datetime: string;
  satellite: string;
  instrument: string;
  confidence: number | null;
  confidence_raw: string | null;
  bright_ti4: number | null;
  bright_ti5: number | null;
  frp: number | null;
  daynight: string | null;
  state: DataState;
  source: string;
  source_url: string | null;
  fetched_at: string;
  wilaya_code: string | null;
  wilaya_name: string | null;
}

export interface PriorityFactor {
  name: string;
  value: number | null;
  normalized: number | null;
  weight: number;
  evidence: string;
}

export interface Incident {
  id: string;
  status: string;
  detection_count: number;
  first_acq: string;
  last_acq: string;
  persistence_hours: number | null;
  centroid_lat: number;
  centroid_lon: number;
  max_frp: number;
  satellites: string[];
  /** Wilaya NAMES, not codes. Resolve through the boundary set before using
   *  one as a map key. */
  wilayas: string[];
  verification: {
    status: string;
    evaluated: boolean;
    model: string | null;
    message: string;
    evidence: string[];
  } | null;
  priority: {
    level: string;
    score: number;
    factors: PriorityFactor[];
    unavailable_factors: string[];
    methodology: string;
    computed_at?: string;
  } | null;
}

export interface Environment {
  latitude: number;
  longitude: number;
  status: string;
  source: string | null;
  observed_at: string | null;
  elevation_m: number | null;
  temperature_2m_c: number | null;
  relative_humidity_2m_pct: number | null;
  wind_speed_10m_ms: number | null;
  wind_direction_10m_deg: number | null;
  wind_gusts_10m_ms: number | null;
  precipitation_mm: number | null;
  soil_moisture_0_1_m3_m3: number | null;
  soil_moisture_3_9_m3_m3: number | null;
  soil_moisture_9_27_m3_m3: number | null;
  soil_temperature_0_7_c: number | null;
  soil_temperature_7_28_c: number | null;
  reason: string | null;
  attached_to?: string;
  precision?: {
    centroid_spread_m: number | null;
    max_precision_m: number;
    exceeds_max_precision_m: boolean | null;
    note?: string;
  };
}

export interface WilayaFeature {
  type: "Feature";
  properties: {
    shapeISO: string;
    shapeName: string;
    shapeNameAr: string;
    created: string;
  };
  geometry:
    | { type: "Polygon"; coordinates: number[][][] }
    | { type: "MultiPolygon"; coordinates: number[][][][] };
}

export interface WilayaCollection {
  type: "FeatureCollection";
  features: WilayaFeature[];
}

/** Country outlines for world context. Natural Earth 110m via public/world.geojson
 *  — deliberately low resolution, and deliberately local so the map still
 *  renders with no network at a demo. */
export interface WorldFeature {
  type: "Feature";
  properties: { ADMIN?: string; NAME?: string; name?: string; [k: string]: unknown };
  geometry:
    | { type: "Polygon"; coordinates: number[][][] }
    | { type: "MultiPolygon"; coordinates: number[][][][] };
}

export interface WorldCollection {
  type: "FeatureCollection";
  features: WorldFeature[];
}

export interface AiResult {
  status: string;
  detection_id: string;
  probability: number | null;
  verified: boolean | null;
  model: string | null;
  prediction: string | null;
  threshold: number | null;
  non_fire_threshold?: number | null;
  features_schema: string | null;
  calibrated: boolean | null;
  scope: string | null;
  message: string | null;
}

/** Which map layers are painted. Lives here rather than in App so that no
 *  component has to import App back, which would be an import cycle. */
export interface LayerState {
  wilayas: boolean;
  detections: boolean;
  labels: boolean;
}