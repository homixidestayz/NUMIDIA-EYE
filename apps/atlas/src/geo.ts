import type { WilayaFeature } from "./types";

/* Pure geometry helpers for the wilaya boundary set.
 *
 *   Kept apart from MapView.tsx on purpose: importing the map component drags in
 *   maplibre-gl, which touches window.URL.createObjectURL at module scope and
 *   throws under jsdom. These functions are testable without a WebGL context,
 *   and they are the part that has to be right — 68 of the 69 wilayas are
 *   Polygon and exactly one is a MultiPolygon.
 *
 *   69 wilayas, per Law 84-09 (48), Law 19-12 (+10) and Law 26-06 (+11).
 */

export type Ring = number[][];
export type Geometry = WilayaFeature["geometry"];

/** Two-digit wilaya code, e.g. "DZ-16" -> "16". Must match the zero-padded
 *  `wilaya_code` the detections API returns, or every filter matches nothing. */
export const wilayaCode = (f: WilayaFeature): string =>
  String(f.properties.shapeISO).split("-").pop() ?? "";

/** Outermost ring of a Polygon or of a MultiPolygon. */
export function exteriorRing(geometry: Geometry): Ring {
  if (geometry.type === "Polygon") {
    return geometry.coordinates[0] ?? [];
  }
  return geometry.coordinates[0]?.[0] ?? [];
}

/** Every ring, so a multi-part wilaya is framed whole by boundsOf(). */
export function allRings(geometry: Geometry): Ring[] {
  return geometry.type === "Polygon" ? geometry.coordinates : geometry.coordinates.flat();
}

/** Longitude/latitude bounding box, or null when there is nothing finite. */
export function boundsOf(
  geometry: Geometry,
): [[number, number], [number, number]] | null {
  let w = Infinity;
  let s = Infinity;
  let e = -Infinity;
  let n = -Infinity;
  let seen = false;
  for (const ring of allRings(geometry)) {
    for (const pt of ring) {
      const lon = pt[0];
      const lat = pt[1];
      if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
      seen = true;
      if (lon < w) w = lon;
      if (lon > e) e = lon;
      if (lat < s) s = lat;
      if (lat > n) n = lat;
    }
  }
  return seen ? [[w, s], [e, n]] : null;
}

/** Label anchor for a wilaya. A vertex average rather than a true centroid: it
 *  needs no area-weighted geometry and cannot fail on a degenerate ring. */
export function anchorOf(geometry: Geometry): [number, number] | null {
  const ring = exteriorRing(geometry);
  if (!ring.length) return null;
  let x = 0;
  let y = 0;
  let k = 0;
  for (const pt of ring) {
    if (Number.isFinite(pt[0]) && Number.isFinite(pt[1])) {
      x += pt[0];
      y += pt[1];
      k += 1;
    }
  }
  return k ? [x / k, y / k] : null;
}

/** Rough planar extent of a wilaya, in square degrees.
 *
 *  Only ever compared against other wilayas to decide which labels win a
 *  collision, so an unprojected magnitude is fine — what matters is that a big
 *  wilaya outranks a small one. */
export function areaOf(geometry: Geometry): number {
  let sum = 0;
  for (const ring of allRings(geometry)) {
    let a = 0;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = ring[i]?.[0];
      const yi = ring[i]?.[1];
      const xj = ring[j]?.[0];
      const yj = ring[j]?.[1];
      if (!Number.isFinite(xi) || !Number.isFinite(yi)) continue;
      if (!Number.isFinite(xj) || !Number.isFinite(yj)) continue;
      a += (xj - xi) * (yj + yi);
    }
    sum += Math.abs(a / 2);
  }
  return sum;
}