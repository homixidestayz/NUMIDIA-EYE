"""Environmental context for a location, and nothing more.

The type in this module is deliberately incapable of representing a guess. Every
measurement is Optional, the default status is UNAVAILABLE, and the only way to
get a number is for the upstream API to have returned one. There is no
constructor argument that sets a default, no zero-fill, and no interpolation
across a gap - because a plausible-looking wind speed or soil moisture value that
nobody measured is exactly the kind of thing that ends up steering an evacuation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Optional

#: The upstream returned real values.
STATUS_AVAILABLE = "AVAILABLE"

#: The upstream did not, or could not. Every measurement is None and `reason` says why.
STATUS_UNAVAILABLE = "UNAVAILABLE"

#: Stated once, reused, never interpolated silently.
SOURCE_OPEN_METEO = "open-meteo"


@dataclass(frozen=True)
class EnvironmentContext:
    """One location's environmental reading, or a truthful absence.

    Frozen so a cached instance cannot be mutated in place by one consumer and
    then served to another.
    """

    latitude: float
    longitude: float
    status: str = STATUS_UNAVAILABLE
    source: Optional[str] = None
    observed_at: Optional[str] = None
    elevation_m: Optional[float] = None

    temperature_2m_c: Optional[float] = None
    relative_humidity_2m_pct: Optional[float] = None
    wind_speed_10m_ms: Optional[float] = None
    wind_direction_10m_deg: Optional[float] = None
    wind_gusts_10m_ms: Optional[float] = None
    precipitation_mm: Optional[float] = None

    soil_moisture_0_1_m3_m3: Optional[float] = None
    soil_moisture_3_9_m3_m3: Optional[float] = None
    soil_moisture_9_27_m3_m3: Optional[float] = None
    soil_temperature_0_7_c: Optional[float] = None
    soil_temperature_7_28_c: Optional[float] = None

    #: Why this is UNAVAILABLE. Never empty when status is UNAVAILABLE.
    reason: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.status == STATUS_AVAILABLE

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def unavailable(cls, latitude: float, longitude: float, reason: str,
                    source: Optional[str] = SOURCE_OPEN_METEO) -> "EnvironmentContext":
        """The only sane way to build a failed lookup: every field stays None."""
        if not reason:
            raise ValueError("an UNAVAILABLE context must carry a reason")
        return cls(latitude=latitude, longitude=longitude,
                   status=STATUS_UNAVAILABLE, source=source, reason=reason)


#: Measurement fields, i.e. everything except identity and bookkeeping.
MEASUREMENT_FIELDS = tuple(
    f.name for f in fields(EnvironmentContext)
    if f.name not in ("latitude", "longitude", "status", "source",
                      "observed_at", "elevation_m", "reason")
)