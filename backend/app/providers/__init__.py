"""Data provider module."""

from app.providers.base import FootballDataProvider
from app.providers.development import DevelopmentProvider
from app.providers.ryzellx import RyzellxFootballProvider
from app.providers.fotmob import FotMobFootballProvider
from app.providers.openligadb import OpenLigaDBFootballProvider
from app.providers.sofascore import SofaScoreFootballProvider
from app.providers.manager import ProviderManager
from app.providers.adapter import ProviderManagerAdapter
from app.providers.database_adapter import DatabaseBackedProvider
from app.providers.hybrid_provider import HybridProvider
from app.providers.data_quality import DataQualityEngine
from app.providers.source_intelligence import SourceIntelligence
from app.providers.exceptions import (
    ProviderError,
    ProviderTimeoutError,
    ProviderHTTPError,
    ProviderInvalidDataError,
    ProviderNotFoundError,
)
from app.providers.cache import ProviderCache
from app.providers.models import (
    ProviderMetadata,
    ProviderCompetition,
    ProviderTeam,
    ProviderPlayer,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderLineup,
    ProviderMatchStats,
    ProviderShot,
    ProviderStanding,
    ProviderLiveMatch,
)

__all__ = [
    # Base provider
    "FootballDataProvider",
    "DevelopmentProvider",
    # Multi-provider implementations
    "RyzellxFootballProvider",
    "FotMobFootballProvider",
    "OpenLigaDBFootballProvider",
    "SofaScoreFootballProvider",
    "ProviderManager",
    "ProviderManagerAdapter",
    "DatabaseBackedProvider",
    "HybridProvider",
    # Data quality
    "DataQualityEngine",
    # Source intelligence
    "SourceIntelligence",
    # Exceptions
    "ProviderError",
    "ProviderTimeoutError",
    "ProviderHTTPError",
    "ProviderInvalidDataError",
    "ProviderNotFoundError",
    # Cache
    "ProviderCache",
    # Normalized models
    "ProviderMetadata",
    "ProviderCompetition",
    "ProviderTeam",
    "ProviderPlayer",
    "ProviderMatch",
    "ProviderMatchEvent",
    "ProviderLineup",
    "ProviderMatchStats",
    "ProviderShot",
    "ProviderStanding",
    "ProviderLiveMatch",
]

