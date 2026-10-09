/* Wind-bearing assertion, as a plain check rather than a comment.

   Meteorological convention: wind speed/direction is the direction wind comes
   FROM. A compass arrow on a hazard panel should show where it blows TO, because
   that is the direction a fire spreads and the direction someone should move away
   from. Getting this backwards would point an operator into the flame front.

   Run: node apps/site/site.test.js   (or via the repo test runner)
*/
const fs = require("fs");
const path = require("path");

let failures = 0;
function check(name, actual, expected) {
  const pass = JSON.stringify(actual) === JSON.stringify(expected);
  if (!pass) failures++;
  console.log(`  ${pass ? "PASS" : "FAIL"}  ${name}` +
    (pass ? "" : `\n         got ${JSON.stringify(actual)}, expected ${JSON.stringify(expected)}`));
}
/* Single-argument form for wiring checks. Without this, `expected` arrives as
   undefined and a passing comparison reads as a failure — which is how the first
   run of this file reported twelve bogus failures. */
function checkTrue(name, actual) {
  const pass = actual === true;
  if (!pass) failures++;
  console.log(`  ${pass ? "PASS" : "FAIL"}  ${name}`);
}

/* ---------------------------------------------------------------- bearing */
const windArrow = (b) => {
  const from = ((Number(b) % 360) + 360) % 360;
  const to = (from + 180) % 360;
  return { from, to, rotate: to };
};

console.log("wind bearing FROM -> TO");
check("from 0 (N) blows south",    windArrow(0).to, 180);
check("from 90 (E) blows west",    windArrow(90).to, 270);
check("from 180 (S) blows north",  windArrow(180).to, 0);
check("from 270 (W) blows east",   windArrow(270).to, 90);
/* 360 degrees IS 0, so its downwind is 180 - not 0. Asserting 0 here would have
   hidden the fact that the conversion is a true +180 and not a lookup table. */
check("360 == 0, so downwind is 180", windArrow(360).to, 180);
check("360 reports from 0, not 360",  windArrow(360).from, 0);
check("negative wraps to from 270",  windArrow(-90).from, 270);
check("negative -90 blows east",     windArrow(-90).to, 90);

/* ------------------------------------------------------------------- FRP */
function frpRadius(frp) {
  if (typeof frp !== "number" || !isFinite(frp) || frp < 0) return 4;
  if (frp < 10) return 4;
  if (frp < 100) return 6;
  if (frp < 500) return 9;
  return 13;
}
console.log("\nFRP -> radius");
check("unknown frp stays small",  frpRadius(undefined), 4);
check("null frp stays small",     frpRadius(null), 4);
check("negative frp stays small", frpRadius(-5), 4);
check("0 MW small",               frpRadius(0), 4);
check("9 MW small",               frpRadius(9), 4);
check("50 MW medium",             frpRadius(50), 6);
check("250 MW large",             frpRadius(250), 9);
check("1500 MW extreme",          frpRadius(1500), 13);
check("radius is monotonic", [5, 50, 250, 1500].map(frpRadius),
      [...[5, 50, 250, 1500].map(frpRadius)].sort((a, b) => a - b));

/* --------------------------------------------------------------- no zeros */
/* An unavailable environmental reading must never render as a plausible number.
   A wind speed of 0.0 reads as "perfectly still", which would silently defeat
   any downwind reasoning an operator does with it. */
function numOrUn(v, dp) {
  return typeof v === "number" && isFinite(v) ? v.toFixed(dp) : "Unavailable";
}
console.log("\nunavailable never renders as a number");
check("null wind",  numOrUn(null, 2), "Unavailable");
check("NaN wind",   numOrUn(NaN, 2), "Unavailable");
check("real wind",  numOrUn(1.83, 2), "1.83");
check("0 is real, not missing", numOrUn(0, 2), "0.00");

/* --------------------------------------------- dial renders its own state */
function dialSvg(deg, speed) {
  const { to } = windArrow(deg);
  const calm = !(typeof speed === "number" && speed > 0.05);
  const len = calm ? 6 : 12 + Math.min(20, (speed / 12) * 20);
  return `<svg class="dial" viewBox="0 0 64 64" role="img" aria-label="wind bearing ${Math.round(to)} degrees">
    <circle cx="32" cy="32" r="29" class="dial-ring"/>
    <text x="32" y="11" class="dial-n">N</text>
    <g transform="rotate(${to.toFixed(1)} 32 32)">
      <path d="M32 ${(32 - len).toFixed(1)} L${(32 + 5).toFixed(1)} 34 L32 ${(32 - len + 9).toFixed(1)} L${(32 - 5).toFixed(1)} 34 Z"
        class="${calm ? "dial-arrow calm" : "dial-arrow"}"/>
    </g>
  </svg>`;
}
console.log("\ndial");
const windy = dialSvg(270, 5);
check("windy dial is not calm", windy.includes("dial-arrow calm"), false);
check("calm dial is calm", dialSvg(90, 0).includes("dial-arrow calm"), true);
check("unknown speed renders calm, not NaN", dialSvg(90, undefined).includes("dial-arrow calm"), true);
check("dial carries a text alternative", dialSvg(270, 5).includes('aria-label="wind bearing 90 degrees"'), true);

/* ---------------------------------------------------- site.js wiring check */
/* ------------------------------------------------------ wilaya ISO codes */
const wilayaCodeFromIso = (v) => {
  if (v === null || v === undefined) return null;
  const s = String(v);
  const m = s.match(/(\d+)\s*$/);
  if (m) return m[1];
  return /^\d+$/.test(s) ? s : null;
};
console.log("\nwilaya ISO -> numeric code");
check("DZ-58 -> 58",      wilayaCodeFromIso("DZ-58"), "58");
check("DZ-01 -> 01",      wilayaCodeFromIso("DZ-01"), "01");
check("DZ-69 -> 69",      wilayaCodeFromIso("DZ-69"), "69");
check("bare '30' passes", wilayaCodeFromIso("30"), "30");
check("numeric 30 passes", wilayaCodeFromIso(30), "30");
check("missing -> null",  wilayaCodeFromIso(undefined), null);
check("nonsense -> null", wilayaCodeFromIso("Adrar"), null);

console.log("\nsite.js wiring");
const sitePath = path.join(__dirname, "site.js");
if (fs.existsSync(sitePath)) {
  const src = fs.readFileSync(sitePath, "utf-8");
  const has = (s) => src.includes(s);
  checkTrue("environment endpoint called", has("/environment"));
  checkTrue("environment state tracked", has("envPhase"));
  checkTrue("frp-driven radius on the live layer", has('["get", "frp"]'));
  checkTrue("keyboard handler installed", has("installKeyboard()"));
  checkTrue("inspection handle exports the new helpers",
        has("stepIncident") && has("dialSvg") && has("frpRadius"));
  checkTrue("no Arabic toggle reintroduced", !has("langButton") && !has("rtlSwitch"));
  checkTrue("still no tile source", !/tiles\.(maplibre|openstreetmap|osm)/.test(src));
  checkTrue("dial uses the downwind bearing, not the FROM bearing",
        src.includes("const to = (from + 180) % 360;"));
  checkTrue("wilaya code is derived from shapeISO, never read as .code",
        src.includes("function wilayaCodeFromIso") && src.includes("wilayaCodeAt"));
  /* The only legitimate `properties.code` left is the fallback inside the ISO
     parser's call site, which is guarded and immediately normalised. What must
     not exist is a raw read: `.properties.code` used directly as a wilaya
     identity, which is what broke keyboard navigation. */
  const rawReads = src
    .split("\n")
    .map((l, i) => [i + 1, l])
    .filter(([, l]) => /\.properties\.code\b/.test(l) && !l.includes("wilayaCodeFromIso"))
    .filter(([, l]) => !/^\s*(\/\/|\*)/.test(l));   // comments are fine
  checkTrue("no consumer reads properties.code as a wilaya identity",
        rawReads.length === 0);
  if (rawReads.length) {
    rawReads.forEach(([n, l]) => console.log(`         line ${n}: ${l.trim()}`));
  }
} else {
  console.log("  SKIP  site.js not found next to this test");
}

console.log("");
if (failures) {
  console.log(`RESULT: ${failures} check(s) FAILED`);
  process.exit(1);
}
console.log("RESULT: all checks passed");