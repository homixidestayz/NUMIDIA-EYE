// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AiVerification from "./AiVerification";
import { t } from "../i18n";

/**
 * Behavioural tests: every rendered value must come from the API response.
 */
const dict = t("en");
afterEach(cleanup);

function mockFetch(body: unknown, status = 200) {
  return vi.fn(async () => ({
    ok: status < 400,
    status,
    json: async () => body,
  }));
}

function served(prediction: string, probability: number) {
  return {
    status: "available",
    detection_id: "abc123",
    probability,
    verified: prediction === "FIRE",
    model: "verifier-v2",
    prediction,
    threshold: 0.52,
    non_fire_threshold: 0.3282,
    features_schema: "live-v1",
    calibrated: false,
    message: prediction,
  };
}

describe("AiVerification", () => {
  it("renders nothing without a detection", () => {
    const { container } = render(<AiVerification detectionId={null} dict={dict} />);
    expect(container.innerHTML).toBe("");
  });

  it("shows nothing before the user asks", () => {
    vi.stubGlobal("fetch", mockFetch(served("FIRE", 0.8)));
    render(<AiVerification detectionId="abc123" dict={dict} />);
    expect(screen.queryByTestId("ai-result")).toBeNull();
  });

  it("renders exactly what the API returned", async () => {
    vi.stubGlobal("fetch", mockFetch(served("FIRE", 0.8123)));
    render(<AiVerification detectionId="abc123" dict={dict} />);
    fireEvent.click(screen.getByRole("button"));

    await waitFor(() => expect(screen.getByTestId("ai-result")).toBeTruthy());
    expect(screen.getByTestId("ai-prediction").textContent).toBe("FIRE");
    expect(screen.getByTestId("ai-probability").textContent).toBe("0.8123");
    expect(screen.getByText("verifier-v2")).toBeTruthy();
    expect(screen.getByText("0.5200")).toBeTruthy();
    expect(screen.getByText("live-v1")).toBeTruthy();
  });

  it("renders NON_FIRE and UNCERTAIN verdicts too", async () => {
    for (const pred of ["NON_FIRE", "UNCERTAIN"] as const) {
      vi.stubGlobal("fetch", mockFetch(served(pred, 0.1)));
      const view = render(<AiVerification detectionId="abc123" dict={dict} />);
      fireEvent.click(screen.getByRole("button"));
      await waitFor(() =>
        expect(screen.getByTestId("ai-prediction").textContent).toBe(pred)
      );
      view.unmount();
    }
  });

  it("shows NO verdict when the backend declines with 503 AI_UNAVAILABLE", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch(
        {
          status: "AI_UNAVAILABLE",
          detection_id: "abc123",
          probability: null,
          message: "No verified verifier is registered.",
        },
        503
      )
    );
    render(<AiVerification detectionId="abc123" dict={dict} />);
    fireEvent.click(screen.getByRole("button"));

    await waitFor(() => expect(screen.getByTestId("ai-result")).toBeTruthy());
    expect(screen.queryByTestId("ai-prediction")).toBeNull();
    expect(screen.queryByTestId("ai-probability")).toBeNull();
    expect(screen.queryByText(/^(FIRE|NON_FIRE|UNCERTAIN)$/)).toBeNull();
    expect(screen.getByText(dict.ai_unavailable_result)).toBeTruthy();
  });

  it("shows no verdict when the request throws", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("network down");
      })
    );
    render(<AiVerification detectionId="abc123" dict={dict} />);
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(screen.getByTestId("ai-result")).toBeTruthy());
    expect(screen.queryByTestId("ai-prediction")).toBeNull();
    expect(screen.queryByTestId("ai-probability")).toBeNull();
  });

  it("always labels the result as an experimental prototype", async () => {
    vi.stubGlobal("fetch", mockFetch(served("FIRE", 0.9)));
    render(<AiVerification detectionId="abc123" dict={dict} />);
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(screen.getByText(dict.ai_experimental)).toBeTruthy());
    expect(screen.getByText(dict.ai_scope)).toBeTruthy();
  });

  it("calls the real /ai endpoint for the selected detection", async () => {
    const calls: unknown[][] = [];
    const f = vi.fn(async (...args: unknown[]) => {
      calls.push(args);
      return { ok: true, status: 200, json: async () => served("UNCERTAIN", 0.4) };
    });
    vi.stubGlobal("fetch", f);
    render(<AiVerification detectionId="deadbeef" dict={dict} />);
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    expect(String(calls[0][0])).toContain("/detections/deadbeef/ai");
  });
});