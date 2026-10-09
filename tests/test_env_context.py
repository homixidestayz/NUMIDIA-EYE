"""Environmental context from Open-Meteo - real API, fail-closed, never invented.

The contract these tests protect is the project's one: a missing or malformed
upstream response must produce an UNAVAILABLE context carrying a REASON, with
every measurement left None. There is no code path that substitutes a default,
a mean, or a guess for a value the API did not return.

Live HTTP is never exercised here. Tests drive a stubbed fetcher over a fixture
recorded from a real Open-Meteo response (tests/fixtures/open_meteo_ouargla.json),
so the suite is deterministic and offline while still testing the real shape.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from numidia_env import context as env_context
from numidia_env.models import STATUS_AVAILABLE, STATUS_UNAVAILABLE, EnvironmentContext

FIXTURE = Path(__file__).parent / "fixtures" / "open_meteo_ouargla.json"
OUARGLA = (30.37457, 7.0109)


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class StubFetcher:
    """Stands in for HTTP. Records calls so caching can be asserted."""

    def __init__(self, payload: dict | None = None, error: Exception | None = None):
        self.payload = payload
        self.error = error
        self.calls: list[tuple[float, float]] = []

    def __call__(self, lat: float, lon: float) -> dict:
        self.calls.append((lat, lon))
        if self.error is not None:
            raise self.error
        return self.payload


# --------------------------------------------------------------- happy path

def test_parses_a_real_open_meteo_response():
    ctx = env_context.get_environment(*OUARGLA, fetcher=StubFetcher(_payload()))

    assert ctx.status == STATUS_AVAILABLE
    assert ctx.source == "open-meteo"
    assert ctx.reason is None
    assert ctx.temperature_2m_c == pytest.approx(31.8)
    assert ctx.relative_humidity_2m_pct == pytest.approx(14)
    assert ctx.wind_direction_10m_deg == pytest.approx(315)


def test_wind_is_returned_in_metres_per_second():
    """Requested with wind_speed_unit=ms so it matches the project's metric world."""
    ctx = env_context.get_environment(*OUARGLA, fetcher=StubFetcher(_payload()))
    assert ctx.wind_speed_10m_ms == pytest.approx(1.83)
    assert ctx.wind_gusts_10m_ms == pytest.approx(4.5)


def test_soil_profile_is_captured_from_the_hourly_block():
    """Soil is hourly-only upstream; a naive `current=` request 400s.

    The observation is 17:15 and the fixture's hourly block ends at 03:00, so the
    rule under test is "most recent sample available" - taking the FIRST entry
    would silently pair 17:15 with midnight soil moisture.
    """
    ctx = env_context.get_environment(*OUARGLA, fetcher=StubFetcher(_payload()))
    assert ctx.soil_moisture_0_1_m3_m3 == pytest.approx(0.016)   # 03:00, not 00:00
    assert ctx.soil_moisture_9_27_m3_m3 == pytest.approx(0.091)
    assert ctx.soil_temperature_0_7_c == pytest.approx(23.2)
    assert ctx.soil_temperature_7_28_c == pytest.approx(28.9)


def test_elevation_and_observed_time_are_retained():
    ctx = env_context.get_environment(*OUARGLA, fetcher=StubFetcher(_payload()))
    assert ctx.elevation_m == pytest.approx(204.0)
    assert ctx.observed_at == "2026-10-09T17:15"


# ------------------------------------------------------------- fail-closed

def test_network_failure_is_unavailable_with_a_reason_and_no_numbers():
    boom = StubFetcher(error=ConnectionError("connection reset"))
    ctx = env_context.get_environment(*OUARGLA, fetcher=boom)

    assert ctx.status == STATUS_UNAVAILABLE
    assert ctx.reason and "connection reset" in ctx.reason
    assert ctx.temperature_2m_c is None
    assert ctx.wind_speed_10m_ms is None
    assert ctx.soil_moisture_0_1_m3_m3 is None


def test_garbage_upstream_response_is_unavailable_not_zero():
    ctx = env_context.get_environment(*OUARGLA, fetcher=StubFetcher({"unexpected": "shape"}))
    assert ctx.status == STATUS_UNAVAILABLE
    assert ctx.reason
    assert ctx.temperature_2m_c is None


def test_partial_response_keeps_what_is_real_and_drops_only_what_is_missing():
    """A null upstream field must stay None, never become 0.0."""
    payload = _payload()
    payload["current"]["temperature_2m"] = None
    ctx = env_context.get_environment(*OUARGLA, fetcher=StubFetcher(payload))

    assert ctx.status == STATUS_AVAILABLE
    assert ctx.temperature_2m_c is None
    assert ctx.wind_speed_10m_ms == pytest.approx(1.83)  # the rest survived


def test_unavailable_context_serialises_without_inventing_fields():
    ctx = env_context.get_environment(
        *OUARGLA, fetcher=StubFetcher(error=TimeoutError("timed out")))
    d = ctx.to_dict()

    assert d["status"] == STATUS_UNAVAILABLE
    for key in ("temperature_2m_c", "wind_speed_10m_ms", "soil_moisture_0_1_m3_m3"):
        assert d[key] is None, f"{key} must be null, never a default"
    assert d["reason"]


# ------------------------------------------------------------------- cache

def test_second_lookup_within_ttl_is_served_from_cache(tmp_path):
    fetcher = StubFetcher(_payload())
    cache = env_context.DiskCache(tmp_path, ttl_seconds=3600)

    a = env_context.get_environment(*OUARGLA, fetcher=fetcher, cache=cache)
    b = env_context.get_environment(*OUARGLA, fetcher=fetcher, cache=cache)

    assert a.temperature_2m_c == b.temperature_2m_c
    assert len(fetcher.calls) == 1, "cache should have prevented a second call"


def test_expired_cache_entry_refetches(tmp_path):
    fetcher = StubFetcher(_payload())
    cache = env_context.DiskCache(tmp_path, ttl_seconds=0)

    env_context.get_environment(*OUARGLA, fetcher=fetcher, cache=cache)
    env_context.get_environment(*OUARGLA, fetcher=fetcher, cache=cache)

    assert len(fetcher.calls) == 2, "expired entry must be refetched"


def test_nearby_coordinates_share_a_cache_entry(tmp_path):
    """Coords are rounded for cache efficiency; ~110 m at 3 decimal places."""
    fetcher = StubFetcher(_payload())
    cache = env_context.DiskCache(tmp_path, ttl_seconds=3600)

    env_context.get_environment(30.37457, 7.01090, fetcher=fetcher, cache=cache)
    env_context.get_environment(30.37458, 7.01091, fetcher=fetcher, cache=cache)

    assert len(fetcher.calls) == 1


def test_a_failed_lookup_is_not_cached(tmp_path):
    """Caching a failure would pin UNAVAILABLE for the whole TTL after one blip."""
    fetcher = StubFetcher(error=ConnectionError("reset"))
    cache = env_context.DiskCache(tmp_path, ttl_seconds=3600)

    env_context.get_environment(*OUARGLA, fetcher=fetcher, cache=cache)
    env_context.get_environment(*OUARGLA, fetcher=fetcher, cache=cache)

    assert len(fetcher.calls) == 2


# ------------------------------------------------------------------ type

def test_context_is_frozen_so_a_caller_cannot_mutate_a_shared_result():
    ctx = env_context.get_environment(*OUARGLA, fetcher=StubFetcher(_payload()))
    with pytest.raises(Exception):
        ctx.temperature_2m_c = 999.0  # type: ignore[misc]


def test_context_defaults_to_unavailable_with_no_arguments():
    """Constructing a context by hand must default to UNAVAILABLE, never AVAILABLE."""
    ctx = EnvironmentContext(latitude=1.0, longitude=2.0)
    assert ctx.status == STATUS_UNAVAILABLE