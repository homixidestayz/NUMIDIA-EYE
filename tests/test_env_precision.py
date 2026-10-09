"""The precision claim must be real, not merely present.

A regression guard for a specific silent failure: `get_incident()` returns
`member_ids`, not member rows, so a spread calculation that reads
`incident["member_detections"]` finds nothing and reports no spread. The
response still *looks* complete - the key exists, the value is null - and a
reader concludes the cluster is a point when it may be 20 km wide.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from numidia_env import STATUS_AVAILABLE
from numidia_env import incident_context as ic
from numidia_env.cache import DiskCache

FIXTURE = Path(__file__).parent / "fixtures" / "open_meteo_ouargla.json"


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class StubFetcher:
    def __init__(self, payload=None, error=None):
        self.payload, self.error, self.calls = payload, error, []

    def __call__(self, lat, lon):
        self.calls.append((lat, lon))
        if self.error:
            raise self.error
        return self.payload


# The shape the API actually produces: ids only, no coordinates.
REAL_INCIDENT = {
    "id": "INC-real", "centroid_lat": 30.37457, "centroid_lon": 7.0109,
    "member_ids": ["a", "b", "c"],
}


def test_spread_is_none_when_only_member_ids_are_present(tmp_path):
    """Documents the trap: ids alone cannot produce a spread."""
    out = ic.environment_for_incident(
        REAL_INCIDENT, fetcher=StubFetcher(_payload()),
        cache=DiskCache(tmp_path / "c"))
    assert out["precision"]["centroid_spread_m"] is None
    assert out["precision"]["exceeds_max_precision_m"] is None


def test_passing_member_rows_yields_a_real_spread(tmp_path):
    members = [{"lat": 30.37457, "lon": 7.0109},
               {"lat": 30.50, "lon": 7.00}]   # ~14 km north
    out = ic.environment_for_incident(
        REAL_INCIDENT, members=members, fetcher=StubFetcher(_payload()),
        cache=DiskCache(tmp_path / "c"))

    spread = out["precision"]["centroid_spread_m"]
    assert spread is not None, "member coordinates were supplied but spread is null"
    assert 13000 < spread < 16000, f"expected ~14 km, got {spread}"
    assert out["precision"]["exceeds_max_precision_m"] is False


def test_a_very_wide_cluster_is_flagged(tmp_path):
    members = [{"lat": 31.0, "lon": 7.0}]   # ~70 km
    out = ic.environment_for_incident(
        REAL_INCIDENT, members=members, fetcher=StubFetcher(_payload()),
        cache=DiskCache(tmp_path / "c"))
    assert out["precision"]["exceeds_max_precision_m"] is True
    assert out["precision"]["centroid_spread_m"] > ic.MAX_PRECISION_M


def test_environment_is_still_returned_when_spread_is_unknown(tmp_path):
    """Unknown precision must not suppress the reading itself."""
    out = ic.environment_for_incident(
        REAL_INCIDENT, fetcher=StubFetcher(_payload()),
        cache=DiskCache(tmp_path / "c"))
    assert out["status"] == STATUS_AVAILABLE
    assert out["temperature_2m_c"] is not None
    assert out["precision"]["note"]