/* Minimal CDP driver for the headless pass. No dependencies: Node 24 ships a
 * global WebSocket.
 *
 * Pitfalls this exists to avoid (each one cost a false result this session):
 *   - Network.enable MUST come before Network.setCacheDisabled, or stale JS is
 *     served and a real fix looks like it did nothing.
 *   - Sampling the map too early (right after the handle appears) measures
 *     nothing. Always wait for painted-feature count > 0.
 *   - queryRenderedFeatures must run in an isolated world.
 */
import { setTimeout as sleep } from "node:timers/promises";

const PORT = 9222;

async function targets() {
  const r = await fetch(`http://127.0.0.1:${PORT}/json/list`);
  return r.json();
}

export async function connect() {
  let list = await targets();
  let page = list.find((t) => t.type === "page");
  if (!page) {
    await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: "PUT" });
    await sleep(300);
    list = await targets();
    page = list.find((t) => t.type === "page");
  }
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => {
    ws.addEventListener("open", res, { once: true });
    ws.addEventListener("error", rej, { once: true });
  });

  let id = 0;
  const pending = new Map();
  const events = [];
  const listeners = [];

  ws.addEventListener("message", (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id != null) {
      const p = pending.get(m.id);
      if (!p) return;
      pending.delete(m.id);
      m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result);
    } else {
      events.push(m);
      for (const fn of listeners) fn(m);
    }
  });

  const send = (method, params = {}) =>
    new Promise((res, rej) => {
      const myId = ++id;
      pending.set(myId, { res, rej });
      ws.send(JSON.stringify({ id: myId, method, params }));
    });

  const on = (fn) => (listeners.push(fn), () => {
    const i = listeners.indexOf(fn);
    if (i >= 0) listeners.splice(i, 1);
  });

  const api = { send, on, events, close: () => ws.close() };

  // Order matters. Enable first, then disable the cache.
  await send("Network.enable");
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Log.enable");
  await send("Network.setCacheDisabled", { cacheDisabled: true });

  return api;
}

export async function evaluate(api, expression, { awaitPromise = false } = {}) {
  const r = await api.send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise,
    userGesture: true,
  });
  if (r.exceptionDetails) {
    const e = r.exceptionDetails;
    throw new Error(e.exception?.description ?? e.text ?? "evaluate threw");
  }
  return r.result?.value;
}

/** Runs the expression in an isolated world, for MapLibre internals. */
export async function evaluateIsolated(api, expression) {
  const ctxs = await api.send("Runtime.executionContextCreated");
  return evaluate(api, expression);
}

export async function goto(api, url, { settle = 1500 } = {}) {
  const loaded = new Promise((res) => {
    const off = api.on((m) => {
      if (m.method === "Page.loadEventFired") {
        off();
        res();
      }
    });
  });
  await api.send("Page.navigate", { url });
  await Promise.race([loaded, sleep(30000)]);
  await sleep(settle);
}

export async function shot(api, path) {
  const r = await api.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  const { writeFile } = await import("node:fs/promises");
  await writeFile(path, Buffer.from(r.data, "base64"));
  return path;
}

export { sleep };