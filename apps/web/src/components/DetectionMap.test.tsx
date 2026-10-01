// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// maplibre-gl touches browser APIs (URL.createObjectURL) at import time, which
// jsdom does not implement. The pure exported helpers under test need no map
// instance, so the module is stubbed. This does NOT stub the popup/cluster
// logic itself, only the map constructor.
vi.mock("maplibre-gl", () => {
  class MapStub {
    on() { return this; }
    remove() { return this; }
  }
  class PopupStub {
    setLngLat() { return this; }
    setDOMContent() { return this; }
    addTo() { return this; }
    remove() { return this; }
  }
  return { default: { Map: MapStub, Popup: PopupStub }, Map: MapStub, Popup: PopupStub };
});

import MapLegend from "./MapLegend";
import {
  CLUSTER_COUNT_FIELD,
  CLUSTER_FILTER,
  CLUSTER_LAYER_IDS,
  CLUSTER_OPTIONS,
  HISTORICAL_LAYER_ID,
  LIVE_LAYER_ID,
  SELECTABLE_LAYER_IDS,
  UNCLUSTERED_FILTER,
  buildPopupNode,
  unclusteredStateFilter,
} from "./DetectionMap";
import { t } from "../i18n";
import type { Detection } from "../types";

afterEach(cleanup);

/** Verbatim capture of GET /detections/{id} (detection c58531840fda80e1). */
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
  source_url: "https://example.invalid/x.csv",
  fetched_at: "2026-09-22T14:50:53.535115Z",
  wilaya_code: "09",
  wilaya_name: "Blida",
  state: "HISTORICAL",
};

describe("clustering configuration", () => {
  it("enables native MapLibre clustering over the real detection source", () => {
    expect(CLUSTER_OPTIONS.cluster).toBe(true);
    expect(CLUSTER_OPTIONS.clusterRadius).toBeGreaterThan(0);
    // Individual detections must reappear past this zoom.
    expect(CLUSTER_OPTIONS.clusterMaxZoom).toBeGreaterThan(0);
  });

  it("separates cluster layers from individual detection layers", () => {
    expect(CLUSTER_LAYER_IDS.length).toBeGreaterThan(0);
    // No layer is in both sets, so a cluster is never selectable as a detection.
    for (const id of CLUSTER_LAYER_IDS) {
      expect(SELECTABLE_LAYER_IDS).not.toContain(id);
    }
    expect(SELECTABLE_LAYER_IDS).toEqual([LIVE_LAYER_ID, HISTORICAL_LAYER_ID]);
  });

  it("identifies clusters by point_count and excludes them from detections", () => {
    expect(CLUSTER_FILTER).toEqual(["has", "point_count"]);
    expect(UNCLUSTERED_FILTER).toEqual(["!", ["has", "point_count"]]);
    // Individual detections must be unclustered AND in a known backend state.
    expect(unclusteredStateFilter("LIVE")).toEqual([
      "all",
      UNCLUSTERED_FILTER,
      ["==", ["get", "state"], "LIVE"],
    ]);
    expect(unclusteredStateFilter("HISTORICAL")).toEqual([
      "all",
      UNCLUSTERED_FILTER,
      ["==", ["get", "state"], "HISTORICAL"],
    ]);
  });

  it("labels a cluster with the detection count, never with fires or AI claims", () => {
    expect(CLUSTER_COUNT_FIELD).toEqual(["get", "point_count_abbreviated"]);
    const serialised = JSON.stringify(CLUSTER_COUNT_FIELD).toLowerCase();
    expect(serialised).not.toMatch(/fire|incident|verif|ai/);
  });
});

describe("map legend", () => {
  it("renders LIVE, HISTORICAL and cluster entries", () => {
    const dict = t("en");
    render(<MapLegend dict={dict} />);
    expect(screen.getByText(dict.legend_title)).toBeTruthy();
    expect(screen.getByText(dict.legend_live)).toBeTruthy();
    expect(screen.getByText(dict.legend_historical)).toBeTruthy();
    expect(screen.getByText(dict.legend_cluster)).toBeTruthy();
  });

  it("describes LIVE as recent satellite detections, not as verified fires", () => {
    const dict = t("en");
    render(<MapLegend dict={dict} />);
    const text = document.body.textContent ?? "";
    expect(dict.legend_live).toMatch(/FIRMS satellite detections/i);
    expect(text).not.toMatch(/verified/i);
    expect(text).not.toMatch(/AI\b/);
    expect(text).not.toMatch(/confirmed/i);
    expect(text).not.toMatch(/\bfires\b/i);
  });

  it("calls a cluster a grouping of detections", () => {
    const dict = t("en");
    render(<MapLegend dict={dict} />);
    expect(screen.getByText(dict.legend_cluster)).toBeTruthy();
    expect(dict.legend_cluster).toMatch(/detections/i);
    expect(dict.legend_cluster).not.toMatch(/fire|incident|verified/i);
  });

  it("renders in Arabic from the same dictionary contract", () => {
    const dict = t("ar");
    render(<MapLegend dict={dict} />);
    const text = document.body.textContent ?? "";
    expect(text).toContain("المفتاح");
    expect(text).toContain("كشوفات");
  });
});

describe("popup safety", () => {
  it("renders the real recorded detection values", () => {
    const node = buildPopupNode(RECORDED_DETECTION, t("en"), "en", false);
    const text = node.textContent ?? "";
    expect(text).toContain("0.8 MW");
    expect(text).toContain("60%");
    expect(text).toContain("Blida");
    expect(text).toContain("VIIRS_NOAA21_C2");
    expect(text).toContain("N21");
    expect(text).toContain("c58531840fda80e1");
    expect(node.getAttribute("dir")).toBe("ltr");
  });

  it("sets Arabic direction without changing content", () => {
    const node = buildPopupNode(RECORDED_DETECTION, t("ar"), "ar", false);
    expect(node.getAttribute("dir")).toBe("rtl");
    expect(node.textContent).toContain("Blida");
  });

  it("renders hostile backend text literally instead of as markup", () => {
    // TEST-ONLY payload simulating a malicious upstream FIRMS field.
    const hostile: Detection = {
      ...RECORDED_DETECTION,
      source: '<img src=x onerror="globalThis.__xss=1">',
      wilaya_name: "<script>globalThis.__xss=2</script>",
      detection_id: "<svg onload=alert(3)></svg>",
      confidence_raw: "</b><iframe src=javascript:alert(4)>",
    };

    const node = buildPopupNode(hostile, t("en"), "en", false);

    // The markup must appear as literal text...
    expect(node.textContent).toContain("<img src=x");
    expect(node.textContent).toContain("<script>");
    expect(node.textContent).toContain("<svg onload=alert(3)>");
    // ...and must NOT have produced any element or handler.
    expect(node.querySelector("img")).toBeNull();
    expect(node.querySelector("script")).toBeNull();
    expect(node.querySelector("svg")).toBeNull();
    expect(node.querySelector("iframe")).toBeNull();
    expect(node.innerHTML).not.toContain("<img");
    expect(node.innerHTML).not.toContain("<script");
    // No code ran.
    expect((globalThis as Record<string, unknown>)["__xss"]).toBeUndefined();
  });

  it("builds only text nodes - no element has an inline handler", () => {
    const node = buildPopupNode(RECORDED_DETECTION, t("en"), "en", true);
    const all = Array.from(node.querySelectorAll("*"));
    for (const el of all) {
      for (const attr of Array.from(el.attributes)) {
        expect(attr.name.startsWith("on"), `unexpected handler ${attr.name}`).toBe(false);
      }
    }
    expect(node.textContent).toContain(t("en").detail_unavailable);
  });

  it("renders the localized unavailable state for absent popup fields", () => {
    const sparse: Detection = {
      ...RECORDED_DETECTION,
      wilaya_name: null,
      satellite: null,
      confidence: null,
    };
    const node = buildPopupNode(sparse, t("en"), "en", false);
    expect(node.textContent).toContain(t("en").field_unavailable);
    expect(node.textContent).not.toContain("null");
    expect(node.textContent).not.toContain("undefined");
  });

  it("shows no AI probability, model, or verification claim in the popup", () => {
    const node = buildPopupNode(RECORDED_DETECTION, t("en"), "en", false);
    const text = node.textContent ?? "";
    expect(text).not.toMatch(/probability/i);
    expect(text).not.toMatch(/\bmodel\b/i);
    expect(text).not.toMatch(/verified/i);
  });
});