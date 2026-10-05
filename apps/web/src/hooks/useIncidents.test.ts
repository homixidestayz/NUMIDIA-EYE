// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useIncidents } from "./useIncidents";
import type { IncidentList, IncidentReport } from "../types";

/**
 * The hook must only ever hold what the API returned. It has no fallback list,
 * no locally synthesized priority and no placeholder report: a failed request
 * leaves the list empty with a visible reason.
 */
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const RECORDED_LIST: IncidentList = {
  status: "OK",
  count: 1,
  incidents: [
    {
      id: "INC-f5dac58df557",
      status: "UNVERIFIED_CLUSTER",
      detection_count: 7,
      first_acq: "2026-09-20T01:30:00+00:00",
      last_acq: "2026-09-21T02:15:00+00:00",
      persistence_hours: 24.75,
      centroid_lat: 31.81,
      centroid_lon: 5.99,
      max_frp: 4.2,
      satellites: ["N20"],
      wilayas: ["Ouargla"],
      verification: {
        status: "UNAVAILABLE",
        evaluated: false,
        model: null,
        message: "grouped without validated evidence",
      },
      priority: {
        level: "MODERATE",
        score: 0.4231,
        factors: [],
        unavailable_factors: [],
        methodology: "priority-v1",
      },
    },
  ],
  methodology: { methodology: "incident-v1" },
  note: "",
};

const RECORDED_REPORT = {
  incident_id: "INC-f5dac58df557",
  generated_at: "2026-09-22T10:00:00+00:00",
  detection_count: 7,
  first_acq: null,
  last_acq: null,
  centroid_lat: null,
  centroid_lon: null,
  max_frp: 4.2,
  frp_sum: 11.9,
  satellites: ["N20"],
  verification: RECORDED_LIST.incidents[0].verification,
  priority: RECORDED_LIST.incidents[0].priority,
  sources: ["VIIRS_NOAA20_C2"],
  limitations: ["not Civil Protection output"],
  provenance: { methodology: "report-v1", incident_methodology: "incident-v1", generator: "x" },
} as IncidentReport;

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return { ok, status, statusText: "OK", json: async () => body } as Response;
}

function stubFetch(handler: (url: string) => Response): ReturnType<typeof vi.fn> {
  const f = vi.fn(async (input: RequestInfo | URL) => handler(String(input)));
  vi.stubGlobal("fetch", f);
  return f;
}

describe("useIncidents", () => {
  it("loads real incidents from /incidents", async () => {
    const f = stubFetch((url) =>
      url.includes("/incidents?") ? jsonResponse(RECORDED_LIST) : jsonResponse(null, false, 404)
    );
    const { result } = renderHook(() => useIncidents());

    await waitFor(() => expect(result.current.phase).toBe("ready"));
    expect(f.mock.calls[0][0]).toContain("/incidents?limit=60");
    expect(result.current.incidents).toHaveLength(1);
    expect(result.current.incidents[0].id).toBe("INC-f5dac58df557");
    expect(result.current.incidents[0].priority.score).toBe(0.4231);
  });

  it("surfaces a real failure instead of substituting incidents", async () => {
    stubFetch(() => jsonResponse({ detail: "boom" }, false, 503));
    const { result } = renderHook(() => useIncidents());

    await waitFor(() => expect(result.current.phase).toBe("error"));
    expect(result.current.incidents).toEqual([]);
    expect(result.current.error).toContain("503");
  });

  it("treats an empty incident list as a real, ready state", async () => {
    stubFetch(() =>
      jsonResponse({ ...RECORDED_LIST, count: 0, incidents: [] })
    );
    const { result } = renderHook(() => useIncidents());

    await waitFor(() => expect(result.current.phase).toBe("ready"));
    expect(result.current.incidents).toEqual([]);
  });

  it("opens a real report for the requested incident", async () => {
    stubFetch((url) =>
      url.includes("/report")
        ? jsonResponse(RECORDED_REPORT)
        : jsonResponse(RECORDED_LIST)
    );
    const { result } = renderHook(() => useIncidents());
    await waitFor(() => expect(result.current.phase).toBe("ready"));

    act(() => result.current.openReport("INC-f5dac58df557"));
    await waitFor(() => expect(result.current.reportPhase).toBe("ready"));
    expect(result.current.report?.incident_id).toBe("INC-f5dac58df557");
    expect(result.current.report?.limitations).toContain("not Civil Protection output");
  });

  it("reports a failing report honestly and keeps no stale document", async () => {
    stubFetch((url) =>
      url.includes("/report")
        ? jsonResponse({ detail: "incident not found" }, false, 404)
        : jsonResponse(RECORDED_LIST)
    );
    const { result } = renderHook(() => useIncidents());
    await waitFor(() => expect(result.current.phase).toBe("ready"));

    act(() => result.current.openReport("INC-missing"));
    await waitFor(() => expect(result.current.reportPhase).toBe("error"));
    expect(result.current.report).toBeNull();
    expect(result.current.reportError).toContain("404");
  });

  it("closes a report back to idle", async () => {
    stubFetch((url) =>
      url.includes("/report")
        ? jsonResponse(RECORDED_REPORT)
        : jsonResponse(RECORDED_LIST)
    );
    const { result } = renderHook(() => useIncidents());
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    act(() => result.current.openReport("INC-f5dac58df557"));
    await waitFor(() => expect(result.current.reportPhase).toBe("ready"));

    act(() => result.current.closeReport());
    expect(result.current.reportPhase).toBe("idle");
    expect(result.current.report).toBeNull();
  });

  it("aborts its request on unmount", async () => {
    let captured: AbortSignal | undefined;
    const f = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      captured = init?.signal ?? undefined;
      return jsonResponse(RECORDED_LIST);
    });
    vi.stubGlobal("fetch", f);
    const { unmount } = renderHook(() => useIncidents());
    await waitFor(() => expect(captured).toBeDefined());
    unmount();
    expect(captured?.aborted).toBe(true);
  });
});