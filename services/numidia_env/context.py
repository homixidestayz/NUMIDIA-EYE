"""Fetch environmental context from Open-Meteo - keyless, real, fail-closed.

Open-Meteo needs no API key and no account, which is what makes this usable in
a demo and in a fresh clone. Two upstream quirks are handled here and nowhere
else, because both fail confusingly:

* Soil moisture and soil temperature are **hourly** variables. Asking for them in
  the `current=` block returns HTTP 400 for the whole request, taking the
  perfectly good surface readings down with it.
* Wind defaults to km/h. Every other distance and speed in this project is
  metric, so the request explicitly asks for `wind_speed_unit=ms`.

The contract: this never raises for an upstream problem. It returns an
EnvironmentContext whose measurements are all None and whose `reason` says what
went wrong. Callers that need to know whether they have real data read `.status`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlencode

from .cache import DiskCache
from .models import SOURCE_OPEN_METEO, STATUS_AVAILABLE, EnvironmentContext

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

#: Surface variables, available in the `current` block.
CURRENT_VARS = (
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "precipitation",
)

#: Soil variables, hourly ONLY. Requesting these in `current` 400s the request.
HOURLY_VARS = (
    "soil_moisture_0_to_1cm",
    "soil_moisture_3_to_9cm",
    "soil_moisture_9_to_27cm",
    "soil_temperature_0_to_7cm",
    "soil_temperature_7_to_28cm",
)

#: Upstream name -> EnvironmentContext field.
CURRENT_MAP = {
    "temperature_2m": "temperature_2m_c",
    "relative_humidity_2m": "relative_humidity_2m_pct",
    "wind_speed_10m": "wind_speed_10m_ms",
    "wind_direction_10m": "wind_direction_10m_deg",
    "wind_gusts_10m": "wind_gusts_10m_ms",
    "precipitation": "precipitation_mm",
}

HOURLY_MAP = {
    "soil_moisture_0_to_1cm": "soil_moisture_0_1_m3_m3",
    "soil_moisture_3_to_9cm": "soil_moisture_3_9_m3_m3",
    "soil_moisture_9_to_27cm": "soil_moisture_9_27_m3_m3",
    "soil_temperature_0_to_7cm": "soil_temperature_0_7_c",
    "soil_temperature_7_to_28cm": "soil_temperature_7_28_c",
}

DEFAULT_TIMEOUT = 20.0


def build_url(lat: float, lon: float) -> str:
    """One request carrying both blocks, wind in m/s."""
    params = {
        "latitude": f"{lat:.5f}",
        "longitude": f"{lon:.5f}",
        "current": ",".join(CURRENT_VARS),
        "hourly": ",".join(HOURLY_VARS),
        "wind_speed_unit": "ms",
        "timezone": "UTC",
        "forecast_days": 1,
    }
    return f"{FORECAST_URL}?{urlencode(params)}"


def _latest(hourly: dict, key: str) -> Optional[float]:
    """Most recent non-null sample of an hourly variable.

    "Most recent available", not "nearest to the observation": an hourly series
    that ends before the observation time has no later truth to offer, and
    quietly reaching backwards for the first entry instead would misreport
    midnight conditions as current ones.
    """
    values = hourly.get(key)
    if not isinstance(values, list):
        return None
    for value in reversed(values):
        if value is not None:
            return float(value)
    return None


def _num(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse(payload: dict, lat: float, lon: float) -> EnvironmentContext:
    """Turn an upstream payload into a context, or an honest absence.

    A payload missing `current` entirely is UNAVAILABLE rather than a context of
    Nones: it means the response was not what we asked for, and a caller showing
    "no data" should be able to tell that apart from "data, all null".
    """
    current = payload.get("current")
    if not isinstance(current, dict) or "time" not in current:
        return EnvironmentContext.unavailable(
            lat, lon, "Open-Meteo response carried no 'current' block")

    fields: dict = {
        "observed_at": current.get("time"),
        "elevation_m": _num(payload.get("elevation")),
    }
    for upstream, field in CURRENT_MAP.items():
        fields[field] = _num(current.get(upstream))

    hourly = payload.get("hourly")
    if isinstance(hourly, dict):
        for upstream, field in HOURLY_MAP.items():
            fields[field] = _latest(hourly, upstream)

    return EnvironmentContext(latitude=lat, longitude=lon, status=STATUS_AVAILABLE,
                              source=SOURCE_OPEN_METEO, **fields)


def http_fetch(lat: float, lon: float, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """The real network call. Raises on transport failure; parse() handles shape."""
    import requests  # imported lazily so tests never need it at import time

    response = requests.get(build_url(lat, lon), timeout=timeout)
    response.raise_for_status()
    return response.json()


def get_environment(
    lat: float,
    lon: float,
    *,
    fetcher: Optional[Callable[[float, float], dict]] = None,
    cache: Optional[DiskCache] = None,
) -> EnvironmentContext:
    """Environmental context for a coordinate. Never raises; never invents.

    Resolution order: cache, then upstream. Failures become UNAVAILABLE with a
    reason and are deliberately NOT cached, so one bad minute cannot become an
    hour of false absence.
    """
    fetch = fetcher or http_fetch

    if cache is not None:
        cached = cache.get(lat, lon)
        if cached is not None:
            return cached

    try:
        payload = fetch(lat, lon)
    except Exception as exc:  # noqa: BLE001 - any upstream failure is UNAVAILABLE
        return EnvironmentContext.unavailable(lat, lon, f"{type(exc).__name__}: {exc}")

    if not isinstance(payload, dict):
        return EnvironmentContext.unavailable(
            lat, lon, f"Open-Meteo returned {type(payload).__name__}, expected an object")

    ctx = parse(payload, lat, lon)
    if cache is not None and ctx.available:
        cache.put(ctx)
    return ctx


def default_cache_dir() -> Path:
    """Project-local, gitignored alongside the rest of the runtime state."""
    return Path(__file__).resolve().parents[2] / "data" / "cache" / "environment"