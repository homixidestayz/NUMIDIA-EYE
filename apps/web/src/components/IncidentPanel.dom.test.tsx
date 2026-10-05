// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import IncidentPanel from "./IncidentPanel";
import { t } from "../i18n";
import type { IncidentReport, IncidentSummary } from "../types";

/**
 * PRIORITIZE + RESPOND must render exactly what the backend returned: the real
 * priority-v1 level/score/factors, the real report and the real limitations.
 * Priority is rule-based and must never be presented as AI output, and a failed
 * request must degrade to a visible error rather than plausible-looking data.
 */
const dict = t("en");
afterEach(cleanup);

/** Shape captured from the live backend's /incidents response. */
const RECORDED_INCIDENT: IncidentSummary = {
  id: "INC-f5dac58df557",
  status: "UNVERIFIED_CLUSTER",
  detection_count: 7,
  first_acq: "2026-09-20T01:30:00+00:00",
  last_acq: "2026-09-21T02:15:00+00:00",
  persistence_hours: 24.75,
  centroid_lat: 31.81,
  centroid_lon: 5.99,
  max_frp: 4.2,
  satellites: ["N20", "N21"],
  wilayas: ["Ouargla"],
  verification: {
    status: "UNAVAILABLE",
    evaluated: false,
    model: null,
    message: "7 detection(s) grouped without validated evidence.",
  },
  priority: {
    level: "MODERATE",
    score: 0.4231,
    factors: [
      {
        name: "thermal_intensity",
        value: 4.2,
        normalized: 0.4139,
        weight: 0.4,
        evidence: "max FRP 4.2 MW across members",
      },
      {
        name: "persistence",
        value: 24.75,
        normalized: 0.3438,
        weight: 0.25,
        evidence: "24.75 h between first/last acquisition",
      },
      {
        name: "detection_count",
        value: 7,
        normalized: 0.35,
        weight: 0.2,
        evidence: "7 grouped detection(s)",
      },
      {
        name: "satellite_agreement",
        value: 2,
        normalized: 0.6667,
        weight: 0.15,
        evidence: "2 distinct satellite(s): ['N20', 'N21']",
      },
    ],
    unavailable_factors: [
      "proximity_to_settlements",
      "terrain_accessibility",
      "visual_verification",
    ],
    methodology: "priority-v1: ...",
    computed_at: "2026-09-22T10:00:00+00:00",
  },
};

const RECORDED_REPORT: IncidentReport = {
  incident_id: "INC-f5dac58df557",
  generated_at: "2026-09-22T10:00:00+00:00",
  detection_count: 7,
  first_acq: "2026-09-20T01:30:00+00:00",
  last_acq: "2026-09-21T02:15:00+00:00",
  centroid_lat: 31.81,
  centroid_lon: 5.99,
  max_frp: 4.2,
  frp_sum: 11.9,
  satellites: ["N20", "N21"],
  verification: RECORDED_INCIDENT.verification,
  priority: RECORDED_INCIDENT.priority,
  sources: ["VIIRS_NOAA20_C2", "VIIRS_NOAA21_C2"],
  limitations: [
    "Independent prototype, non-official data product; not Civil Protection output.",
    "Incident members are grouped FIRMS detections, not confirmed wildfires.",
  ],
  provenance: {
    methodology: "report-v1",
    incident_methodology: "incident-v1",
    generator: "numidia_intel.reports.build_report",
  },
};

function renderPanel(over: Partial<Parameters<typeof IncidentPanel>[0]> = {}) {
  const props = {
    dict,
    incidents: [RECORDED_INCIDENT],
    phase: "ready" as const,
    error: null,
    report: null,
    reportPhase: "idle" as const,
    reportError: null,
    onOpenReport: vi.fn(),
    onCloseReport: vi.fn(),
    ...over,
  };
  return render(<IncidentPanel {...props} />);
}

describe("IncidentPanel", () => {
  it("shows the real incident count and priority level", () => {
    renderPanel();
    expect(screen.getByTestId("incident-count").textContent).toBe(
      `1 ${dict.incidents_count}`
    );
    expect(screen.getByTestId("incident-priority-level").textContent).toBe("MODERATE");
    expect(screen.getByTestId("incident-priority-score").textContent).toBe("0.4231");
  });

  it("shows real grouping evidence, not a bare score", () => {
    renderPanel();
    expect(screen.getByText(/7\s/)).toBeTruthy();
    expect(screen.getByText("Ouargla")).toBeTruthy();
    expect(screen.getByText("24.75 h")).toBeTruthy();
    expect(screen.getByText(/N20, N21/)).toBeTruthy();
    expect(screen.getByText("4.2 MW")).toBeTruthy();
  });

  it("keeps the priority breakdown hidden until asked", () => {
    renderPanel();
    expect(screen.queryByTestId("priority-factors")).toBeNull();
  });

  it("breaks the score down into its four real weighted factors", () => {
    renderPanel();
    fireEvent.click(screen.getByTestId("toggle-priority"));
    expect(screen.getByTestId("priority-factors")).toBeTruthy();
    for (const name of [
      "thermal_intensity",
      "persistence",
      "detection_count",
      "satellite_agreement",
    ]) {
      expect(screen.getByTestId(`factor-${name}`)).toBeTruthy();
    }
    // The evidence string is the backend's, verbatim.
    expect(screen.getByText("max FRP 4.2 MW across members")).toBeTruthy();
  });

  it("states that priority is NOT the AI verifier", () => {
    renderPanel();
    fireEvent.click(screen.getByTestId("toggle-priority"));
    expect(screen.getByText(dict.priority_not_ai)).toBeTruthy();
  });

  it("lists the factors that have no data and contribute nothing", () => {
    renderPanel();
    fireEvent.click(screen.getByTestId("toggle-priority"));
    const text = screen.getByTestId("priority-unavailable").textContent ?? "";
    expect(text).toContain("proximity_to_settlements");
    expect(text).toContain("visual_verification");
  });

  it("renders the incident-level verification status exactly as reported", () => {
    renderPanel();
    fireEvent.click(screen.getByTestId("toggle-priority"));
    expect(screen.getByTestId("incident-verification").textContent).toBe("UNAVAILABLE");
    // ...and explains that this is about incident-level evidence, not the model.
    expect(screen.getByText(dict.incident_verification_note)).toBeTruthy();
  });

  it("shows a real error instead of an empty list when /incidents fails", () => {
    renderPanel({ incidents: [], phase: "error", error: "API 503 Service Unavailable" });
    expect(screen.getByTestId("incident-error").textContent).toContain("API 503");
    expect(screen.queryByTestId("incident-card")).toBeNull();
  });

  it("shows the real empty state when there are no incidents", () => {
    renderPanel({ incidents: [] });
    expect(screen.getByText(dict.incidents_empty)).toBeTruthy();
  });

  it("requests a report for the incident that was clicked", () => {
    const onOpenReport = vi.fn();
    renderPanel({ onOpenReport });
    fireEvent.click(screen.getByTestId("open-report"));
    expect(onOpenReport).toHaveBeenCalledWith("INC-f5dac58df557");
  });

  it("renders the real report with its limitations and prototype boundary", () => {
    renderPanel({ report: RECORDED_REPORT, reportPhase: "ready" });
    const panel = screen.getByTestId("incident-report");
    expect(panel.textContent).toContain("INC-f5dac58df557");
    expect(panel.textContent).toContain("VIIRS_NOAA21_C2");
    expect(panel.textContent).toContain("not Civil Protection output");
    expect(panel.textContent).toContain("not confirmed wildfires");
    expect(screen.getByText(dict.report_prototype)).toBeTruthy();
  });

  it("shows the report loading and error states honestly", () => {
    const { unmount } = renderPanel({ reportPhase: "loading" });
    expect(screen.getByTestId("report-loading")).toBeTruthy();
    unmount();

    renderPanel({ reportPhase: "error", reportError: "API 404 Not Found" });
    expect(screen.getByTestId("report-error").textContent).toContain("API 404");
  });

  it("renders Arabic labels for the priority factors", () => {
    const ar = t("ar");
    render(
      <IncidentPanel
        dict={ar}
        incidents={[RECORDED_INCIDENT]}
        phase="ready"
        error={null}
        report={null}
        reportPhase="idle"
        reportError={null}
        onOpenReport={() => {}}
        onCloseReport={() => {}}
      />
    );
    fireEvent.click(screen.getByTestId("toggle-priority"));
    expect(screen.getByTestId("factor-thermal_intensity").textContent).toContain(
      ar.priority_factor_thermal_intensity
    );
  });
});