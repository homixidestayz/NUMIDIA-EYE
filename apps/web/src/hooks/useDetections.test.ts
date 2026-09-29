// @vitest-environment jsdom
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useDetections } from "./useDetections";
import type { Detection, SystemStatus } from "../types";

/**
 * RECORDED_* values are verbatim captures from the live API
 * (GET /system/status, GET /detections) taken from the running backend.
 * They are used ONLY to stub the network transport so the tests can prove the
 * hook passes API values through untouched. The hook itself never fabricates
 * a detection, a coordinate, or a fallback.
 */
const RECORDED_LIVE_DETECTION: Detection = {
  detection_id: "9803f0e3ae7452d4",
  lat: 27.57402,
  lon: -8.11681,
  acq_datetime: "2026-09-29T13:38:00Z",
  acq_date: "2026-09-29",
  acq_time: "1338",
  satellite: "N21",
  instrument: null,
  confidence: 0.2,
  confidence_raw: "low",
  bright_ti4: 331.02,
  bright_ti5: 297.11,
  scan: 0.39,
  track: 0.36,
  frp: 5.92,
  daynight: "D",
  version: "2.0NRT",
  source: "VIIRS_NOAA21_NRT",
  source_url:
    "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_MAP_KEY}/VIIRS_NOAA21_NRT/-9.0,18.0,12.0,38.0/1",
  fetched_at: "2026-09-29T21:32:35.669241Z",
  wilaya_code: "37",
  wilaya_name: "Tindouf",
  type: null,
  state: "LIVE",
};

const RECORDED_STATUS: SystemStatus = {
  firms: "CONNECTED",
  firms_last_fetch: "2026-09-29T22:26:03.805165Z",
  ai: "UNAVAILABLE",
  model: null,
  db: "OK",
  data_state: "LIVE",
  detections_count: 2373,
  message: "Live: 570 freshly acquired VIIRS detections via FIRMS NRT API.",
};

const RECORDED_STALE_STATUS: SystemStatus = {
  ...RECORDED_STATUS,
  data_state: "STALE",
};

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    statusText: ok ? "OK" : "Service Unavailable",
    json: async () => body,
  } as Response;
}

type Route = "status" | "detections";
let routes: Record<Route, () => Promise<Response>>;
let requestedUrls: string[];

beforeEach(() => {
  requestedUrls = [];
  routes = {
    status: async () => jsonResponse(RECORDED_STATUS),
    detections: async () => jsonResponse([RECORDED_LIVE_DETECTION]),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      requestedUrls.push(url);
      if (url.includes("/system/status")) return routes.status();
      if (url.includes("/detections")) return routes.detections();
      throw new Error(`unexpected request: ${url}`);
    })
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("useDetections", () => {
  it("fetches only /system/status and /detections", async () => {
    const { result } = renderHook(() => useDetections());
    await waitFor(() => expect(result.current.phase).toBe("ready"));

    const paths = requestedUrls.map((u) => new URL(u).pathname).sort();
    expect(paths).toEqual(["/detections", "/system/status"]);
    // No other backend surface is touched by the data layer.
    expect(requestedUrls.some((u) => u.includes("/incidents"))).toBe(false);
    expect(requestedUrls.some((u) => u.includes("/system/data"))).toBe(false);
  });

  it("starts in loading and returns API detections verbatim", async () => {
    const { result } = renderHook(() => useDetections());
    expect(result.current.phase).toBe("loading");
    expect(result.current.detections).toEqual([]);

    await waitFor(() => expect(result.current.phase).toBe("ready"));

    // Pass-through: the exact API record, nothing invented or reshaped.
    expect(result.current.detections).toEqual([RECORDED_LIVE_DETECTION]);
    expect(result.current.detections[0].lat).toBe(27.57402);
    expect(result.current.detections[0].lon).toBe(-8.11681);
    expect(result.current.detections[0].frp).toBe(5.92);
    expect(result.current.detections[0].wilaya_name).toBe("Tindouf");
    expect(result.current.isEmpty).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("surfaces status.data_state and never hardcodes it", async () => {
    const { result } = renderHook(() => useDetections());
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    expect(result.current.status?.data_state).toBe("LIVE");
    expect(result.current.isStale).toBe(false);
  });

  it("flags STALE when the API reports STALE", async () => {
    routes.status = async () => jsonResponse(RECORDED_STALE_STATUS);
    const { result } = renderHook(() => useDetections());
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    expect(result.current.isStale).toBe(true);
  });

  it("treats a genuine empty response as empty, not as an error", async () => {
    routes.detections = async () => jsonResponse([]);
    const { result } = renderHook(() => useDetections());

    await waitFor(() => expect(result.current.phase).toBe("ready"));
    expect(result.current.detections).toEqual([]);
    expect(result.current.isEmpty).toBe(true);
    expect(result.current.error).toBeNull();
  });

  it("produces an error state with the real reason when the API fails", async () => {
    routes.detections = async () => jsonResponse(null, false, 503);
    const { result } = renderHook(() => useDetections());

    await waitFor(() => expect(result.current.phase).toBe("error"));
    expect(result.current.error).toBe("API 503 Service Unavailable");
    // No fallback data is invented when the request fails.
    expect(result.current.detections).toEqual([]);
    expect(result.current.isEmpty).toBe(false);
  });

  it("keeps a healthy /system/status when /detections fails", async () => {
    routes.detections = async () => jsonResponse(null, false, 500);
    const { result } = renderHook(() => useDetections());

    await waitFor(() => expect(result.current.phase).toBe("error"));
    expect(result.current.status).toEqual(RECORDED_STATUS);
  });

  it("aborts the in-flight request on refresh so a stale response cannot land", async () => {
    // The superseded request resolves to a DIFFERENT, distinguishable payload.
    // If the abort guard were removed, this stale record would overwrite state.
    const STALE_DETECTION: Detection = {
      ...RECORDED_LIVE_DETECTION,
      detection_id: "stale0000000000ff",
      lat: 19.0,
      lon: 5.0,
      frp: 99.9,
      wilaya_name: "STALE-WILAYA",
    };

    let releaseFirst: (() => void) | null = null;
    let call = 0;

    routes.detections = async () => {
      call += 1;
      if (call === 1) {
        await new Promise<void>((resolve) => {
          releaseFirst = resolve;
        });
        return jsonResponse([STALE_DETECTION]);
      }
      return jsonResponse([RECORDED_LIVE_DETECTION]);
    };

    const { result } = renderHook(() => useDetections());
    expect(result.current.phase).toBe("loading");

    // Supersede the first request before it can resolve.
    await act(async () => {
      result.current.refresh();
    });

    await waitFor(() => expect(result.current.phase).toBe("ready"));
    expect(
      requestedUrls.filter((u) => u.includes("/detections")).length
    ).toBeGreaterThanOrEqual(2);

    // The first (now-aborted) response resolves late and must be discarded.
    await act(async () => {
      releaseFirst?.();
      await Promise.resolve();
    });

    expect(result.current.detections).toEqual([RECORDED_LIVE_DETECTION]);
    expect(result.current.detections[0].detection_id).toBe("9803f0e3ae7452d4");
    expect(
      result.current.detections.some((d) => d.wilaya_name === "STALE-WILAYA")
    ).toBe(false);
    expect(result.current.phase).toBe("ready");
  });

  it("aborts on unmount and never sets state afterwards", async () => {
    let release: (() => void) | null = null;
    routes.detections = async () => {
      await new Promise<void>((resolve) => {
        release = resolve;
      });
      return jsonResponse([RECORDED_LIVE_DETECTION]);
    };

    const { result, unmount } = renderHook(() => useDetections());
    unmount();
    await act(async () => {
      release?.();
      await Promise.resolve();
    });

    expect(result.current.phase).toBe("loading");
    expect(result.current.detections).toEqual([]);
  });
});
