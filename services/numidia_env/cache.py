"""On-disk cache for environmental readings.

Two decisions that matter more than they look:

1. Only SUCCESSFUL reads are cached. Caching a failure would pin UNAVAILABLE for
   the whole TTL after a single network blip, turning a momentary outage into an
   hour-long lie.

2. Coordinates are rounded to `PRECISION` decimals before keying (~110 m at 3 dp),
   so neighbouring fires in the same wilaya share an entry instead of each paying
   for its own request.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from .models import STATUS_AVAILABLE, EnvironmentContext

#: ~110 m. Fine enough to be honest about where a reading came from, coarse
#: enough that a cluster of fires in one valley shares one cache entry.
PRECISION = 3


class DiskCache:
    """TTL cache of EnvironmentContext, keyed by rounded coordinate."""

    def __init__(self, directory: Path | str, ttl_seconds: int = 3600):
        self.directory = Path(directory)
        self.ttl_seconds = ttl_seconds
        self.directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(lat: float, lon: float) -> str:
        return f"{round(lat, PRECISION):.{PRECISION}f}_{round(lon, PRECISION):.{PRECISION}f}"

    def _path(self, lat: float, lon: float) -> Path:
        return self.directory / f"{self._key(lat, lon)}.json"

    def get(self, lat: float, lon: float, now: Optional[float] = None) -> Optional[EnvironmentContext]:
        path = self._path(lat, lon)
        if not path.exists():
            return None
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt entry is a miss, not a failure: the caller refetches.
            return None
        stamp = blob.pop("_cached_at", None)
        if stamp is None:
            return None
        age = (now if now is not None else time.time()) - stamp
        # `>=`, not `>`: a ttl of 0 must mean "always expired". With `>`, an
        # entry written and read within the same clock tick has age 0, which
        # 0 > 0 rejects as fresh - so the cache silently served a stale hit for
        # a caller that asked for no caching at all.
        if age >= self.ttl_seconds:
            return None
        try:
            ctx = EnvironmentContext(**blob)
        except TypeError:
            return None
        # Never serve a cached UNAVAILABLE: it is only written defensively, and
        # serving one would outlast the condition that caused it.
        if ctx.status != STATUS_AVAILABLE:
            return None
        return ctx

    def put(self, ctx: EnvironmentContext, now: Optional[float] = None) -> None:
        if ctx.status != STATUS_AVAILABLE:
            return
        blob = ctx.to_dict()
        blob["_cached_at"] = now if now is not None else time.time()
        path = self._path(ctx.latitude, ctx.longitude)
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(blob), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            # A cache that cannot write must not break the caller.
            pass