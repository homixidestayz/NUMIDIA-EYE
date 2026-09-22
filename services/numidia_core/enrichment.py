"""Real GIS enrichment: assign each detection its Algerian wilaya.

Computation, not data: point-in-polygon lookups against the bundled
geoBoundaries Algeria ADM1 polygons (48 units, CC-BY-4.0 - the pre-2019
delineation, so newer split wilayas resolve to their parent polygon and the
source is documented, not hidden). Detections outside every polygon
(offshore, border noise) keep null wilaya fields - honestly missing, never
guessed.
"""
from __future__ import annotations

import json

import pandas as pd
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

from .config import WILAYA_GEOJSON

_tree: STRtree | None = None
_units: list[dict] | None = None


def _load_index() -> tuple[STRtree | None, list[dict]]:
    global _tree, _units
    if _tree is not None and _units is not None:
        return _tree, _units
    if not WILAYA_GEOJSON.exists():
        _tree, _units = None, []
        return _tree, _units
    data = json.loads(WILAYA_GEOJSON.read_text(encoding="utf-8"))
    geoms, _units = [], []
    for feat in data.get("features", []):
        try:
            geom = shape(feat["geometry"])
        except (KeyError, ValueError):
            continue
        if geom.is_empty:
            continue
        geoms.append(geom)
        props = feat.get("properties", {}) or {}
        iso = str(props.get("shapeISO", ""))
        _units.append({
            "wilaya_code": iso.split("-")[-1] if "-" in iso else None,
            "wilaya_name": props.get("shapeName"),
            "wilaya_iso": iso or None,
        })
    _tree = STRtree(geoms) if geoms else None
    return _tree, _units


def lookup_wilaya(lat: float, lon: float) -> dict:
    """Return {wilaya_code, wilaya_name} for a point, or Nones if unmatched."""
    tree, units = _load_index()
    if tree is None:
        return {"wilaya_code": None, "wilaya_name": None}
    try:
        pt = Point(float(lon), float(lat))
    except (TypeError, ValueError):
        return {"wilaya_code": None, "wilaya_name": None}
    for idx in tree.query(pt, predicate="intersects"):
        props = units[int(idx)]
        if props["wilaya_code"]:
            return {"wilaya_code": props["wilaya_code"],
                    "wilaya_name": props["wilaya_name"]}
    return {"wilaya_code": None, "wilaya_name": None}


def assign_wilaya(df: pd.DataFrame) -> pd.DataFrame:
    """Add wilaya_code / wilaya_name columns (null where unmatched)."""
    out = df.copy()
    codes, names = [], []
    for lat, lon in zip(out.get("lat", []), out.get("lon", [])):
        hit = lookup_wilaya(lat, lon)
        codes.append(hit["wilaya_code"])
        names.append(hit["wilaya_name"])
    out["wilaya_code"] = codes
    out["wilaya_name"] = names
    return out


# Tolerance for simplified-boundary slivers (~1 km). Points farther than this
# from every polygon are genuinely outside Algeria (the FIRMS bbox necessarily
# over-covers: neighbors + Mediterranean) and are excluded, never guessed.
TOLERANCE_DEG = 0.01


def clip_to_algeria(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Keep only detections inside Algeria; snap sub-tolerance edge slivers.

    Returns (clipped frame, n_excluded). The product scope is Algeria: FIRMS
    bbox rows over Tunisia/Morocco/Libya/Mali/Niger and the Mediterranean are
    excluded with a recorded count (audit), not silently served as Algerian.
    """
    out = assign_wilaya(df)
    missing = out["wilaya_code"].isna()
    if missing.any():
        tree, units = _load_index()
        geoms = list(tree.geometries) if tree is not None else []
        for idx in out[missing].index:
            try:
                pt = Point(float(out.at[idx, "lon"]), float(out.at[idx, "lat"]))
            except (TypeError, ValueError):
                continue
            best, best_d = None, None
            for j, geom in enumerate(geoms):
                d = geom.distance(pt)
                if best_d is None or d < best_d:
                    best, best_d = j, d
            if best is not None and best_d is not None and best_d <= TOLERANCE_DEG:
                out.at[idx, "wilaya_code"] = units[best]["wilaya_code"]
                out.at[idx, "wilaya_name"] = units[best]["wilaya_name"]
    excluded = int(out["wilaya_code"].isna().sum())
    return out[out["wilaya_code"].notna()].reset_index(drop=True), excluded