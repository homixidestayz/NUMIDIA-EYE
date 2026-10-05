// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import Sidebar from "./Sidebar";
import { t } from "../i18n";
import type { Detection, SystemStatus } from "../types";

afterEach(cleanup);

/**
 * RECORDED_DETECTION is a verbatim capture of GET /detections/{id}
 * (detection c58531840fda80e1, Blida, VIIRS_NOAA21_C2, 2026-09-21T01:30:00Z).
 * Every asserted value below is the real API value.
 */
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

function renderSidebar(
  detail: Detection | null,
  detailPhase: "idle" | "loading" | "ready" | "missing" | "error",
  lang: "en" | "ar" = "en",
  detailStale = false
) {
  return render(
    <Sidebar
      status={RECORDED_STATUS}
      detections={[RECORDED_DETECTION]}
      lang={lang}
      dict={t(lang)}
      detail={detail}
      detailPhase={detailPhase}
      detailStale={detailStale}
      onAiResult={() => {}}
      onSelect={() => {}}
      onCloseDetail={() => {}}
    />
  );
}

/**
 * Text of the detail card only - excludes the sidebar meta/AI status block.
 * All .detail-card nodes are concatenated because the loading/missing/error
 * banner is itself a .detail-card and may precede the populated one.
 */
function cardText(container: HTMLElement): string {
  return Array.from(container.querySelectorAll(".detail-card"))
    .map((el) => el.textContent ?? "")
    .join(" | ");
}

describe("detection detail card", () => {
  it("renders the real recorded values from GET /detections/{id}", () => {
    const { container } = renderSidebar(RECORDED_DETECTION, "ready");
    const text = cardText(container);

    expect(text).toContain("36.59527"); // latitude
    expect(text).toContain("2.87984"); // longitude
    expect(text).toContain("Blida"); // wilaya name
    expect(text).toContain("09"); // wilaya code
    expect(text).toContain("VIIRS_NOAA21_C2"); // real FIRMS source
    expect(text).toContain("N21"); // satellite id
    expect(text).toContain("0.8 MW"); // FRP, toFixed(1) per existing schema convention
    expect(text).toContain("312.61"); // brightness TI4
    expect(text).toContain("290.90"); // brightness TI5
    expect(text).toContain("60%"); // FIRMS confidence
    expect(text).toContain("nominal"); // FIRMS confidence_raw
    expect(text).toContain("HISTORICAL"); // backend state
    expect(text).toContain("c58531840fda80e1"); // detection id
    expect(screen.getByText(t("en").acquired)).toBeTruthy();
  });

  it("labels the satellite confidence as FIRMS confidence, never as AI", () => {
    const { container } = renderSidebar(RECORDED_DETECTION, "ready");
    expect(screen.getByText("FIRMS confidence")).toBeTruthy();

    const text = cardText(container);
    // The confidence row must not be attributed to AI anywhere in the card.
    expect(text).not.toMatch(/AI\s*confidence/i);
    expect(text).not.toMatch(/confidence[^\n]*\bAI\b/i);
    expect(text).not.toMatch(/\bAI\b[^\n]*confidence/i);
  });

  it("shows no AI probability, model, or verification result in the card", () => {
    const { container } = renderSidebar(RECORDED_DETECTION, "ready");
    const text = cardText(container);
    expect(text).not.toMatch(/probability/i);
    expect(text).not.toMatch(/\bmodel\b/i);
    expect(text).not.toMatch(/verified/i);
    // The card states the AI verifier is unavailable and shows nothing else.
    expect(text).toContain(t("en").no_ai);
  });

  it("renders the localized unavailable state for null fields, never a fake value", () => {
    // A real record shape with nullable fields absent, exercising the null path.
    const sparse: Detection = {
      ...RECORDED_DETECTION,
      wilaya_name: null,
      wilaya_code: null,
      satellite: null,
      confidence: null,
      confidence_raw: null,
      bright_ti4: null,
      bright_ti5: null,
    };
    const { container } = renderSidebar(sparse, "ready");
    const text = cardText(container);
    const unavailable = t("en").field_unavailable;

    expect(text).toContain(unavailable);
    expect(text).not.toMatch(/NaN/);
    expect(text).not.toMatch(/undefined/);
    expect(text).not.toMatch(/\bnull\b/i);
    expect(text).not.toMatch(/\?/); // no "value ?" placeholder
  });

  it("renders a genuine 0 FRP as 0 rather than as unavailable", () => {
    const zeroFrp: Detection = { ...RECORDED_DETECTION, frp: 0 };
    const { container } = renderSidebar(zeroFrp, "ready");
    expect(cardText(container)).toContain("0.0 MW");
  });

  it("renders loading, missing, and error phases without crashing", () => {
    renderSidebar(null, "loading");
    expect(screen.getByText(t("en").detail_loading)).toBeTruthy();

    cleanup();
    renderSidebar(null, "missing");
    expect(screen.getByText(t("en").detail_not_found)).toBeTruthy();

    cleanup();
    renderSidebar(null, "error");
    expect(screen.getByText(t("en").detail_error)).toBeTruthy();
  });

  it("marks the list fallback as non-authoritative when detail failed", () => {
    const { container } = renderSidebar(RECORDED_DETECTION, "error", "en", true);
    expect(cardText(container)).toContain(t("en").detail_unavailable);
  });

  it("renders the LIVE state from the backend", () => {
    const { container } = renderSidebar({ ...RECORDED_DETECTION, state: "LIVE" }, "ready");
    const text = cardText(container);
    expect(text).toContain("LIVE");
    expect(text).not.toContain("HISTORICAL");
  });

  it("translates every new detail label into Arabic", () => {
    const { container } = renderSidebar(RECORDED_DETECTION, "ready", "ar");
    const text = cardText(container);
    expect(text).toContain("خط العرض");
    expect(text).toContain("خط الطول");
    expect(text).toContain("الولاية");
    expect(text).toContain("القمر الصناعي");
    expect(text).toContain("ثقة FIRMS");
    expect(text).toContain("الإشعاع TI4 (ك)");
    expect(text).toContain("الإشعاع TI5 (ك)");
    expect(text).toContain("حالة الكشف");
    expect(text).toContain("Blida"); // real values survive translation
  });

  it("has identical EN/AR key sets including the new detail labels", () => {
    expect(Object.keys(t("en")).sort()).toEqual(Object.keys(t("ar")).sort());
    for (const key of [
      "latitude",
      "longitude",
      "wilaya",
      "satellite",
      "brightness_ti4",
      "brightness_ti5",
      "detection_state",
      "field_unavailable",
      "detail_loading",
      "detail_not_found",
      "detail_error",
    ] as const) {
      expect(t("en")[key].length, key).toBeGreaterThan(0);
      expect(t("ar")[key].length, key).toBeGreaterThan(0);
    }
  });
});