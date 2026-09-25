"""Sentinel-2 verification foundation: provider abstraction + interfaces.

Pipeline vision (not yet executable end-to-end):
FIRMS detection -> geographic/time query -> Sentinel-2 scene discovery ->
image/patch retrieval -> preprocessing -> visual model -> verification evidence.

What exists today: the interface, the query/metadata types, an UNAVAILABLE
provider (no credentials/API access configured) and a metadata fixture
provider for integration tests. The fixture provider is TEST ONLY and is
never used outside tests. No visual model is registered; nothing here claims
production readiness.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field


class ProviderUnavailable(RuntimeError):
    """Raised when the provider cannot serve (no credentials, no access)."""


@dataclass(frozen=True)
class SceneQuery:
    """Geographic/time query derived from a FIRMS detection."""
    lat: float
    lon: float
    start_date: str   # YYYY-MM-DD inclusive
    end_date: str     # YYYY-MM-DD inclusive
    max_cloud_pct: float = 20.0
    radius_km: float = 5.0


@dataclass(frozen=True)
class SceneMetadata:
    scene_id: str
    satellite: str = "Sentinel-2"
    sensing_date: str = ""
    cloud_cover_pct: float | None = None
    bbox: tuple[float, float, float, float] | None = None  # lon_min,lat_min,lon_max,lat_max
    source: str = ""
    fixture: bool = False
    test_only: bool = False


@dataclass
class PatchRequest:
    scene_id: str
    lat: float
    lon: float
    size_px: int = 128
    bands: tuple[str, ...] = ("B04", "B03", "B02", "B8A")


@dataclass
class VerificationEvidenceDraft:
    detection_id: str
    scene_id: str
    preprocessing: list[str] = field(default_factory=list)
    model: str | None = None
    model_version: str | None = None
    note: str = ""


class SentinelProvider(ABC):
    """Interface every Sentinel-2 backend must implement."""

    @abstractmethod
    def discover(self, query: SceneQuery) -> list[SceneMetadata]:
        """Return candidate scenes for the query (metadata only)."""

    @abstractmethod
    def fetch_patch(self, request: PatchRequest) -> bytes:
        """Return a preprocessed image patch (bytes). Unavailable until wired."""

    @property
    @abstractmethod
    def status(self) -> dict:
        """Provider availability report (honest, no fake readiness)."""


class UnavailableSentinelProvider(SentinelProvider):
    """Default provider: no credentials/API access configured."""

    def __init__(self, reason: str = "no Sentinel-2 credentials or API access configured"):
        self._reason = reason

    def discover(self, query: SceneQuery) -> list[SceneMetadata]:
        raise ProviderUnavailable(self._reason)

    def fetch_patch(self, request: PatchRequest) -> bytes:
        raise ProviderUnavailable(self._reason)

    @property
    def status(self) -> dict:
        return {"data_available": False, "status": "UNAVAILABLE",
                "provider": "sentinel-2", "reason": self._reason}


class FixtureSentinelProvider(SentinelProvider):
    """TEST ONLY metadata fixture provider. Never used outside tests."""

    FIXTURE_SCENES = (
        SceneMetadata(
            scene_id="TEST-ONLY-S2A-20210101T000000",
            sensing_date="2021-01-01",
            cloud_cover_pct=5.0,
            bbox=(3.0, 36.5, 3.2, 36.7),
            source="TEST FIXTURE - not a real scene",
            fixture=True, test_only=True,
        ),
    )

    def discover(self, query: SceneQuery) -> list[SceneMetadata]:
        scenes = [s for s in self.FIXTURE_SCENES
                  if s.bbox and s.bbox[0] <= query.lon <= s.bbox[2]
                  and s.bbox[1] <= query.lat <= s.bbox[3]]
        return [SceneMetadata(**{**asdict(s)}) for s in scenes]

    def fetch_patch(self, request: PatchRequest) -> bytes:
        raise ProviderUnavailable("fixture provider carries metadata only (TEST ONLY)")

    @property
    def status(self) -> dict:
        return {"data_available": False, "status": "UNAVAILABLE",
                "provider": "sentinel-2-fixture", "test_only": True,
                "reason": "metadata fixture for integration tests only"}


def get_provider() -> SentinelProvider:
    """Production factory: unavailable until credentials/API access exist."""
    return UnavailableSentinelProvider()
