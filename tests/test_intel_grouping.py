"""Equivalence and performance guards for incident grouping.

group_detections() was rewritten to look up candidate incidents through a grid
index instead of scanning every open incident. The chaining rule must be
bit-for-bit the same, so these tests keep a verbatim copy of the original scan
and require the two implementations to produce identical groupings - including
the tie-break between incidents that share a last acquisition time, rows with
unusable coordinates or times, and rows that fall exactly on the chaining radius.

The equivalence tests use synthetic rows, so they never need the model artifact.
"""
from __future__ import annotations

import random
import time as time_mod
from datetime import datetime, timedelta, timezone

import numpy as np

from numidia_intel import incidents as I

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _reference_group(rows: list[dict]) -> list[list[dict]]:
    """Verbatim copy of the pre-optimisation implementation.

    Kept deliberately naive and slow: it scans every open incident for every
    detection. The optimised version must agree with it exactly.
    """
    timed = []
    for r in rows:
        ts = I._parse_acq(r.get("acq_datetime"))
        try:
            lat, lon = float(r.get("lat")), float(r.get("lon"))
        except (TypeError, ValueError):
            lat, lon = None, None
        timed.append((ts, lat, lon, r))
    timed.sort(key=lambda t: (t[0] is None, t[0]))

    incidents: list[dict] = []
    for ts, lat, lon, r in timed:
        best, best_ts = None, None
        if ts is not None and lat is not None:
            for inc in incidents:
                if inc["last_ts"] is None or inc["last_lat"] is None:
                    continue
                gap_h = (ts - inc["last_ts"]).total_seconds() / 3600.0
                if gap_h < 0 or gap_h > I.TEMPORAL_GAP_HOURS:
                    continue
                d = I._haversine_deg(
                    lat, lon,
                    np.array([inc["last_lat"]]), np.array([inc["last_lon"]]))[0]
                if d <= I.SPATIAL_EPS_DEG and (best is None or inc["last_ts"] > best_ts):
                    best, best_ts = inc, inc["last_ts"]
        if best is None:
            incidents.append({"members": [r], "last_ts": ts,
                              "last_lat": lat, "last_lon": lon})
        else:
            best["members"].append(r)
            best["last_ts"] = ts
            best["last_lat"] = lat
            best["last_lon"] = lon
    return [inc["members"] for inc in incidents]


def _ids(groups: list[list[dict]]) -> list[list[str]]:
    return [[str(m.get("detection_id")) for m in g] for g in groups]


def _rows(seed: int, count: int) -> list[dict]:
    """Synthetic detections over an Algerian-sized bounding box."""
    rng = random.Random(seed)
    rows = []
    for i in range(count):
        lat = round(rng.uniform(18.0, 38.0), 5)
        lon = round(rng.uniform(-9.0, 12.0), 5)
        rows.append({
            "detection_id": f"d{i:04d}",
            "lat": lat,
            "lon": lon,
            # Many rows share a timestamp so the tie-break is exercised.
            "acq_datetime": (BASE + timedelta(minutes=30 * rng.randint(0, 60))
                             ).isoformat(),
            "frp": round(rng.uniform(0, 50), 2),
            "satellite": rng.choice(["N20", "N21", "SNPP"]),
            "wilaya_name": "Adrar",
        })
    return rows


def _assert_same_groups(rows: list[dict]) -> None:
    expected = _ids(_reference_group([dict(r) for r in rows]))
    actual = _ids(I.group_detections([dict(r) for r in rows]))
    assert actual == expected, (
        f"grouping diverged: {len(actual)} groups vs {len(expected)} expected"
    )


def test_grouping_matches_reference_on_random_data():
    for seed in (1, 2, 3, 7, 11):
        _assert_same_groups(_rows(seed, 300))


def test_grouping_matches_reference_when_detections_are_clustered():
    """Dense clusters: many candidate matches per detection."""
    rng = random.Random(99)
    rows = []
    for c in range(12):
        clat = round(rng.uniform(19.0, 37.0), 5)
        clon = round(rng.uniform(-8.0, 11.0), 5)
        for i in range(25):
            rows.append({
                "detection_id": f"c{c}-{i:03d}",
                "lat": round(clat + rng.uniform(-0.02, 0.02), 5),
                "lon": round(clon + rng.uniform(-0.02, 0.02), 5),
                "acq_datetime": (BASE + timedelta(hours=rng.randint(0, 48))
                                 ).isoformat(),
                "frp": 1.0,
                "satellite": "N21",
            })
    _assert_same_groups(rows)


def test_grouping_matches_reference_on_exact_radius():
    """Points placed exactly on / just inside / just outside the radius."""
    for delta in (0.0, 1e-9, -1e-9, 0.001, -0.001):
        rows = [
            {"detection_id": "a", "lat": 30.0, "lon": 2.0,
             "acq_datetime": BASE.isoformat(), "frp": 1.0},
            {"detection_id": "b", "lat": 30.0 + I.SPATIAL_EPS_DEG + delta, "lon": 2.0,
             "acq_datetime": (BASE + timedelta(hours=1)).isoformat(), "frp": 1.0},
        ]
        _assert_same_groups(rows)


def test_grouping_matches_reference_with_unusable_fields():
    rows = _rows(5, 120)
    # Rows with missing coordinates, non-numeric coordinates and missing times
    # must still stand alone and must not corrupt the candidate index.
    rows.append({"detection_id": "nolat", "lat": None, "lon": 2.0,
                 "acq_datetime": (BASE + timedelta(hours=2)).isoformat()})
    rows.append({"detection_id": "nocoord", "lat": "not-a-number", "lon": "x",
                 "acq_datetime": (BASE + timedelta(hours=2)).isoformat()})
    rows.append({"detection_id": "notime", "lat": 31.0, "lon": 3.0,
                 "acq_datetime": None})
    rows.append({"detection_id": "emptyid", "lat": 31.0, "lon": 3.0,
                 "acq_datetime": (BASE + timedelta(hours=3)).isoformat()})
    _assert_same_groups(rows)


def test_grouping_matches_reference_at_high_latitude():
    """The candidate-cell radius widens with longitude compression near poles."""
    for lat in (0.0, 45.0, 60.0, 75.0, 89.0):
        rows = [
            {"detection_id": f"p{i}", "lat": lat, "lon": 0.002 * i,
             "acq_datetime": (BASE + timedelta(hours=i)).isoformat(), "frp": 1.0}
            for i in range(24)
        ]
        _assert_same_groups(rows)


def test_grouping_matches_reference_on_grid_boundaries():
    """Coordinates that land exactly on a grid cell edge must not fall through."""
    for k in range(6):
        lat = round(k * I._CELL_DEG, 10)
        lon = round(-k * I._CELL_DEG, 10)
        rows = [
            {"detection_id": f"g{k}-{i}", "lat": round(lat + 1e-6, 10),
             "lon": round(lon + 1e-6, 10),
             "acq_datetime": (BASE + timedelta(minutes=i)).isoformat(), "frp": 1.0}
            for i in range(8)
        ]
        _assert_same_groups(rows)


def test_incident_ids_are_stable_and_deterministic():
    rows = _rows(3, 200)
    first = sorted(g[0]["detection_id"] for g in I.group_detections([dict(r) for r in rows]))
    shuffled = list(rows)
    random.Random(42).shuffle(shuffled)
    second = sorted(g[0]["detection_id"] for g in I.group_detections(shuffled))
    # Grouping is time-ordered, so input order cannot change the outcome.
    assert first == second


def test_summarize_accepts_precomputed_reason_without_changing_output():
    """The memoised verification reason must produce an identical summary."""
    from numidia_intel import verification as V

    rows = _rows(4, 150)
    groups = I.group_detections(rows)
    reason = "resolved-once-for-tests"
    for group in groups[:25]:
        a = I.summarize(group)
        b = I.summarize(group, reason)
        a["priority"].pop("computed_at", None)
        b["priority"].pop("computed_at", None)
        assert a["priority"] == b["priority"]
        assert a["id"] == b["id"]
        # The message text differs only by the reason that was supplied.
        assert a["verification"]["message"].endswith(V.unavailability_reason())
        assert b["verification"]["message"].endswith(reason)
        assert a["verification"]["status"] == b["verification"]["status"] == "UNAVAILABLE"


def test_grouping_scales_linearly_not_quadratically():
    """A guard against the exact regression that made /incidents unusable.

    The naive scan compares every detection against every open incident, so its
    cost grows with the square of the row count. This asserts the optimised path
    stays near-linear over a 4x larger input.
    """
    rows = _rows(21, 2400)
    times = {}
    for n in (300, 1200):
        t0 = time_mod.perf_counter()
        I.group_detections([dict(r) for r in rows[:n]])
        times[n] = time_mod.perf_counter() - t0

    growth = times[1200] / max(times[300], 1e-6)
    # Quadratic would be ~16x for a 4x larger input; allow generous headroom
    # for timer noise on shared CI hardware while still failing a real return
    # to the naive scan.
    assert growth < 9.0, f"grouping looks super-linear again: {growth:.1f}x for 4x rows"