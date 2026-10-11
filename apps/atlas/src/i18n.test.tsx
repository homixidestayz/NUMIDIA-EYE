import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { I18nProvider, dict } from "./i18n";

import status from "./__fixtures__/status.json";
import detections from "./__fixtures__/detections.json";
import incidentsEnvelope from "./__fixtures__/incidents.json";
import environment from "./__fixtures__/environment.json";

/* Minimal map stub. These assertions are about text, so the style "load" event
   never fires and no layer is ever painted. */
vi.mock("maplibre-gl", () => {
  class Ctrl {
    onAdd() {
      return null;
    }
  }
  class FakeMap {
    constructor(public opts: Record<string, unknown>) {}
    addControl() {}
    on() {}
    off() {}
    addSource() {}
    addImage() {}
    addLayer() {}
    getSource() {
      return { setData() {} };
    }
    getLayer() {
      return {};
    }
    setLayoutProperty() {}
    setFilter() {}
    fitBounds() {}
    easeTo() {}
    resize() {}
    getZoom() {
      return 4;
    }
    queryRenderedFeatures() {
      return [];
    }
    remove() {}
    getCanvas() {
      return { style: {} };
    }
  }
  class FakeMarker {
    setLngLat() {
      return this;
    }
    addTo() {
      return this;
    }
    remove() {}
  }
  return {
    default: { Map: FakeMap, NavigationControl: Ctrl, ScaleControl: Ctrl, Marker: FakeMarker },
    Map: FakeMap,
    NavigationControl: Ctrl,
    ScaleControl: Ctrl,
    Marker: FakeMarker,
  };
});

import App from "./App";
import Header from "./components/Header";

const wilayas = JSON.parse(
  readFileSync(resolve(__dirname, "../public/wilayas.geojson"), "utf8"),
);

const json = (b: unknown) =>
  new Response(JSON.stringify(b), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

beforeEach(() => {
  localStorage.clear();
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const u = String(input);
    if (/\/system\/status/.test(u)) return json(status);
    if (/\/detections\?/.test(u)) return json(detections);
    if (/\/incidents\?/.test(u)) return json(incidentsEnvelope);
    if (/\/incidents\/[^/]+\/environment/.test(u)) return json(environment);
    if (/wilayas\.geojson/.test(u)) return json(wilayas);
    return new Response("not found", { status: 404 });
  }) as unknown as typeof fetch;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

/* Every user-facing English string the brief lists. None may survive in Arabic. */
const ENGLISH_UI = [
  "Unavailable",
  "Loading",
  "Layers",
  "Fire detections",
  "Wilaya boundaries",
  "Wilaya labels",
  "Incidents & priority",
  "Rule-based priority",
  "Not confirmed wildfires",
  "Grouping incidents",
  "Grouping status",
  "Priority — rule-based",
  "Verification state",
  "Evaluated",
  "Coordinates",
  "Acquired",
  "Brightness",
  "FIRMS confidence",
  "Calibrated",
  "Threshold",
  "Environment at incident",
  "Refresh environment",
  "Run AI verification",
  "Not calibrated",
  "Soil moisture",
  "Drying",
  "Shallow fuel",
  "Replay",
  "Stop",
  "on map",
  "in range",
  " shown",
  " loaded",
  "Move window",
  "Pan the time",
  "Time range",
  "Not a fire-spread model",
  "not a forecast",
  "Fire Radiative Power",
  "Historical observation",
  "Independent research prototype",
  "Jump to a wilaya",
  "Cannot reach the API",
  "Wildfire intelligence",
  "Close detail panel",
  "No detections in view",
  "priority-v1 is deterministic",
  "The arrow points",
  "Cluster spread",
  "No wilaya matches",
  "Data attribution",
  "World outlines",
  "Map renderer",
  "Incidents at incident",
  "features drawn",
  "Map unavailable",
];

/** Strings the API itself returns are English by design; strip them before
 *  scanning, or every one of them reads as a leaked UI string. */
function apiStrings(): string[] {
  const out: string[] = [];
  const walk = (v: unknown) => {
    if (typeof v === "string") {
      if (v.length >= 8) out.push(v);
    } else if (Array.isArray(v)) v.forEach(walk);
    else if (v && typeof v === "object") Object.values(v).forEach(walk);
  };
  [status, incidentsEnvelope, environment].forEach(walk);
  return out.sort((a, b) => b.length - a.length);
}

/** Visible text plus the attributes a reader or a screen reader encounters. */
function surface(): string {
  let text = document.body.textContent ?? "";
  document.body.querySelectorAll("[aria-label],[title],[placeholder]").forEach((el) => {
    if (el.closest("svg")) return;
    for (const a of ["aria-label", "title", "placeholder"]) {
      const v = el.getAttribute(a);
      if (v) text += ` ${v}`;
    }
  });
  for (const s of apiStrings()) text = text.split(s).join(" ");
  return text;
}

async function arabicApp() {
  localStorage.setItem("numidia-lang", "ar");
  render(
    <I18nProvider>
      <App />
    </I18nProvider>,
  );
  await waitFor(() => expect(screen.getAllByText(dict.ar.incidents).length).toBeGreaterThan(0));
  await waitFor(() => expect(document.querySelector(".inc")).toBeTruthy());
  fireEvent.click(document.querySelector(".inc")!);
  await waitFor(() => expect(screen.getByText(dict.ar.groupingStatus)).toBeTruthy());
}

describe("dictionary", () => {
  it("has an Arabic string for every English key, none empty", () => {
    const en = Object.keys(dict.en).sort();
    expect(Object.keys(dict.ar).sort()).toEqual(en);
    for (const k of en) expect((dict.ar as Record<string, string>)[k].trim(), k).not.toBe("");
  });

  it("keeps the three-way distinction between unavailable, loading and none", () => {
    // "Unavailable" means the upstream declined. It must not collapse into the
    // word for "nothing" or for "still loading".
    expect(dict.ar.unavailable).not.toBe(dict.ar.noneWord);
    expect(dict.ar.unavailable).not.toBe(dict.ar.loading);
    expect(dict.ar.noneWord).not.toBe(dict.ar.loading);
  });

  it("keeps the disclaimers intact in Arabic, not softened", () => {
    expect(dict.ar.tlFoot).toContain("ليست نموذج انتشار حرائق");
    expect(dict.ar.incidentsLede).toContain("ليست حرائق مؤكدة");
    expect(dict.ar.notCalibrated).toContain("ليست احتمالاً فعلياً");
    expect(dict.ar.indep).toContain("ليس نموذج انتشار حرائق");
  });
});

describe("full app in Arabic", () => {
  it("shows none of the English user-facing strings", async () => {
    await arabicApp();
    const seen = surface();
    const leaked = ENGLISH_UI.filter((s) => seen.includes(s));
    expect(leaked, `English left in Arabic mode: ${leaked.join(" | ")}`).toEqual([]);
  });

  it("puts dir=rtl on text panels and never on the map, timeline or <html>", async () => {
    await arabicApp();
    for (const sel of [".topbar", "aside.left", "aside.right", ".foot"]) {
      expect(document.querySelector(sel)?.getAttribute("dir"), sel).toBe("rtl");
    }
    // A global flip would reverse the map and the time axis.
    expect(document.documentElement.getAttribute("dir")).not.toBe("rtl");
    expect(document.documentElement.lang).toBe("ar");
    for (const sel of [".stage", ".tl"]) {
      const el = document.querySelector(sel)!;
      expect(el, sel).toBeTruthy();
      expect(el.closest('[dir="rtl"]'), `${sel} must not sit inside RTL`).toBeNull();
    }
  });

  it("keeps API data exactly as returned", async () => {
    await arabicApp();
    const inc = incidentsEnvelope.incidents[0];
    const body = document.body.textContent ?? "";
    expect(body).toContain(inc.priority.level);
    expect(body).toContain(inc.priority.score.toFixed(4));
    expect(body).toContain(inc.priority.factors[0].evidence);
    expect(body).toContain(inc.verification.message);
  });
});

describe("attribution row", () => {
  it("separates the label from the legal detail", async () => {
    // These two ran together as "رصد الحرائقNASA FIRMS / VIIRS": JSX drops
    // whitespace-with-newline between adjacent elements, and nothing in the
    // markup separated them.
    await arabicApp();
    for (const span of document.querySelectorAll(".attrib > span:not(.indep)")) {
      const kids = [...span.children].map((c) => c.tagName);
      const label = span.textContent ?? "";
      expect(kids, label).toContain("B");
      expect(kids, label).toContain("I");
      expect(kids, label).toContain("SPAN");
    }
  });

  it("keeps the legal detail LTR but lets the row follow the page direction", async () => {
    // Forcing dir="ltr" on the whole credit reordered the Arabic label and
    // pinned the row the wrong way.
    await arabicApp();
    expect(document.querySelector(".attrib")?.getAttribute("dir")).toBe("rtl");
    for (const span of document.querySelectorAll(".attrib > span:not(.indep)")) {
      expect(span.getAttribute("dir"), span.textContent ?? "").toBeNull();
      const detail = span.querySelector("span");
      expect(detail?.getAttribute("lang"), "licence text stays English").toBe("en");
      expect(detail?.getAttribute("dir"), "licence text stays LTR").toBe("ltr");
    }
  });
});

describe("language switch is lossless", () => {
  it("restores the exact English text after Arabic and back", async () => {
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    await waitFor(() => expect(document.querySelector(".inc")).toBeTruthy());
    fireEvent.click(document.querySelector(".inc")!);
    await waitFor(() => expect(screen.getByText("Grouping status")).toBeTruthy());
    const before = document.body.textContent;

    fireEvent.click(screen.getByRole("button", { name: dict.en.langLabel }));
    await waitFor(() => expect(screen.getByText(dict.ar.groupingStatus)).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: dict.ar.langLabel }));
    await waitFor(() => expect(document.body.textContent).toBe(before));
    expect(document.documentElement.lang).toBe("en");
  });
});

describe("header toggle", () => {
  it("switches language and back", () => {
    render(
      <I18nProvider>
        <Header
          status={null}
          loading={false}
          liveCount={3}
          total={10}
          onSearch={() => {}}
          onToggleLeft={() => {}}
          onToggleRight={() => {}}
          leftOpen={false}
          rightOpen={false}
        />
      </I18nProvider>,
    );
    expect(screen.getByText(dict.en.tagline)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: dict.en.langLabel }));
    expect(screen.getByText(dict.ar.layers)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: dict.ar.langLabel }));
    expect(screen.getByText(dict.en.tagline)).toBeTruthy();
  });
});