import { connect, evaluate, goto, shot, sleep } from "./cdp.mjs";

const URL_APP = "http://localhost:5600/?api=8010";
const OUT = "C:/Users/Admin/AppData/Local/Temp/opencode/shots";
import { mkdirSync } from "node:fs";
mkdirSync(OUT, { recursive: true });

const api = await connect();
const problems = [];
const consoleErrors = [];

api.on((m) => {
  if (m.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(m.params.type)) {
    consoleErrors.push(
      `[${m.params.type}] ` + m.params.args.map((a) => a.value ?? a.description ?? a.type).join(" "),
    );
  }
  if (m.method === "Runtime.exceptionThrown") {
    consoleErrors.push("[exception] " + (m.params.exceptionDetails?.exception?.description ?? m.params.exceptionDetails?.text));
  }
  if (m.method === "Log.entryAdded" && m.params.entry.level === "error") {
    consoleErrors.push("[log] " + m.params.entry.text);
  }
});

/* ── English ─────────────────────────────────────────────────────────── */
await goto(api, URL_APP, { settle: 1200 });

/* Wait on real conditions, never on a fixed sleep. Sampling early is how a
 * check ends up passing while measuring nothing. */
async function waitFor(expr, label, tries = 80) {
  for (let i = 0; i < tries; i++) {
    const v = await evaluate(api, expr);
    if (v) return v;
    await sleep(500);
  }
  throw new Error(`timed out waiting for ${label}`);
}

const painted = await waitFor(
  `(() => { const t = document.querySelector('.mapstat')?.textContent ?? ''; return /\\d+ (features|عنصراً)/.test(t) ? t : false; })()`,
  "map to paint features",
);

// The incidents list comes from a slow endpoint; wait for a row, not a timer.
await waitFor(`!!document.querySelector('.inc')`, "an incident row to render");

const en = await evaluate(api, `(() => {
  const g = (s) => document.querySelector(s);
  const cs = (s, p) => { const e = g(s); return e ? getComputedStyle(e)[p] : null; };
  return {
    lang: document.documentElement.lang,
    htmlDir: document.documentElement.getAttribute('dir'),
    topbarDir: g('.topbar')?.getAttribute('dir') ?? null,
    leftDir: g('aside.left')?.getAttribute('dir') ?? null,
    rightDir: g('aside.right')?.getAttribute('dir') ?? null,
    tlInsideRtl: !!g('.tl')?.closest('[dir="rtl"]'),
    stageInsideRtl: !!g('.stage')?.closest('[dir="rtl"]'),
    topbarFont: cs('.topbar', 'fontFamily'),
    topbarBorderImage: cs('.topbar', 'borderImageSource'),
    markSvg: !!g('.mark')?.querySelector('path'),
    langBtn: g('.lang-btn')?.textContent?.trim() ?? null,
    flameIcons: document.querySelectorAll('canvas').length,
  };
})()`);

await shot(api, `${OUT}/01-en.png`);

/* ── Switch to Arabic via the real button ────────────────────────────── */
await evaluate(api, `document.querySelector('.lang-btn').click()`);
await sleep(900);

const ar = await evaluate(api, `(() => {
  const g = (s) => document.querySelector(s);
  const cs = (s, p) => { const e = g(s); return e ? getComputedStyle(e)[p] : null; };
  const heads = [...document.querySelectorAll('.group-h, h2, h3')].slice(0, 8).map(e => e.textContent.trim());
  return {
    lang: document.documentElement.lang,
    htmlDir: document.documentElement.getAttribute('dir'),
    topbarDir: g('.topbar')?.getAttribute('dir') ?? null,
    leftDir: g('aside.left')?.getAttribute('dir') ?? null,
    rightDir: g('aside.right')?.getAttribute('dir') ?? null,
    tlInsideRtl: !!g('.tl')?.closest('[dir="rtl"]'),
    stageInsideRtl: !!g('.stage')?.closest('[dir="rtl"]'),
    leftTextAlign: cs('aside.left', 'textAlign'),
    topbarFont: cs('.topbar', 'fontFamily'),
    // does the Arabic face actually resolve, or is it falling back?
    arabicFontLoaded: document.fonts.check('16px "IBM Plex Sans Arabic"'),
    plusJakartaLoaded: document.fonts.check('16px "Plus Jakarta Sans"'),
    tagline: g('.brandtext p')?.textContent?.trim() ?? null,
    heads,
    langBtn: g('.lang-btn')?.textContent?.trim() ?? null,
    tlFoot: g('.tl-foot')?.textContent?.trim() ?? null,
  };
})()`);

await shot(api, `${OUT}/02-ar.png`);

/* ── Overflow check: does Arabic text spill or clip? ─────────────────── */
// Measure every panel against its own scroll width.
const overflow = await evaluate(api, `(() => {
  const bad = [];
  document.querySelectorAll('.topbar, aside.left, aside.right, .foot, .attrib, .tl, .legend, .search-box').forEach((el) => {
    if (el.scrollWidth > el.clientWidth + 2) {
      bad.push({ sel: el.className, scrollW: el.scrollWidth, clientW: el.clientWidth });
    }
  });
  // Any element whose text is visually clipped by an ancestor.
  const clipped = [];
  document.querySelectorAll('.topbar *, aside.left *, aside.right *').forEach((el) => {
    if (el.children.length === 0 && el.textContent.trim() && el.scrollWidth > el.clientWidth + 2) {
      clipped.push({ txt: el.textContent.trim().slice(0, 40), cls: el.className });
    }
  });
  return { bad, clipped: clipped.slice(0, 12) };
})()`);

/* ── Open an incident so the detail panel is exercised in Arabic ─────── */
await waitFor(`!!document.querySelector('.inc')`, "an incident row (AR)");
await evaluate(api, `document.querySelector('.inc').click()`);
await waitFor(`!!document.querySelector('.right h3')`, "the detail panel headings");
await waitFor(
  `document.body.textContent.includes('حالة التجميع')`,
  "the grouping section in Arabic",
);
const arDetail = await evaluate(api, `(() => {
  const g = (s) => document.querySelector(s);
  return {
    hasGrouping: document.body.textContent.includes('حالة التجميع'),
    envTitle: !!g('.right h3'),
    headings: [...document.querySelectorAll('.right h3')].map(e => e.textContent.trim()),
    notes: [...document.querySelectorAll('.right .note')].slice(0, 4).map(e => e.textContent.trim().slice(0, 90)),
  };
})()`);
await shot(api, `${OUT}/03-ar-detail.png`);

/* ── Search modal in Arabic ──────────────────────────────────────────── */
await evaluate(api, `window.dispatchEvent(new KeyboardEvent('keydown', {key:'k', ctrlKey:true, bubbles:true}))`);
await sleep(800);
const arSearch = await evaluate(api, `(() => {
  const el = document.querySelector('.search-box');
  const inp = document.querySelector('.search-box input');
  if (inp) { inp.focus(); }
  return {
    open: !!el,
    dir: el?.getAttribute('dir') ?? null,
    placeholder: inp?.getAttribute('placeholder') ?? null,
  };
})()`);
await evaluate(api, `(() => { const i=document.querySelector('.search-box input'); if(!i) return;
  // React tracks the value on the element instance, so assigning .value
  // directly is invisible to onChange. Go through the native setter.
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  setter.call(i, 'البليدة');
  i.dispatchEvent(new Event('input', { bubbles: true }));
})()`);
await sleep(900);
const arSearchQuery = await evaluate(api, `(() => ({
  rows: [...document.querySelectorAll('.search-item')].map(r => r.querySelector('.nm')?.textContent.trim()),
  arNames: [...document.querySelectorAll('.search-item .nm-ar')].map(r => r.textContent.trim()),
}))()`);
await shot(api, `${OUT}/04-ar-search.png`);

console.log(JSON.stringify({
  en, ar, overflow, arDetail, arSearch: arSearchQuery,
  painted,
  consoleErrors: consoleErrors.slice(0, 25),
}, null, 2));

api.close();