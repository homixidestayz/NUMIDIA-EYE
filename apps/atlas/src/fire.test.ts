import { describe, expect, it } from "vitest";
import {
  BUCKET_COLORS,
  BUCKET_COUNT,
  FRP_BREAKS,
  bucketFor,
  bucketLabel,
  coreAlpha,
  coreTipY,
  flameImageData,
  flameImageNames,
  matchExpression,
  outlineScale,
  radiusScale,
} from "./fire";

describe("FRP buckets", () => {
  it("has breaks ascending and a matching bucket count", () => {
    for (let i = 1; i < FRP_BREAKS.length; i++) {
      expect(FRP_BREAKS[i]).toBeGreaterThan(FRP_BREAKS[i - 1]);
    }
    expect(BUCKET_COUNT).toBe(FRP_BREAKS.length + 1);
  });

  it("puts a missing FRP in the lowest bucket rather than inventing a size", () => {
    // A null FRP must not render as a large flame. Lowest bucket is the
    // smallest, so an unmeasured detection never implies a big fire.
    expect(bucketFor(null)).toBe(0);
    expect(bucketFor(undefined)).toBe(0);
    expect(bucketFor(Number.NaN)).toBe(0);
  });

  it("never returns a bucket outside the ramp for absurd values", () => {
    for (const v of [-1, 0, 9.9, 10, 99, 100, 499, 500, 1999, 2000, 1e9]) {
      const b = bucketFor(v);
      expect(b).toBeGreaterThanOrEqual(0);
      expect(b).toBeLessThan(BUCKET_COUNT);
    }
  });

  it("increases monotonically with FRP", () => {
    let prev = -1;
    for (const v of [1, 20, 200, 800, 5000]) {
      const b = bucketFor(v);
      expect(b).toBeGreaterThanOrEqual(prev);
      prev = b;
    }
    expect(bucketFor(5000)).toBeGreaterThan(bucketFor(1));
  });

  it("places each break value in the bucket above it", () => {
    expect(bucketFor(FRP_BREAKS[0])).toBe(1);
    expect(bucketFor(FRP_BREAKS[1])).toBe(2);
  });

  it("names each bucket so the legend can state the real range", () => {
    for (let b = 0; b < BUCKET_COUNT; b++) {
      expect(bucketLabel(b)).toMatch(/MW/);
      expect(bucketLabel(b).length).toBeGreaterThan(3);
    }
    expect(bucketLabel(BUCKET_COUNT - 1)).toMatch(/>|above/i);
  });
});

describe("flame radius", () => {
  it("is strictly increasing with FRP within a bucket", () => {
    expect(radiusScale(5)).toBeLessThan(radiusScale(40));
    expect(radiusScale(40)).toBeLessThan(radiusScale(400));
  });

  it("keeps a null FRP at the smallest size", () => {
    expect(radiusScale(null)).toBe(radiusScale(0));
  });

  it("stays inside a sane pixel band so a big fire cannot cover the country", () => {
    for (const v of [0, 10, 100, 500, 2000, 1e7]) {
      const s = radiusScale(v);
      expect(s).toBeGreaterThan(0);
      expect(s).toBeLessThan(60);
    }
  });
});

describe("flame image", () => {
  it("produces one correctly sized image per bucket", () => {
    for (let b = 0; b < BUCKET_COUNT; b++) {
      const img = flameImageData(b, 64);
      expect(img.width).toBe(64);
      expect(img.height).toBe(64);
      expect(img.data).toHaveLength(64 * 64 * 4);
    }
  });

  it("rejects an out-of-range bucket rather than silently wrapping", () => {
    expect(() => flameImageData(-1, 64)).toThrow();
    expect(() => flameImageData(BUCKET_COUNT, 64)).toThrow();
    expect(() => flameImageData(1.5, 64)).toThrow();
  });
});

describe("flame intensity", () => {
  // These are the parameters that decide whether a bigger fire looks bigger.
  // Asserting them directly avoids testing a stubbed rasteriser.
  it("brightens the core as FRP rises", () => {
    for (let b = 1; b < BUCKET_COUNT; b++) {
      expect(coreAlpha(b)).toBeGreaterThan(coreAlpha(b - 1));
    }
    for (let b = 0; b < BUCKET_COUNT; b++) {
      expect(coreAlpha(b)).toBeGreaterThan(0);
      expect(coreAlpha(b)).toBeLessThanOrEqual(1);
    }
  });

  it("lifts the core tip as FRP rises", () => {
    for (let b = 1; b < BUCKET_COUNT; b++) {
      expect(coreTipY(b)).toBeLessThan(coreTipY(b - 1));
    }
  });

  it("gives every bucket a distinct colour", () => {
    expect(new Set(BUCKET_COLORS).size).toBe(BUCKET_COUNT);
    for (const c of BUCKET_COLORS) expect(c).toMatch(/^#[0-9a-f]{6}$/i);
  });

  it("scales the outline with the requested size", () => {
    expect(outlineScale(64)).toBe(1);
    expect(outlineScale(128)).toBe(2);
    expect(outlineScale(32)).toBe(0.5);
  });
});

describe("icon-image expression", () => {
  const names = () => JSON.stringify(matchExpression());

  it("selects an image per bucket", () => {
    expect(matchExpression()[0]).toBe("case");
  });

  it("makes every bucket reachable", () => {
    const s = names();
    for (const n of flameImageNames()) expect(s).toContain(n);
  });

  it("defaults to the coolest flame, never the hottest", () => {
    // A detection with no frpBucket must not render as the most intense fire.
    const e = matchExpression();
    const inner = e[3] as unknown[];
    expect(inner[0]).toBe("match");
    expect(inner[inner.length - 1]).toBe("flame-0");
    expect(e[e.length - 1]).not.toBe(`flame-${BUCKET_COUNT - 1}`);
  });

  it("routes the top bucket to the hottest flame", () => {
    const e = matchExpression();
    expect(e[2]).toBe(`flame-${BUCKET_COUNT - 1}`);
    expect(JSON.stringify(e[1])).toContain(String(BUCKET_COUNT - 1));
  });
});