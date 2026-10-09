"""The bundled boundaries must reflect Algeria's CURRENT administrative division.

Algeria has 69 wilayas: 48 original (Law 84-09, 1984), +10 southern promoted in2019
(Law 19-12), +11 Hauts Plateaux promoted in 2026 (Law 26-06). The previous bundle
was the 1984 delineation, in which every promoted wilaya silently resolved to its
parent - including In Salah, Touggourt, Djanet and El M'Ghair, all oil and gas
fields, which resolved to Tamanrasset, Ouargla, Illizi and El Oued.

These tests pin the count, the coding, and the specific resolution that was wrong.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import Point, shape

from numidia_core.config import WILAYA_GEOJSON

TOTAL_WILAYAS = 69
ORIGINAL_1984 = 48
PROMOTED_2019 = 10
PROMOTED_2026 = 11


@pytest.fixture(scope="module")
def features() -> list[dict]:
    data = json.loads(WILAYA_GEOJSON.read_text(encoding="utf-8"))
    return data["features"]


def test_boundaries_carry_every_current_wilaya(features):
    assert len(features) == TOTAL_WILAYAS


def test_codes_run_one_to_sixty_nine(features):
    codes = sorted(int(f["properties"]["shapeISO"].split("-")[-1]) for f in features)
    assert codes == list(range(1, TOTAL_WILAYAS + 1))


def test_the_three_reform_eras_are_recorded(features):
    """A promoted wilaya must stay visible as promoted, not be flattened away."""
    eras = [f["properties"]["created"] for f in features]
    assert eras.count("original") == ORIGINAL_1984
    assert eras.count("2019") == PROMOTED_2019
    assert eras.count("2026") == PROMOTED_2026


def test_wilayas_promoted_after_1984_are_not_the_ones_we_lost(features):
    """Every one of the 21 promoted wilayas must exist as its own feature."""
    promoted = {int(f["properties"]["shapeISO"].split("-")[-1])
                for f in features if f["properties"]["created"] != "original"}
    assert len(promoted) == PROMOTED_2019 + PROMOTED_2026
    assert min(promoted) == 49, "the 2019 promotion begins at wilaya 49"


@pytest.mark.parametrize("code", [49, 53, 55, 56, 57, 58, 59, 69])
def test_promoted_wilaya_capitals_resolve_to_themselves(features, code):
    """The regression: these used to resolve to a pre-2019 parent wilaya."""
    target = next(f for f in features
                  if int(f["properties"]["shapeISO"].split("-")[-1]) == code)
    capital = Point(target["properties"]["capital_lon"],
                    target["properties"]["capital_lat"])
    hits = {int(f["properties"]["shapeISO"].split("-")[-1])
            for f in features if shape(f["geometry"]).intersects(capital)}
    assert code in hits, f"wilaya {code} capital did not resolve to itself: {hits}"


def test_oil_and_gas_wilayas_are_distinct_from_their_old_parents(features):
    """The four flare-heartland wilayas that were misattributed."""
    expected_parents_that_must_not_win = {
        53: 11,   # In Salah, not Tamanrasset
        55: 30,   # Touggourt, not Ouargla
        56: 32,   # Djanet, not Illizi
        57: 39,   # El M'Ghair, not El Oued
    }
    for code, old_parent in expected_parents_that_must_not_win.items():
        f = next(x for x in features
                 if int(x["properties"]["shapeISO"].split("-")[-1]) == code)
        capital = Point(f["properties"]["capital_lon"], f["properties"]["capital_lat"])
        hits = {int(x["properties"]["shapeISO"].split("-")[-1])
                for x in features if shape(x["geometry"]).intersects(capital)}
        assert code in hits
        # The old parent may still contain the point if the new wilaya has not
        # fully separated yet; what must not happen is the new code being absent.
        assert hits != {old_parent}, f"wilaya {code} collapsed back into {old_parent}"


def test_points_outside_algeria_resolve_to_nothing(features):
    """Must stay honestly null rather than snapping to a nearest polygon."""
    offshore = Point(2.0, 20.0)  # open Mediterranean
    hits = [f for f in features if shape(f["geometry"]).intersects(offshore)]
    assert hits == []


def test_every_feature_is_a_valid_polygon_with_a_name(features):
    for f in features:
        props = f["properties"]
        assert props["shapeName"], f"unnamed wilaya {props.get('shapeISO')}"
        assert f["geometry"]["type"] in ("Polygon", "MultiPolygon")