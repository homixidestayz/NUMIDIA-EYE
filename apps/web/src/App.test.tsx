// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { t } from "./i18n";
import type { Detection, SystemStatus } from "./types";

// The map is a leaf component with its own WebGL/CDN lifecycle; it is not the
// subject of these tests. Stubbing it keeps these focused on the detail
// request lifecycle in App.
vi.mock("./components/DetectionMap", () => ({
  default: () => null,
}));

/** Verbatim capture of GET /system/status from the live backend. */
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

/** Verbatim captures of GET /detections/{id}. */
const RECORDED_DETECTION: Detection = {
  detection_id: "c58531840fda80e1",
  lat: 36.59527,
  lon: 2.87984,
  acq_datetime: "2026-09-21T01:30:00Z",
  acq_date: "2026-09-21",
  acq_time: "0130",
  satellite: "N21",
  instrument: null,
  confidence: 0.6,
  confidence_raw: "nominal",
  bright_ti4: 312.61,
  bright_ti5: 290.9,
  scan: 0.41,
  track: 0.37,
  frp: 0.82,
  daynight: "N",
  version: "2.0NRT",
  type: null,
  source: "VIIRS_NOAA21_C2",
  source_url:
    "https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-21-viirs-c2/csv/J2_VJ320_M_C2_361.csv",
  fetched_at: "2026-09-22T14:50:53.535115Z",
  wilaya_code: "09",
  wilaya_name: "Blida",
  state: "HISTORICAL",
};

let requested: string[];
let detailHandler: (url: string) => Promise<Response>;

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    statusText: ok ? "OK" : "Not Found",
    json: async () => body,
  } as Response;
}

beforeEach(() => {
  requested = [];
  detailHandler = async () => jsonResponse(RECORDED_DETECTION);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      requested.push(url);
      if (url.includes("/system/status")) return jsonResponse(RECORDED_STATUS);
      if (/\/detections\/[^/?]+$/.test(url)) return detailHandler(url);
      if (url.includes("/detections")) return jsonResponse([RECORDED_DETECTION]);
      throw new Error(`unexpected request: ${url}`);
    })
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("authoritative detection detail", () => {
  // The list row does NOT print the detection id (that appears only in the
  // detail card), so readiness is detected by the presence of a list row.
  async function renderReadyApp(): Promise<HTMLElement> {
    render(<App />);
    await waitFor(
      () => expect(document.querySelector(".det-list li")).toBeTruthy(),
      { timeout: 4000 }
    );
    return document.querySelector(".det-list li") as HTMLElement;
  }

  function clickDetection(row: HTMLElement): void {
    row.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  }

  it("requests GET /detections/{id} when a detection is selected", async () => {
    const row = await renderReadyApp();
    clickDetection(row);

    await waitFor(() =>
      expect(requested.some((u) => /\/detections\/c58531840fda80e1$/.test(u))).toBe(true)
    );
    // The unavailable AI endpoint is never contacted for a detail view.
    expect(requested.some((u) => u.includes("/detections/c58531840fda80e1/ai"))).toBe(false);
  });

  it("shows the localized missing state on 404 instead of crashing", async () => {
    detailHandler = async () => jsonResponse({ detail: "detection not found" }, false, 404);
    const row = await renderReadyApp();
    clickDetection(row);

    await waitFor(() => expect(screen.getByText(t("en").detail_not_found)).toBeTruthy());
  });

  it("shows the localized error state on a non-404 failure", async () => {
    detailHandler = async () => jsonResponse(null, false, 503);
    const row = await renderReadyApp();
    clickDetection(row);

    await waitFor(() => expect(screen.getByText(t("en").detail_error)).toBeTruthy());
  });

  it("does not invent detail data when the authoritative request fails", async () => {
    detailHandler = async () => jsonResponse(null, false, 404);
    const row = await renderReadyApp();
    clickDetection(row);
    await waitFor(() => expect(screen.getByText(t("en").detail_not_found)).toBeTruthy());

    // The fallback shown is the real list row and is labelled non-authoritative.
    expect(screen.getByText(t("en").detail_unavailable)).toBeTruthy();
  });

  it("renders the authoritative detail values once loaded", async () => {
    const row = await renderReadyApp();
    clickDetection(row);

    await waitFor(() => expect(screen.getByText("c58531840fda80e1")).toBeTruthy());
    const cards = Array.from(document.querySelectorAll(".detail-card")).map(
      (el) => el.textContent ?? ""
    );
    const text = cards.join(" | ");
    expect(text).toContain("36.59527");
    expect(text).toContain("2.87984");
    expect(text).toContain("VIIRS_NOAA21_C2");
    expect(text).toContain("Blida");
    expect(text).toContain("312.61");
    expect(text).toContain("60%");
  });
});