"""Database module."""

from app.database.base import Base, BaseModel, TimestampMixin, utc_now
from app.database.session import engine, SessionLocal, get_session_factory, get_db
from app.database.models import (
    ProviderSource,
    Competition,
    Team,
    Player,
    Match,
    MatchEvent,
    Standing,
    MatchStatistic,
    LatencyLog,
)
from app.database.repository import (
    BaseRepository,
    ProviderSourceRepository,
    CompetitionRepository,
    TeamRepository,
    PlayerRepository,
    MatchRepository,
    MatchEventRepository,
    StandingRepository,
    MatchStatisticRepository,
    LatencyLogRepository,
)

__all__ = [
    # Base
    "Base",
    "BaseModel",
    "TimestampMixin",
    "utc_now",
    # Session
    "engine",
    "SessionLocal",
    "get_session_factory",
    "get_db",
    # Models
    "ProviderSource",
    "Competition",
    "Team",
    "Player",
    "Match",
    "MatchEvent",
    "Standing",
    "MatchStatistic",
    "LatencyLog",
    # Repositories
    "BaseRepository",
    "ProviderSourceRepository",
    "CompetitionRepository",
    "TeamRepository",
    "PlayerRepository",
    "MatchRepository",
    "MatchEventRepository",
    "StandingRepository",
    "MatchStatisticRepository",
    "LatencyLogRepository",
]
