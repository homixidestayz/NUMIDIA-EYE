import { describe, expect, it } from "vitest";
import source from "./AiVerification.tsx?raw";

/**
 * A static source audit of the AI panel.
 *
 * Behavioural coverage lives in AiVerification.dom.test.tsx (jsdom). This file
 * pins the honesty rules at the source level: the verdict, probability and
 * threshold may only come from the API response, and nothing may be hard-coded
 * or randomised. The source is imported via Vite's `?raw` so no Node-only
 * import is needed and `tsc -b` stays clean.
 */

/** Strip comments so prose describing a rule cannot trip the rule's own regex. */
const code = source
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/^\s*\/\/.*$/gm, "");

describe("AiVerification source honesty", () => {
  it("never randomises a probability", () => {
    expect(code).not.toMatch(/Math\s*\.\s*random/);
  });

  it("hard-codes no probability value", () => {
    expect(code).not.toMatch(/probability\s*[:=]\s*0\.\d/);
    expect(code).not.toMatch(/["']0\.\d{3,}["']/);
  });

  it("hard-codes no verdict as a fallback result", () => {
    expect(code).not.toMatch(
      /(prediction|verdict)\s*[:=]\s*["'](FIRE|NON_FIRE|UNCERTAIN)["']/
    );
  });

  it("fetches the real endpoint and reads the response", () => {
    expect(source).toContain("api.ai(");
    expect(source).toContain("result.probability");
    expect(source).toContain("result.prediction");
    expect(source).toContain("result.threshold");
    expect(source).toContain("result.model");
  });

  it("treats an unserved result as no verdict", () => {
    expect(source).toMatch(/status\s*===\s*["']available["']/);
    expect(source).toMatch(/probability\s*!=\s*null/);
  });

  it("labels output as an experimental prototype", () => {
    expect(source).toContain("dict.ai_experimental");
    expect(source).toContain("dict.ai_scope");
  });
});