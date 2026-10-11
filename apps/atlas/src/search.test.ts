import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { WilayaCollection } from "./types";
import { normalise } from "./components/SearchModal";
import { wilayaCode } from "./geo";

const wilayas = JSON.parse(
  readFileSync(resolve(__dirname, "../public/wilayas.geojson"), "utf8"),
) as WilayaCollection;

const names = new Map(
  wilayas.features.map((f) => [f.properties.shapeName, f.properties.shapeNameAr]),
);

/* The same predicate the modal uses, run against the real dataset. The code
 * branch matters: codes are zero-padded, so "9" must reach DZ-09. A helper that
 * quietly drops it measures a weaker thing than the app does. */
function search(raw: string): string[] {
  const trimmed = raw.trim();
  const needle = normalise(trimmed);
  if (!needle) return [];
  return wilayas.features
    .filter((f) => {
      const n = normalise(f.properties.shapeName);
      const a = normalise(f.properties.shapeNameAr);
      const codeHit =
        /^\d{1,2}$/.test(trimmed) && wilayaCode(f) === trimmed.padStart(2, "0");
      return codeHit || n === needle || n.includes(needle) || a === needle || a.includes(needle);
    })
    .map((f) => f.properties.shapeName);
}

describe("query folding keeps both scripts", () => {
  it("does not fold an Arabic query to the empty string", () => {
    // This was the bug: every non-[a-z0-9] character was dropped, an Arabic
    // query became "", and the modal silently fell through to "show all 69".
    expect(normalise("البليدة")).not.toBe("");
    expect(normalise("تيميمون")).not.toBe("");
  });

  it("still folds Latin accents, articles and punctuation", () => {
    expect(normalise("Béjaïa")).toBe(normalise("bejaia"));
    expect(normalise("Wilaya of Bejaia")).toBe(normalise("bejaia"));
    expect(normalise("El Oued")).toBe("oued");
  });

  it("folds Arabic letter variants a typist will not distinguish", () => {
    expect(normalise("الجزاير")).toBe(normalise("الجزائر"));
    expect(normalise("ورقلة")).toBe(normalise("ورقله"));
    // Tashkeel must not stop a match.
    expect(normalise("قسنديضة")).toBe(normalise("قسنديضة"));
  });
});

describe("searching the real 69 wilayas", () => {
  it("finds the three wilayas the Arabic placeholder advertises", () => {
    // The Arabic placeholder literally reads "جرّب البليدة أو تيميمون أو 9".
    // If any of these misses, the placeholder is advertising a search that
    // does not work.
    expect(search("البليدة")).toContain("Blida");
    expect(search("تيميمون")).toContain("Timimoun");
    expect(search("9")).toContain("Blida"); // DZ-09
  });

  it("accepts a partial Arabic query", () => {
    expect(search("بل")).toContain("Blida");
    expect(search("خنشلة")).toEqual(["Khenchela"]);
  });

  it("accepts a partial Latin query", () => {
    expect(search("beja")).toContain("Béjaïa");
    expect(search("Timim")).toContain("Timimoun");
  });

  it("every wilaya carries a real Arabic name, so no query is a dead end", () => {
    for (const [latin, arabic] of names) {
      expect(arabic, `${latin} has no Arabic name at all`).toBeTruthy();
      expect(/[\u0600-\u06FF]/.test(arabic), `${latin} has a non-Arabic name`).toBe(true);
      // The Arabic name must be findable by its own first characters.
      expect(search(arabic).length, `searching "${arabic}" found nothing`).toBeGreaterThan(0);
    }
  });

  it("returns nothing for a query that matches no wilaya", () => {
    expect(search("zzzznotawilaya")).toEqual([]);
  });
});