"""Environmental context for Algerian wildfire incidents.

Real, keyless data from Open-Meteo (ERA5 reanalysis and GFS forecast), attached
to locations as display context. It does NOT feed `priority-v1`: that engine's
contract is SHA-pinned in the verifier artifact manifest and changing its inputs
would invalidate it. This is context a human reads, not a number the model
silently absorbed.

Anything unavailable is reported UNAVAILABLE with a reason. Nothing is filled in.
"""
from .cache import DiskCache
from .context import get_environment, http_fetch, parse
from .models import (
    SOURCE_OPEN_METEO,
    STATUS_AVAILABLE,
    STATUS_UNAVAILABLE,
    EnvironmentContext,
)

__all__ = [
    "EnvironmentContext",
    "DiskCache",
    "get_environment",
    "http_fetch",
    "parse",
    "STATUS_AVAILABLE",
    "STATUS_UNAVAILABLE",
    "SOURCE_OPEN_METEO",
]