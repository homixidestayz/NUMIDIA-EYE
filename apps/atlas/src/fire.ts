/* Fire appearance.
 *
 *  Rule that governs this whole file: a marker's size and colour encode fire
 *  radiative power and nothing else. Nothing here animates, pulses, or
 *  brightens on a timer, because none of that is measured. A detection whose
 *  FRP is missing gets the smallest mark, never a substitute size.
 */

/** Upper MW bound of each bucket. Bucket i covers [BREAKS[i-1], BREAKS[i]). */
export const FRP_BREAKS = [10, 100, 500, 2000] as const;

export const BUCKET_COUNT = FRP_BREAKS.length + 1;

/** Warm ramp, coolest first. Deeper red reads as more intense than pale
 *  orange, so the ramp moves that way as FRP rises. */
export const BUCKET_COLORS = [
  "#e8934a", // < 10 MW
  "#ef7a33", // 10 – 100 MW
  "#f05a28", // 100 – 500 MW
  "#e03a2f", // 500 – 2000 MW
  "#d0243f", // > 2000 MW
] as const;

const CORE = "#ffe0a3";

export function bucketFor(frp: number | null | undefined): number {
  if (typeof frp !== "number" || !Number.isFinite(frp) || frp < 0) return 0;
  for (let i = 0; i < FRP_BREAKS.length; i++) {
    if (frp < FRP_BREAKS[i]) return i;
  }
  return BUCKET_COUNT - 1;
}

/** Plain-language range for the legend, so no number appears without a basis. */
export function bucketLabel(b: number): string {
  if (b <= 0) return "< 10 MW";
  if (b >= BUCKET_COUNT - 1) return "> 2000 MW";
  return `${FRP_BREAKS[b - 1]} – ${FRP_BREAKS[b]} MW`;
}

/** Log scale. FRP spans four orders of magnitude, so a linear radius would
 *  make everything above 100 MW an identical dot. Capped so one very large
 *  fire cannot cover a wilaya. */
export function radiusScale(frp: number | null | undefined): number {
  const v = typeof frp === "number" && Number.isFinite(frp) && frp > 0 ? frp : 0;
  return 9 + Math.min(1, Math.log10(v + 1) / Math.log10(2001)) * 17;
}

/* Canvas lives only in the browser. jsdom has no 2D context, so the tests
   exercise this through the same drawing calls with a stub context. */
type Ctx = Pick<
  CanvasRenderingContext2D,
  | "createRadialGradient"
  | "beginPath"
  | "moveTo"
  | "bezierCurveTo"
  | "closePath"
  | "fill"
  | "fillStyle"
>;

/** Brightness of the hot core. Rises with the bucket so a bigger fire reads as
 *  a bigger fire without any animation. Pure, so it is testable. */
export function coreAlpha(bucket: number): number {
  return 0.55 + bucket * 0.09;
}

/** Height of the core tip above its base, in 64-box units. Higher buckets burn
 *  hotter toward the top. Pure, so it is testable. */
export function coreTipY(bucket: number): number {
  return 33 - (0.1 + bucket * 0.035) * 14;
}

/** Outline of a flame in a 64×64 box, tip at the top, scaled to `size`. */
export function outlineScale(size: number): number {
  return size / 64;
}

/* Bezier segments: [c1x, c1y, c2x, c2y, x, y], with the first entry the
   starting moveTo. Typed as number[][] rather than a tuple union so the
   compiler does not treat the short first row as unindexable. */
const OUTER: ReadonlyArray<ReadonlyArray<number>> = [
  [32, 62],
  [16, 50, 10, 38, 13, 29],
  [15, 20, 22, 15, 25, 10],
  [27, 7, 30, 5, 32, 2],
  [34, 9, 41, 13, 45, 21],
  [51, 32, 52, 42, 47, 50],
  [43, 56, 37, 60, 32, 62],
];

/** Outline of a flame in a 64×64 box, tip at the top. */
function traceFlame(ctx: Ctx, scale: number): void {
  ctx.beginPath();
  ctx.moveTo(OUTER[0][0] * scale, OUTER[0][1] * scale);
  for (let i = 1; i < OUTER.length; i++) {
    const c = OUTER[i]!;
    ctx.bezierCurveTo(
      c[0] * scale,
      c[1] * scale,
      c[2] * scale,
      c[3] * scale,
      c[4] * scale,
      c[5] * scale,
    );
  }
  ctx.closePath();
}

/** Renders a flame for `bucket` at `size` px, returning RGBA pixel data for
 *  MapLibre's addImage. The soft radial glow is baked in so a single symbol
 *  layer reads as fire rather than a sticker. */
export function flameImageData(bucket: number, size: number): ImageData {
  if (!Number.isInteger(bucket) || bucket < 0 || bucket >= BUCKET_COUNT) {
    throw new RangeError(`bucket ${bucket} outside 0..${BUCKET_COUNT - 1}`);
  }
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("2D canvas unavailable");
  const s = size / 64;
  const color = BUCKET_COLORS[bucket];

  // glow
  const g = ctx.createRadialGradient(32 * s, 42 * s, 2 * s, 32 * s, 42 * s, 31 * s);
  g.addColorStop(0, hexToRgba(color, 0.5));
  g.addColorStop(0.55, hexToRgba(color, 0.16));
  g.addColorStop(1, hexToRgba(color, 0));
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.arc(32 * s, 42 * s, 31 * s, 0, Math.PI * 2);
  ctx.fill();

  // outer flame
  ctx.fillStyle = color;
  traceFlame(ctx, s);
  ctx.fill();

  // hot core, brighter and taller for higher buckets
  const tip = coreTipY(bucket);
  ctx.fillStyle = hexToRgba(CORE, coreAlpha(bucket));
  ctx.beginPath();
  ctx.moveTo(32 * s, 58 * s);
  ctx.bezierCurveTo(25 * s, 50 * s, 24 * s, (tip + 7) * s, 30 * s, tip * s);
  ctx.bezierCurveTo(33 * s, (tip + 5) * s, 38 * s, (tip + 7) * s, 32 * s, 58 * s);
  ctx.closePath();
  ctx.fill();

  return ctx.getImageData(0, 0, size, size);
}

function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

/** MapLibre icon-image expression, so the icon is chosen on the GPU rather
 *  than by thousands of DOM nodes.
 *
 *  The default is deliberately the COOLEST flame. A single `match` cannot both
 *  reach the hottest bucket and default safely, so the top bucket is pulled out
 *  with a `case`. Getting this wrong renders a detection with no FRP as the
 *  most intense fire on the map, which is precisely the fabrication this
 *  project exists to avoid. */
export function matchExpression(): unknown[] {
  const inner: unknown[] = ["match", ["get", "frpBucket"]];
  for (let b = 0; b < BUCKET_COUNT - 1; b++) {
    inner.push(b, `flame-${b}`);
  }
  inner.push("flame-0");
  return [
    "case",
    ["==", ["get", "frpBucket"], BUCKET_COUNT - 1],
    `flame-${BUCKET_COUNT - 1}`,
    inner,
  ];
}

/** Every image name this module expects to have been registered. */
export function flameImageNames(): string[] {
  return Array.from({ length: BUCKET_COUNT }, (_, b) => `flame-${b}`);
}