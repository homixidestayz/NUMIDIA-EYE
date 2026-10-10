import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { BUCKET_COUNT, bucketFor } from "./fire";

import status from "./__fixtures__/status.json";
import detections from "./__fixtures__/detections.json";
import incidentsEnvelope from "./__fixtures__/incidents.json";
import environment from "./__fixtures__/environment.json";

const wilayas = JSON.parse(
  readFileSync(resolve(__dirname, "../public/wilayas.geojson"), "utf8"),
);

/* MapLibre needs WebGL, which jsdom does not provide. Stub the surface the
   component actually touches so the render path is exercised rather than
   short-circuited, and record every setData call so tests can assert on what
   actually reached the map. */
export const setDataCalls: Record<string, unknown>[] = [];
(globalThis as unknown as { __setDataCalls: unknown[] }).__setDataCalls = setDataCalls;

vi.mock("maplibre-gl", () => {
  class Ctrl {
    constructor(_opts?: unknown) {}
    onAdd() {
      return null;
    }
  }
  class FakeMap {
    private handlers: Record<string, ((e: unknown) => void)[]> = {};
    private removed = false;
    constructor(public opts: Record<string, unknown>) {
      // The real map fires "load" asynchronously once the style resolves, and
      // the component only adds sources inside that handler. Without this the
      // stub silently records no data at all.
      setTimeout(() => {
        if (this.removed) return;
        try {
          this.fire("load");
        } catch {
          /* a stub gap must not fail an unrelated assertion */
        }
      }, 0);
    }
    fire(key: string) {
      if (this.removed) return;
      for (const fn of [...(this.handlers[key] ?? [])]) fn({ features: [] });
    }
    addControl() {}
    on(evt: string, layerOrFn: unknown, maybeFn?: unknown) {
      const fn = (typeof layerOrFn === "function" ? layerOrFn : maybeFn) as
        | ((e: unknown) => void)
        | undefined;
      const key = typeof layerOrFn === "function" ? evt : `${evt}:${String(layerOrFn)}`;
      if (fn) (this.handlers[key] ??= []).push(fn);
    }
    addSource(id: string, spec: Record<string, unknown>) {
      this.sources[id] = spec;
      this.sourceIds.push(id);
    }
    addImage() {}
    addLayer() {}
    off(evt: string, _fn?: unknown) {
      void evt;
    }
    sourceIds: string[] = [];
    sources: Record<string, Record<string, unknown>> = {};
    getSource(id: string) {
      return {
        setData: (d: unknown) => {
          const call = { id, data: d };
          setDataCalls.push(call);
        },
      };
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
    remove() {
      this.removed = true;
    }
    getCanvas() {
      return { style: {} };
    }
  }
  class FakeMarker {
    constructor(public opts: Record<string, unknown>) {}
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

const asked: string[] = [];

function installFetch(overrides: Record<string, unknown> = {}): typeof fetch {
  const handlers: [RegExp, () => Response][] = [
    [/\/system\/status/, () => json(status)],
    [/\/detections\?/, () => json(detections)],
    [/\/incidents\?/, () => json(incidentsEnvelope)],
    [/\/incidents\/[^/]+\/environment/, () => json(environment)],
    [/\/wilayas\.geojson/, () => json(wilayas)],
  ];
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    asked.push(url);
    // Overrides are keyed by path so a test does not have to know the API
    // origin. Matching on the raw absolute URL silently never matched, and the
    // "upstream fails" case quietly rendered a healthy panel instead.
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    if (path in overrides) return json(overrides[path]);
    for (const [re, make] of handlers) {
      if (re.test(url)) return make();
    }
    return new Response("not found", { status: 404 });
  }) as unknown as typeof fetch;
  return globalThis.fetch;
}

/** Selects the first incident in the list and waits for its panel. */
async function selectFirstIncident() {
  await waitFor(() => expect(screen.getAllByText(/Incidents & priority/).length).toBeGreaterThan(0));
  const target = incidentsEnvelope.incidents[0];
  const node = screen.getAllByText(`${target.detection_count} detections`)[0];
  fireEvent.click(node.closest("button")!);
  await waitFor(() =>
    expect(screen.getAllByText(`${target.detection_count} detections`).length).toBeGreaterThan(0),
  );
  return target;
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  asked.length = 0;
  setDataCalls.length = 0;
  installFetch();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("no clustering: one mark per detection", () => {
  interface Pushed {
    id: string;
    data: { features: { geometry: { type: string }; properties: Record<string, unknown> }[] };
  }

  const detPush = async (): Promise<Pushed> => {
    // The stub fires "load" on a timer, so the header can render before the map
    // has pushed anything. Waiting on the header made these tests flaky.
    await waitFor(() =>
      expect(setDataCalls.some((x) => x.id === "detections")).toBe(true),
    );
    const c = [...setDataCalls].reverse().find((x) => x.id === "detections");
    if (!c) throw new Error("detections source never received data");
    return c as unknown as Pushed;
  };

  it("pushes exactly one point feature per detection, with no aggregate clusters", async () => {
    render(<App />);
    const p = await detPush();
    expect(p.data.features).toHaveLength(detections.length);
    for (const f of p.data.features) expect(f.geometry.type).toBe("Point");
    // The fingerprint of a clustered source: a point_count property.
    for (const f of p.data.features) {
      expect(f.properties).not.toHaveProperty("point_count");
      expect(f.properties).not.toHaveProperty("cluster_id");
    }
  });

  it("gives every detection an FRP bucket within the ramp", async () => {
    render(<App />);
    for (const f of (await detPush()).data.features) {
      const b = f.properties.frpBucket as number;
      expect(Number.isInteger(b)).toBe(true);
      expect(b).toBeGreaterThanOrEqual(0);
      expect(b).toBeLessThan(BUCKET_COUNT);
    }
  });

  it("carries the real FRP alongside the bucket, never a substituted number", async () => {
    render(<App />);
    const feats = (await detPush()).data.features;
    const withFrp = (detections as { frp: number | null }[]).filter(
      (d) => typeof d.frp === "number",
    );
    expect(withFrp.length).toBeGreaterThan(0);
    for (let i = 0; i < feats.length; i++) {
      const frp = withFrp[i]?.frp;
      if (typeof frp === "number") {
        expect(feats[i].properties.frp).toBeCloseTo(frp, 5);
        expect(feats[i].properties.frpBucket).toBe(bucketFor(frp));
      }
    }
  });

  it("keeps 69 wilaya boundaries on their own source", async () => {
    render(<App />);
    await detPush();
    await waitFor(() => expect(setDataCalls.some((x) => x.id === "wilayas")).toBe(true));
    const w = [...setDataCalls].reverse().find((x) => x.id === "wilayas");
    expect(w).toBeDefined();
    expect((w as unknown as Pushed).data.features).toHaveLength(69);
  });
});

describe("App against real API payloads", () => {
  it("renders without throwing and reports the live FIRMS state", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("CONNECTED")).toBeDefined());
    expect(screen.getByText(/NUMIDIA EYE/)).toBeDefined();
    expect(screen.getAllByText("verifier-v2").length).toBeGreaterThan(0);
    expect(status.detections_count).toBeGreaterThan(0);
  });

  it("lists incidents from the envelope, not from a bare array", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Incidents & priority/)).toBeDefined());
    for (const inc of incidentsEnvelope.incidents.slice(0, 5)) {
      expect(screen.getAllByText(`${inc.detection_count} detections`).length).toBeGreaterThan(0);
    }
  });

  it("asks the environment endpoint with an incident id, never a wilaya code", async () => {
    // The bug this guards: /incidents returns wilaya NAMES, the map is keyed by
    // code. Passing a name where an id is expected returns 404 and the panel
    // silently loses all environmental context.
    render(<App />);
    const target = await selectFirstIncident();

    await waitFor(() =>
      expect(asked.some((u) => u.includes(`/incidents/${target.id}/environment`))).toBe(true),
    );
    const envCalls = asked.filter((u) => u.includes("/environment"));
    expect(envCalls[0]).toContain(target.id);
    for (const call of envCalls) {
      expect(call).not.toContain("/incidents/wilaya");
      // a wilaya name would appear verbatim in the path
      for (const w of target.wilayas) expect(call).not.toContain(w);
    }
  });

  it("renders environmental context with its stated provenance", async () => {
    render(<App />);
    await selectFirstIncident();
    await waitFor(() =>
      expect(screen.getAllByText(/Environment at incident/).length).toBeGreaterThan(0),
    );
    expect(screen.getByText(/open-meteo/)).toBeDefined();
    expect(screen.getAllByText(/Not a fire-spread model/i).length).toBeGreaterThan(0);
  });

  it("says UNAVAILABLE rather than inventing a reading when the upstream fails", async () => {
    installFetch({
      [`/incidents/${incidentsEnvelope.incidents[0].id}/environment`]: {
        ...environment,
        status: "UNAVAILABLE",
        reason: "upstream timeout",
        source: null,
        observed_at: null,
        wind_speed_10m_ms: null,
      },
    });
    render(<App />);
    await selectFirstIncident();
    await waitFor(() =>
      expect(screen.getAllByText(/Environmental context unavailable/).length).toBeGreaterThan(0),
    );
    expect(screen.getAllByText(/upstream timeout/).length).toBeGreaterThan(0);
    // A null wind must render as Unavailable, never as a bare 0.00 m/s.
    expect(screen.queryByText(/0\.00 m\/s/)).toBeNull();
  });

  it("surfaces the verifier's own scope statement instead of overclaiming", async () => {
    render(<App />);
    await selectFirstIncident();
    await waitFor(() =>
      expect(screen.getAllByText(/Verification state/).length).toBeGreaterThan(0),
    );
    expect(
      screen.getAllByText(/NOT a validated Algerian wildfire detector/).length,
    ).toBeGreaterThan(0);
  });

  it("opens search on Ctrl+K and filters to a wilaya by accent-insensitive name", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Ctrl K/)).toBeDefined());
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });

    const input = await screen.findByLabelText("Search wilayas");
    fireEvent.change(input, { target: { value: "bejaia" } });
    await waitFor(() => expect(screen.getAllByText("Béjaïa").length).toBeGreaterThan(0));
  });

  it("announces the wilaya filter instead of silently emptying the map", async () => {
    render(<App />);
    const target = await selectFirstIncident();
    // Focusing a wilaya filters detections to it; with no indicator the map
    // just goes quiet and reads as broken. The name sits in a <b>, so assert on
    // the button's full text rather than getByText's per-element match.
    await waitFor(() => expect(screen.getByText(/Filtered to/)).toBeDefined());
    const btn = screen.getByText(/Filtered to/).closest("button")!;
    expect(btn.textContent).toContain(target.wilayas[0]);

    fireEvent.click(btn);
    await waitFor(() => expect(screen.queryByText(/Filtered to/)).toBeNull());
  });

  it("says Loading, not Unavailable, while the request is still in flight", async () => {
    // Measured: /system/status 4.2s, /incidents 4.1s. Rendering "Unavailable"
    // during that window is a claim about the world, and this project's one
    // rule is that unavailable is only ever reported after a real failure.
    let open: () => void = () => {};
    const gate = new Promise<void>((res) => (open = res));
    const base = installFetch();
    const inner = base as unknown as (u: string) => Promise<Response>;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (/system\/status|detections\?|incidents\?|wilayas/.test(url)) await gate;
      return inner(url);
    }) as unknown as typeof fetch;

    render(<App />);
    // Synchronously after mount the batch cannot possibly have resolved.
    expect(screen.getAllByText(/Loading…/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Unavailable/)).toBeNull();
    expect(screen.getByText(/Grouping incidents/)).toBeDefined();

    open();
    await waitFor(() => expect(screen.getAllByText("CONNECTED").length).toBeGreaterThan(0));
    expect(screen.queryByText(/Loading…/)).toBeNull();
  });

  it("does not fire the batch twice under StrictMode", async () => {
    // One worker, 4-second endpoints: doubling the batch is what pushed first
    // paint past ten seconds.
    render(<App />);
    await waitFor(() => expect(screen.getAllByText("CONNECTED").length).toBeGreaterThan(0));
    const statusCalls = asked.filter((u) => u.includes("/system/status"));
    expect(statusCalls).toHaveLength(1);
  });

  it("reports a bad API instead of rendering an empty confident-looking map", async () => {
    globalThis.fetch = vi.fn(async () => new Response("nope", { status: 500 })) as never;
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Cannot reach the API/)).toBeDefined());
  });
});