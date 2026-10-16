"""Tests for database layer."""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base, TimestampMixin, utc_now
from app.database.models import (
    ProviderSource,
    Competition,
    Team,
    Match,
    MatchEvent,
    Standing,
    MatchStatistic,
)
from app.database.repository import (
    ProviderSourceRepository,
    CompetitionRepository,
    TeamRepository,
    MatchRepository,
)
from app.domain.enums import MatchStatus, MatchOutcome


@pytest.fixture
def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def provider_source(db_session):
    """Create a test provider source."""
    repo = ProviderSourceRepository(db_session)
    source = repo.get_or_create_by_name(
        name="ryzellx",
        base_url="https://test.com"
    )
    db_session.commit()
    return source


class TestBase:
    """Test base classes and utilities."""
    
    def test_base_model_creates_uuid_id(self, db_session, provider_source):
        """Test that BaseModel creates UUID primary keys."""
        team = Team(
            provider_source_id=provider_source.id,
            provider_id="team_123",
            name="Test Team",
        )
        db_session.add(team)
        db_session.commit()
        
        assert team.id is not None
        assert len(team.id) == 36  # UUID format
    
    def test_timestamp_mixin_sets_created_at(self, db_session, provider_source):
        """Test that TimestampMixin sets created_at on creation."""
        team = Team(
            provider_source_id=provider_source.id,
            provider_id="team_123",
            name="Test Team",
        )
        db_session.add(team)
        db_session.commit()
        
        assert team.created_at is not None
        assert isinstance(team.created_at, datetime)
    
    def test_timestamp_mixin_sets_updated_at(self, db_session, provider_source):
        """Test that TimestampMixin sets updated_at on creation."""
        team = Team(
            provider_source_id=provider_source.id,
            provider_id="team_123",
            name="Test Team",
        )
        db_session.add(team)
        db_session.commit()
        
        assert team.updated_at is not None
        assert isinstance(team.updated_at, datetime)
    
    def test_utc_now_returns_utc_datetime(self):
        """Test that utc_now returns UTC datetime."""
        now = utc_now()
        assert now.tzinfo == timezone.utc


class TestProviderSourceRepository:
    """Test ProviderSourceRepository."""
    
    def test_get_or_create_by_name_creates_new(self, db_session):
        """Test creating a new provider source."""
        repo = ProviderSourceRepository(db_session)
        source = repo.get_or_create_by_name(
            name="fotmob",
            base_url="https://www.fotmob.com"
        )
        db_session.commit()
        
        assert source.id is not None
        assert source.name == "fotmob"
        assert source.base_url == "https://www.fotmob.com"
        assert source.is_active is True
    
    def test_get_or_create_by_name_gets_existing(self, db_session):
        """Test getting existing provider source."""
        repo = ProviderSourceRepository(db_session)
        
        # Create first time
        source1 = repo.get_or_create_by_name(name="ryzellx")
        db_session.commit()
        source1_id = source1.id
        
        # Get second time
        source2 = repo.get_or_create_by_name(name="ryzellx")
        db_session.commit()
        
        assert source2.id == source1_id
        assert source2.name == "ryzellx"


class TestBaseRepository:
    """Test BaseRepository upsert functionality."""
    
    def test_upsert_by_provider_id_creates_new(self, db_session, provider_source):
        """Test that upsert creates new entity when it doesn't exist."""
        repo = TeamRepository(db_session)
        
        team = repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id="team_123",
            data={
                "name": "Arsenal",
                "short_name": "ARS",
                "country": "England",
            }
        )
        db_session.commit()
        
        assert team.id is not None
        assert team.name == "Arsenal"
        assert team.short_name == "ARS"
        assert team.country == "England"
    
    def test_upsert_by_provider_id_updates_existing(self, db_session, provider_source):
        """Test that upsert updates existing entity."""
        repo = TeamRepository(db_session)
        
        # Create first time
        team1 = repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id="team_123",
            data={
                "name": "Arsenal",
                "short_name": "ARS",
            }
        )
        db_session.commit()
        team1_id = team1.id
        created_at = team1.created_at
        
        # Update second time
        team2 = repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id="team_123",
            data={
                "name": "Arsenal FC",
                "short_name": "Arsenal",
                "country": "England",
            }
        )
        db_session.commit()
        
        # Should be same entity
        assert team2.id == team1_id
        # created_at should be preserved
        assert team2.created_at == created_at
        # updated_at should be newer
        assert team2.updated_at > created_at
        # Data should be updated
        assert team2.name == "Arsenal FC"
        assert team2.short_name == "Arsenal"
        assert team2.country == "England"
    
    def test_upsert_preserves_non_none_fields(self, db_session, provider_source):
        """Test that upsert never overwrites non-None with None."""
        repo = TeamRepository(db_session)
        
        # Create with country
        team1 = repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id="team_123",
            data={
                "name": "Arsenal",
                "country": "England",
                "founded": 1886,
            },
            preserve_fields=["country", "founded"]
        )
        db_session.commit()
        
        # Update with None country (should preserve)
        team2 = repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id="team_123",
            data={
                "name": "Arsenal FC",
                "country": None,
                "founded": None,
            },
            preserve_fields=["country", "founded"]
        )
        db_session.commit()
        
        # country and founded should be preserved
        assert team2.country == "England"
        assert team2.founded == 1886
        # name should be updated (not in preserve_fields)
        assert team2.name == "Arsenal FC"
    
    def test_get_by_provider_id(self, db_session, provider_source):
        """Test retrieving entity by provider ID."""
        repo = TeamRepository(db_session)
        
        # Create entity
        team = repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id="team_456",
            data={"name": "Chelsea"}
        )
        db_session.commit()
        
        # Retrieve by provider ID
        found = repo.get_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id="team_456"
        )
        
        assert found is not None
        assert found.id == team.id
        assert found.name == "Chelsea"
    
    def test_different_providers_same_id_creates_separate_records(self, db_session):
        """Test that same provider_id from different providers creates separate records."""
        # Create two provider sources
        source_repo = ProviderSourceRepository(db_session)
        ryzellx = source_repo.get_or_create_by_name("ryzellx")
        fotmob = source_repo.get_or_create_by_name("fotmob")
        db_session.commit()
        
        team_repo = TeamRepository(db_session)
        
        # Create team from ryzellx
        team1 = team_repo.upsert_by_provider_id(
            provider_source_id=ryzellx.id,
            provider_id="team_123",
            data={"name": "Arsenal (Ryzellx)"}
        )
        db_session.commit()
        
        # Create team with same provider_id from fotmob
        team2 = team_repo.upsert_by_provider_id(
            provider_source_id=fotmob.id,
            provider_id="team_123",
            data={"name": "Arsenal (FotMob)"}
        )
        db_session.commit()
        
        # Should be different entities
        assert team1.id != team2.id
        assert team1.name == "Arsenal (Ryzellx)"
        assert team2.name == "Arsenal (FotMob)"


class TestMatchRepository:
    """Test MatchRepository queries."""
    
    def test_get_team_matches_before_date(self, db_session, provider_source):
        """Test retrieving team matches before a specific date."""
        # Create teams
        team_repo = TeamRepository(db_session)
        home_team = team_repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id="team_home",
            data={"name": "Home Team"}
        )
        away_team = team_repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id="team_away",
            data={"name": "Away Team"}
        )
        db_session.commit()
        
        # Create matches
        match_repo = MatchRepository(db_session)
        
        # Match 1: 2024-01-01 (finished)
        match1 = match_repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id="match_1",
            data={
                "home_team_id": home_team.id,
                "away_team_id": away_team.id,
                "scheduled_at": datetime(2024, 1, 1, 15, 0, tzinfo=timezone.utc),
                "status": MatchStatus.FINISHED,
                "home_score": 2,
                "away_score": 1,
                "outcome": MatchOutcome.HOME_WIN,
            }
        )
        
        # Match 2: 2024-01-10 (finished)
        match2 = match_repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id="match_2",
            data={
                "home_team_id": home_team.id,
                "away_team_id": away_team.id,
                "scheduled_at": datetime(2024, 1, 10, 15, 0, tzinfo=timezone.utc),
                "status": MatchStatus.FINISHED,
                "home_score": 1,
                "away_score": 1,
                "outcome": MatchOutcome.DRAW,
            }
        )
        
        # Match 3: 2024-01-20 (scheduled, future)
        match3 = match_repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id="match_3",
            data={
                "home_team_id": home_team.id,
                "away_team_id": away_team.id,
                "scheduled_at": datetime(2024, 1, 20, 15, 0, tzinfo=timezone.utc),
                "status": MatchStatus.SCHEDULED,
            }
        )
        db_session.commit()
        
        # Query matches before 2024-01-15 (should get match1 and match2, not match3)
        before_date = datetime(2024, 1, 15, tzinfo=timezone.utc)
        matches = match_repo.get_team_matches_before_date(
            team_id=home_team.id,
            before_datetime=before_date,
            finished_only=True
        )
        
        assert len(matches) == 2
        assert matches[0].id == match1.id
        assert matches[1].id == match2.id
        # Verify chronological order
        assert matches[0].scheduled_at < matches[1].scheduled_at
    
    def test_get_team_matches_no_future_leakage(self, db_session, provider_source):
        """Test that future matches are never included (data leakage prevention)."""
        # Create team
        team_repo = TeamRepository(db_session)
        team = team_repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id="team_1",
            data={"name": "Test Team"}
        )
        db_session.commit()
        
        # Create historical match
        match_repo = MatchRepository(db_session)
        historical = match_repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id="match_hist",
            data={
                "home_team_id": team.id,
                "away_team_id": team.id,
                "scheduled_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "status": MatchStatus.FINISHED,
            }
        )
        
        # Create future match
        future = match_repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id="match_future",
            data={
                "home_team_id": team.id,
                "away_team_id": team.id,
                "scheduled_at": datetime(2024, 1, 20, tzinfo=timezone.utc),
                "status": MatchStatus.FINISHED,
            }
        )
        db_session.commit()
        
        # Query matches before 2024-01-10 (between historical and future)
        target_date = datetime(2024, 1, 10, tzinfo=timezone.utc)
        matches = match_repo.get_team_matches_before_date(
            team_id=team.id,
            before_datetime=target_date,
            finished_only=True
        )
        
        # Should only get historical match, not future
        assert len(matches) == 1
        assert matches[0].id == historical.id
