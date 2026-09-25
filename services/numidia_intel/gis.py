"""GIS intelligence foundation: uniform layer responses, honest availability.

Real today: Algeria wilaya lookup (bundled geoBoundaries polygons, reused from
numidia_core.enrichment - computation, not duplicated data).
Not available (no validated dataset bundled): nearest settlement, nearest
road, elevation, slope, protected/forest context. Those layers return
data_available=false / status=UNAVAILABLE with a reason - never fabricated.
"""
from __future__ import annotations

from numidia_core.enrichment import lookup_wilaya

from .schemas import GisContext, GisLayer

WILAYA_SOURCE = ("geoBoundaries Algeria ADM1 (48 units, pre-2019 delineation, "
                 "CC-BY-4.0), bundled at data/gis/algeria_wilayas.geojson")


def _unavailable(reason: str) -> GisLayer:
    return GisLayer(data_available=False, status="UNAVAILABLE",
                    value=None, source=None, reason=reason)


def get_context(lat: float, lon: float) -> GisContext:
    """GIS context for a point. Only wilaya is real; the rest are UNAVAILABLE."""
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return GisContext(
            lat=None, lon=None,
            wilaya=_unavailable("invalid coordinates"),
            settlement=_unavailable("invalid coordinates"),
            road=_unavailable("invalid coordinates"),
            elevation=_unavailable("invalid coordinates"),
            slope=_unavailable("invalid coordinates"),
            forest_cover=_unavailable("invalid coordinates"),
        )
    hit = lookup_wilaya(lat_f, lon_f)
    if hit.get("wilaya_code"):
        wilaya = GisLayer(data_available=True, status="OK",
                          value={"code": hit["wilaya_code"], "name": hit["wilaya_name"]},
                          source=WILAYA_SOURCE)
    else:
        wilaya = _unavailable("point falls outside all bundled wilaya polygons "
                              "(offshore / border / outside Algeria)")
    return GisContext(
        lat=lat_f, lon=lon_f,
        wilaya=wilaya,
        settlement=_unavailable("no validated settlement dataset bundled; "
                                "nearest-settlement lookup unavailable"),
        road=_unavailable("no validated road-network dataset bundled; "
                          "nearest-road lookup unavailable"),
        elevation=_unavailable("no validated elevation dataset (e.g. SRTM DEM) "
                               "bundled; elevation lookup unavailable"),
        slope=_unavailable("slope derives from elevation data, which is "
                           "unavailable; slope lookup unavailable"),
        forest_cover=_unavailable("no validated protected/forest-area dataset "
                                  "bundled; forest-context lookup unavailable"),
    )


def layers_status() -> dict:
    """Which GIS layers are backed by real data (for status/reporting)."""
    return {
        "wilaya": {"data_available": True, "source": WILAYA_SOURCE},
        "settlement": {"data_available": False, "status": "UNAVAILABLE"},
        "road": {"data_available": False, "status": "UNAVAILABLE"},
        "elevation": {"data_available": False, "status": "UNAVAILABLE"},
        "slope": {"data_available": False, "status": "UNAVAILABLE"},
        "forest_cover": {"data_available": False, "status": "UNAVAILABLE"},
    }
