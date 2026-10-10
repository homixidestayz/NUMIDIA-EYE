import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { anchorOf, exteriorRing, wilayaCode } from "./geo";
import type { WilayaCollection, WorldCollection } from "./types";

const COLLECTION: WilayaCollection = JSON.parse(
  readFileSync(resolve(__dirname, "../public/wilayas.geojson"), "utf8"),
) as WilayaCollection;

const feats = COLLECTION.features;

describe("world outline layer", () => {
  const world = JSON.parse(
    readFileSync(resolve(__dirname, "../public/world.geojson"), "utf8"),
  ) as WorldCollection;

  it("carries a usable set of country polygons", () => {
    expect(world.type).toBe("FeatureCollection");
    expect(world.features.length).toBeGreaterThan(150);
  });

  it("includes Algeria, so the focused view has neighbours behind it", () => {
    const algeria = world.features.filter(
      (f) => f.properties.ADMIN === "Algeria" || f.properties.NAME === "Algeria",
    );
    expect(algeria).toHaveLength(1);
    expect(["Polygon", "MultiPolygon"]).toContain(algeria[0].geometry.type);
  });

  it("spans the globe rather than only the Algerian neighbourhood", () => {
    let minLon = 180;
    let maxLon = -180;
    for (const f of world.features) {
      const polys = f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates;
      for (const poly of polys) {
        for (const pt of poly[0] ?? []) {
          const lon = pt[0];
          if (!Number.isFinite(lon)) continue;
          if (lon < minLon) minLon = lon;
          if (lon > maxLon) maxLon = lon;
        }
      }
    }
    expect(minLon).toBeLessThan(-140);
    expect(maxLon).toBeGreaterThan(150);
  });

  it("uses only Polygon/MultiPolygon, which is all the layer supports", () => {
    const kinds = new Set(world.features.map((f) => f.geometry.type));
    for (const k of kinds) expect(["Polygon", "MultiPolygon"]).toContain(k);
  });
});

describe("wilaya boundary set", () => {
  it("carries all 69 wilayas", () => {
    expect(feats).toHaveLength(69);
  });

  it("has no empty shapeName", () => {
    const blank = feats.filter(
      (f) => !f.properties.shapeName || !f.properties.shapeName.trim(),
    );
    expect(blank.map((f) => f.properties.shapeISO)).toEqual([]);
  });

  it("includes exactly one MultiPolygon, Alger", () => {
    const multi = feats.filter((f) => f.geometry.type === "MultiPolygon");
    expect(multi).toHaveLength(1);
    expect(multi[0].properties.shapeISO).toBe("DZ-16");
  });

  it("gives every wilaya a usable anchor, MultiPolygon included", () => {
    // The regression: exteriorRing() used to return coordinates[0] blindly,
    // which for the one MultiPolygon is a ring-of-ring and threw. buildWilaya
    // markers then aborted partway and silently drew only 15 of 69 labels.
    const missing = feats
      .filter((f) => {
        const a = anchorOf(f.geometry);
        return !a || !Number.isFinite(a[0]) || !Number.isFinite(a[1]);
      })
      .map((f) => f.properties.shapeISO);
    expect(missing).toEqual([]);
    expect(feats.filter((f) => anchorOf(f.geometry) !== null)).toHaveLength(69);
  });

  it("places Alger's anchor inside Algeria, not at the null island", () => {
    const alger = feats.find((f) => f.properties.shapeISO === "DZ-16")!;
    const a = anchorOf(alger.geometry);
    expect(a).not.toBeNull();
    // Algeria spans roughly 19W..12E, 18N..38N.
    expect(a![0]).toBeGreaterThan(-20);
    expect(a![0]).toBeLessThan(13);
    expect(a![1]).toBeGreaterThan(18);
    expect(a![1]).toBeLessThan(39);
  });

  it("returns an empty ring rather than throwing on a degenerate geometry", () => {
    expect(exteriorRing({ type: "Polygon", coordinates: [] })).toEqual([]);
    expect(
      exteriorRing({ type: "MultiPolygon", coordinates: [] }),
    ).toEqual([]);
  });

  it("yields two-digit codes matching the API's wilaya_code format", () => {
    // /detections returns wilaya_code as zero-padded strings such as "03".
    // If these ever diverge, every wilaya filter silently matches nothing.
    for (const f of feats) {
      expect(wilayaCode(f)).toMatch(/^\d{2}$/);
    }
    expect(wilayaCode(feats.find((f) => f.properties.shapeISO === "DZ-16")!)).toBe("16");
  });

  it("has unique codes and unique names", () => {
    const codes = feats.map(wilayaCode);
    expect(new Set(codes).size).toBe(69);
    const names = feats.map((f) => f.properties.shapeName.toLowerCase());
    expect(new Set(names).size).toBe(69);
  });

  it("resolves every wilaya name back to its own code", () => {
    // /incidents returns wilaya NAMES ("Laghouat"), not codes. This is the
    // lookup that turns one into the other; if it is not total, selecting an
    // incident frames nothing at all.
    for (const f of feats) {
      const name = f.properties.shapeName;
      const hit = feats.find(
        (x) => x.properties.shapeName.toLowerCase() === name.trim().toLowerCase(),
      );
      expect(hit, name).toBeDefined();
      expect(wilayaCode(hit!), name).toBe(wilayaCode(f));
    }
  });

  it("keeps accented names intact so labels do not render as question marks", () => {
    const bejaia = feats.find((f) => f.properties.shapeISO === "DZ-06")!;
    expect(bejaia.properties.shapeName).toBe("Béjaïa");
    expect(bejaia.properties.shapeName).not.toContain("?");
    expect(bejaia.properties.shapeNameAr).not.toContain("?");
    const anyQuestion = feats.filter(
      (f) => f.properties.shapeName.includes("?") || f.properties.shapeNameAr.includes("?"),
    );
    expect(anyQuestion).toHaveLength(0);
  });
});