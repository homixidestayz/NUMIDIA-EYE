"""Environmental context attached to an incident.

The properties under test are the ones that make the number safe to reason with:
precision is STATED rather than implied, and an unavailable upstream produces an
explicitly absent value rather than a zero that would read as "no wind".
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from numidia_env import STATUS_AVAILABLE, STATUS_UNAVAILABLE
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


# Ouargla centroid with detections a few km out, so spread is measurable.
INCIDENT = {
    "incident_id": "INC-test",
    "centroid_lat": 30.37457, "centroid_lon": 7.0109,
    "member_detections": [
        {"lat": 30.40, "lon": 7.00},
        {"lat": 30.35, "lon": 7.05},
    ],
}


def test_attaches_real_environment_to_an_incident(tmp_path):
    out = ic.environment_for_incident(
        INCIDENT, fetcher=StubFetcher(_payload()),
        cache=DiskCache(tmp_path / "c"))
    assert out["status"] == STATUS_AVAILABLE
    assert out["wind_speed_10m_ms"] == pytest.approx(1.83)
    assert out["attached_to"] == "incident_centroid"
    assert out["reason"] is None


def test_precision_is_stated_not_implied(tmp_path):
    out = ic.environment_for_incident(
        INCIDENT, fetcher=StubFetcher(_payload()),
        cache=DiskCache(tmp_path / "c"))
    p = out["precision"]
    assert p["centroid_spread_m"] > 0, "a cluster is not a point"
    assert p["max_precision_m"] == ic.MAX_PRECISION_M
    assert "not at each detection" in p["note"]


def test_a_wide_cluster_is_flagged_as_exceeding_precision(tmp_path):
    wide = dict(INCIDENT, member_detections=[{"lat": 30.60, "lon": 7.20}])
    out = ic.environment_for_incident(
        wide, fetcher=StubFetcher(_payload()), cache=DiskCache(tmp_path / "c"))
    assert out["precision"]["exceeds_max_precision_m"] is True


def test_upstream_failure_never_becomes_zero_wind(tmp_path):
    """0.0 m/s would read as 'perfectly still' and defeat downwind reasoning."""
    out = ic.environment_for_incident(
        INCIDENT, fetcher=StubFetcher(error=ConnectionError("reset")),
        cache=DiskCache(tmp_path / "c"))
    assert out["status"] == STATUS_UNAVAILABLE
    assert out["wind_speed_10m_ms"] is None
    assert out["wind_direction_10m_deg"] is None
    assert out["temperature_2m_c"] is None
    assert out["reason"]


def test_incident_without_a_centroid_is_unavailable_not_a_crash(tmp_path):
    out = ic.environment_for_incident(
        {"incident_id": "INC-x"}, fetcher=StubFetcher(_payload()),
        cache=DiskCache(tmp_path / "c"))
    assert out["status"] == STATUS_UNAVAILABLE
    assert "centroid" in out["reason"]


def test_the_centroid_is_what_gets_fetched(tmp_path):
    fetcher = StubFetcher(_payload())
    ic.environment_for_incident(INCIDENT, fetcher=fetcher,
                                cache=DiskCache(tmp_path / "c"))
    assert fetcher.calls == [(30.37457, 7.0109)]


def test_repeated_calls_hit_the_cache(tmp_path):
    fetcher = StubFetcher(_payload())
    cache = DiskCache(tmp_path / "c")
    inc = ic.environment_for_incident(INCIDENT, fetcher=fetcher, cache=cache)
    again = ic.environment_for_incident(INCIDENT, fetcher=fetcher, cache=cache)
    assert len(fetcher.calls) == 1
    assert inc["wind_speed_10m_ms"] == again["wind_speed_10m_ms"]


def test_payload_is_json_serialisable(tmp_path):
    out = ic.environment_for_incident(
        INCIDENT, fetcher=StubFetcher(_payload()),
        cache=DiskCache(tmp_path / "c"))
    json.dumps(out)  # must not raise


def test_centroid_spread_handles_missing_member_coordinates():
    inc = {"centroid_lat": 30.0, "centroid_lon": 7.0,
           "member_detections": [{"lat": None, "lon": None}]}
    assert ic.centroid_spread_m(inc) is None