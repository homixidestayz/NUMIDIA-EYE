// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import FlowRail from "./FlowRail";
import { t } from "../i18n";

/**
 * The operational chain must report real state and nothing else. These tests
 * pin that a stage only reads "ready" when the data that stage needs actually
 * exists, and that a failed request reads "unavailable" instead of showing a
 * plausible value.
 */
const dict = t("en");
afterEach(cleanup);

function rail(over: Partial<Parameters<typeof FlowRail>[0]> = {}) {
  const props = {
    dict,
    detections: 500,
    detectState: "LIVE",
    selectionMade: true,
    detailReady: true,
    aiServed: true,
    aiModel: "verifier-v2",
    incidentsCount: 409,
    reportReady: true,
    ...over,
  };
  return render(<FlowRail {...props} />);
}

function node(key: string): HTMLElement {
  return screen.getByTestId(`flow-${key}`);
}
function value(key: string): string {
  return screen.getByTestId(`flow-${key}-value`).textContent ?? "";
}

describe("FlowRail", () => {
  it("renders the five stages in order", () => {
    rail();
    const names = Array.from(document.querySelectorAll(".flow-name")).map(
      (el) => el.textContent
    );
    expect(names).toEqual([
      dict.flow_detect,
      dict.flow_verify,
      dict.flow_understand,
      dict.flow_prioritize,
      dict.flow_respond,
    ]);
  });

  it("shows the real detection count and data state for DETECT", () => {
    rail({ detections: 2373, detectState: "LIVE" });
    expect(value("detect")).toBe("2373 · LIVE");
  });

  it("shows the real model name for VERIFY only when a result was served", () => {
    rail({ aiServed: true, aiModel: "verifier-v2" });
    expect(value("verify")).toBe("verifier-v2");
  });

  it("never shows a verdict for VERIFY before the model has run", () => {
    rail({ aiServed: false, aiModel: null });
    expect(value("verify")).toBe(dict.flow_idle);
    expect(node("verify").closest("li")?.className).toContain("is-idle");
  });

  it("asks for a selection instead of inventing one", () => {
    rail({
      selectionMade: false,
      detailReady: false,
      aiServed: false,
      aiModel: null,
      detections: 0,
      detectState: "UNAVAILABLE",
    });
    expect(value("detect")).toBe(dict.flow_select);
    expect(value("verify")).toBe(dict.flow_select);
    expect(value("understand")).toBe(dict.flow_select);
  });

  it("reports PRIORITIZE as unavailable when the request failed", () => {
    rail({ incidentsCount: null });
    expect(value("prioritize")).toBe(dict.flow_unavailable);
    expect(node("prioritize").closest("li")?.className).toContain("is-unavailable");
  });

  it("does not claim a count of zero incidents as a real result", () => {
    rail({ incidentsCount: 0 });
    expect(value("prioritize")).toBe(dict.incidents_empty);
  });

  it("shows the real incident count when PRIORITIZE has data", () => {
    rail({ incidentsCount: 409 });
    expect(value("prioritize")).toBe(`409 ${dict.incidents_count}`);
  });

  it("keeps RESPOND idle until a real report is open", () => {
    rail({ reportReady: false });
    expect(value("respond")).toBe(dict.flow_idle);
    expect(node("respond").closest("li")?.className).toContain("is-idle");
  });

  it("renders Arabic labels without losing the real values", () => {
    const ar = t("ar");
    render(
      <FlowRail
        dict={ar}
        detections={12}
        detectState="LIVE"
        selectionMade
        detailReady
        aiServed
        aiModel="verifier-v2"
        incidentsCount={3}
        reportReady={false}
      />
    );
    expect(screen.getByTestId("flow-detect").textContent).toBe(ar.flow_detect);
    expect(screen.getByTestId("flow-verify-value").textContent).toBe("verifier-v2");
  });

  it("never leaks a fabricated probability into the chain", () => {
    rail();
    for (const el of Array.from(document.querySelectorAll(".flow-value"))) {
      expect(el.textContent ?? "").not.toMatch(/\d\.\d{4}/);
    }
  });
});

describe("FlowRail does not re-request anything", () => {
  beforeEach(() => vi.stubGlobal("fetch", vi.fn()));
  afterEach(() => vi.unstubAllGlobals());

  it("issues no network calls of its own", () => {
    rail();
    expect(fetch).not.toHaveBeenCalled();
  });
});