"""Sonarr / Radarr v3 compatible API (``/sonarr/api/v3`` and ``/radarr/api/v3``)."""
from .base import VERSIONS, radarr_router, sonarr_router
from .common import _register_common
from .radarr import _register_radarr
from .sonarr import _register_sonarr
from .arrconfig import register_arrconfig

_register_common(sonarr_router, "sonarr")
_register_common(radarr_router, "radarr")
_register_radarr(radarr_router)
_register_sonarr(sonarr_router)
register_arrconfig(sonarr_router, "sonarr")
register_arrconfig(radarr_router, "radarr")

__all__ = ["VERSIONS", "radarr_router", "sonarr_router"]
