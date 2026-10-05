// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import StatusHeader, { describeAi, describeFirms } from "./StatusHeader";
import Sidebar from "./Sidebar";
import { t } from "../i18n";
import type { Detection, SystemStatus } from "../types";

afterEach(cleanup);

/**
 * RECORDED_STATUS is a verbatim capture of GET /system/status from the live
 * backend: firms=CONNECTED, ai=UNAVAILABLE, model=null, db=OK, data_state=LIVE.
 * RECORDED_DETECTION is a verbatim capture of one GET /detections row.
 * These fixtures only drive rendering; no production data is invented here.
 */
const RECORDED_STATUS: SystemStatus = {
  firms: "CONNECTED",
  firms_last_fetch: "2026-09-29T22:26:03.805165Z",
  ai: "UNAVAILABLE",
  model: null,
  db: "OK",
  data_state: "LIVE",
  detections_count: 2373,
  message:
    "Live: 570 freshly acquired VIIRS detections via FIRMS NRT API (VIIRS_NOAA21_NRT, VIIRS_SNPP_NRT, VIIRS_NOAA20_NRT); pipeline healthy. AI verifier UNAVAILABLE until a labeled, evaluated model exists. Alerts are PROTOTYPE ONLY - not Civil Protection.",
};

const RECORDED_DETECTION: Detection = {
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
  type: null,
  source: "VIIRS_NOAA21_NRT",
  source_url:
    "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_MAP_KEY}/VIIRS_NOAA21_NRT/-9.0,18.0,12.0,38.0/1",
  fetched_at: "2026-09-29T21:32:35.669241Z",
  wilaya_code: "37",
  wilaya_name: "Tindouf",
  state: "LIVE",
};

const FORBIDDEN = [
  /AI verified/i,
  /AI active/i,
  /AI confidence/i,
  /verified fire/i,
  /model ready/i,
  /Incidents: pending/i,
];

function renderHeader(status: SystemStatus | null, lang: "en" | "ar" = "en") {
  return render(
    <StatusHeader status={status} dict={t(lang)} onToggleLang={() => {}} />
  );
}

function renderSidebar(status: SystemStatus | null, lang: "en" | "ar" = "en") {
  return render(
    <Sidebar
      status={status}
      detections={[RECORDED_DETECTION]}
      lang={lang}
      dict={t(lang)}
      detail={RECORDED_DETECTION}
      detailPhase="ready"
      detailStale={false}
      onAiResult={() => {}}
      onSelect={() => {}}
      onCloseDetail={() => {}}
    />
  );
}

describe("system status rendering", () => {
  it("shows the backend data_state (LIVE) rather than a frontend guess", () => {
    renderHeader(RECORDED_STATUS);
    expect(screen.getByText("LIVE")).toBeTruthy();
  });

  it("renders FIRMS connectivity from the backend", () => {
    renderHeader(RECORDED_STATUS);
    expect(screen.getByText(/CONNECTED/)).toBeTruthy();
  });

  it("renders the AI verifier as unavailable when ai=UNAVAILABLE", () => {
    renderHeader(RECORDED_STATUS);
    expect(screen.getByText(/Unavailable — no evaluated model deployed/)).toBeTruthy();
  });

  it("never invents a model name when model is null", () => {
    renderHeader(RECORDED_STATUS);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/undefined/i);
    expect(text).not.toMatch(/\(null\)/);
    expect(text).not.toMatch(/model\s*[:=]\s*[A-Za-z0-9_-]+\.(joblib|pkl)/i);
    expect(describeAi(RECORDED_STATUS, t("en"))).toBe(
      "Unavailable — no evaluated model deployed"
    );
  });

  it("does not claim verification anywhere in the rendered output", () => {
    renderHeader(RECORDED_STATUS);
    renderSidebar(RECORDED_STATUS);
    const text = document.body.textContent ?? "";
    for (const pattern of FORBIDDEN) {
      expect(text, `forbidden phrase: ${pattern}`).not.toMatch(pattern);
    }
  });

  it("no longer contains the false 'Incidents: pending' string in EN or AR", () => {
    expect(t("en")).not.toHaveProperty("incidents");
    expect(t("ar")).not.toHaveProperty("incidents");
    renderSidebar(RECORDED_STATUS, "en");
    renderSidebar(RECORDED_STATUS, "ar");
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/Incidents: pending/i);
    expect(text).not.toMatch(/الحوادث: قيد الإعداد/);
  });

  it("keeps live satellite data visually distinct from AI availability", () => {
    renderHeader(RECORDED_STATUS);
    const text = document.body.textContent ?? "";
    // LIVE is present (real FIRMS data) AND AI is explicitly unavailable.
    expect(text).toMatch(/LIVE/);
    expect(text).toMatch(/AI verifier/);
    expect(text).toMatch(/no evaluated model deployed/);
  });

  it("reflects a non-connected FIRMS state from the backend", () => {
    const degraded: SystemStatus = { ...RECORDED_STATUS, firms: "DISCONNECTED" };
    expect(describeFirms(degraded, t("en"))).toBe("DISCONNECTED");
    renderHeader(degraded);
    expect(screen.getByText(/DISCONNECTED/)).toBeTruthy();
    // Lookbehind so DISCONNECTED does not satisfy a bare CONNECTED match.
    expect(screen.queryByText(/(?<!DIS)CONNECTED/)).toBeNull();
  });

  it("reflects a non-LIVE data_state from the backend", () => {
    const stale: SystemStatus = { ...RECORDED_STATUS, data_state: "STALE" };
    renderHeader(stale);
    expect(screen.getByText(/STALE/)).toBeTruthy();
    expect(screen.queryByText("LIVE")).toBeNull();
  });

  it("shows unknown rather than a value when no status has arrived", () => {
    expect(describeFirms(null, t("en"))).toBe("unknown");
    expect(describeAi(null, t("en"))).toBe("unknown");
  });

  it("shows a backend-reported model name only when the backend supplies one", () => {
    const withModel: SystemStatus = {
      ...RECORDED_STATUS,
      ai: "READY",
      model: "candidate_abc.joblib",
    };
    expect(describeAi(withModel, t("en"))).toBe("READY (candidate_abc.joblib)");
  });
});

describe("i18n status strings", () => {
  it("defines the new status keys in both English and Arabic", () => {
    for (const lang of ["en", "ar"] as const) {
      const dict = t(lang);
      expect(dict.db_status.length).toBeGreaterThan(0);
      expect(dict.status_unknown.length).toBeGreaterThan(0);
      expect(dict.ai_unavailable.length).toBeGreaterThan(0);
      expect(dict.ai_status.length).toBeGreaterThan(0);
      expect(dict.firms.length).toBeGreaterThan(0);
    }
    expect(t("en").db_status).toBe("Database");
    expect(t("ar").db_status).toBe("قاعدة البيانات");
  });

  it("keeps English and Arabic key structures identical", () => {
    expect(Object.keys(t("en")).sort()).toEqual(Object.keys(t("ar")).sort());
  });

  it("renders the AI status row in Arabic from the same API payload", () => {
    renderSidebar(RECORDED_STATUS, "ar");
    expect(screen.getByText("قاعدة البيانات")).toBeTruthy();
    expect(screen.getByText(/لا يوجد نموذج/)).toBeTruthy();
  });
});