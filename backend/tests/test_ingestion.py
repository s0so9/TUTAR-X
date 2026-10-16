"""Tests for ingestion layer."""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.providers.models import ProviderMatch, ProviderMatchStats
from app.ingestion.match_ingestion import MatchIngester
from app.ingestion.deduplication import DeduplicationChecker
from app.database.repository import MatchRepository, ProviderSourceRepository
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


class TestDeduplicationChecker:
    """Test deduplication logic."""
    
    def test_should_preserve_field_when_existing_not_none_new_none(self):
        """Test that should_preserve_field returns True when existing is not None and new is None."""
        checker = DeduplicationChecker()
        result = checker.should_preserve_field(
            existing_value=2.5,
            new_value=None
        )
        assert result is True
    
    def test_should_not_preserve_when_both_not_none(self):
        """Test that should_preserve_field returns False when both values are not None."""
        checker = DeduplicationChecker()
        result = checker.should_preserve_field(
            existing_value=2.5,
            new_value=3.0
        )
        assert result is False
    
    def test_should_not_preserve_when_existing_none(self):
        """Test that should_preserve_field returns False when existing is None."""
        checker = DeduplicationChecker()
        result = checker.should_preserve_field(
            existing_value=None,
            new_value=2.5
        )
        assert result is False


class TestMatchIngester:
    """Test match ingestion."""
    
    def test_ingest_match_creates_new_match(self, db_session):
        """Test ingesting a new match creates database records."""
        ingester = MatchIngester(db_session)
        
        provider_match = ProviderMatch(
            provider="ryzellx",
            source_id="match_123",
            fetched_at=datetime.now(timezone.utc),
            home_team_id="team_home",
            home_team_name="Arsenal",
            away_team_id="team_away",
            away_team_name="Chelsea",
            scheduled_at=datetime(2024, 1, 15, 15, 0, tzinfo=timezone.utc),
            status=MatchStatus.SCHEDULED,
        )
        
        match = ingester.ingest_match(provider_match)
        db_session.commit()
        
        assert match.id is not None
        assert match.provider_id == "match_123"
        assert match.status == MatchStatus.SCHEDULED
    
    def test_ingest_match_updates_existing(self, db_session):
        """Test ingesting same match twice updates it."""
        ingester = MatchIngester(db_session)
        
        # First ingest
        provider_match1 = ProviderMatch(
            provider="ryzellx",
            source_id="match_123",
            fetched_at=datetime.now(timezone.utc),
            home_team_id="team_home",
            home_team_name="Arsenal",
            away_team_id="team_away",
            away_team_name="Chelsea",
            scheduled_at=datetime(2024, 1, 15, 15, 0, tzinfo=timezone.utc),
            status=MatchStatus.SCHEDULED,
        )
        match1 = ingester.ingest_match(provider_match1)
        db_session.commit()
        match1_id = match1.id
        
        # Second ingest with updated status
        provider_match2 = ProviderMatch(
            provider="ryzellx",
            source_id="match_123",
            fetched_at=datetime.now(timezone.utc),
            home_team_id="team_home",
            home_team_name="Arsenal",
            away_team_id="team_away",
            away_team_name="Chelsea",
            scheduled_at=datetime(2024, 1, 15, 15, 0, tzinfo=timezone.utc),
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=1,
            outcome=MatchOutcome.HOME_WIN,
        )
        match2 = ingester.ingest_match(provider_match2)
        db_session.commit()
        
        # Should be same match, updated
        assert match2.id == match1_id
        assert match2.status == MatchStatus.FINISHED
        assert match2.home_score == 2
        assert match2.away_score == 1
    
    def test_ingest_match_preserves_xg_when_new_is_none(self, db_session):
        """Test that ingestion never overwrites valid xG with None."""
        ingester = MatchIngester(db_session)
        
        # First ingest with xG data
        provider_match1 = ProviderMatch(
            provider="ryzellx",
            source_id="match_123",
            fetched_at=datetime.now(timezone.utc),
            home_team_id="team_home",
            home_team_name="Arsenal",
            away_team_id="team_away",
            away_team_name="Chelsea",
            scheduled_at=datetime(2024, 1, 15, 15, 0, tzinfo=timezone.utc),
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=1,
        )
        
        # Manually set xG in database
        match1 = ingester.ingest_match(provider_match1)
        match1.home_xg = 2.3
        match1.away_xg = 1.1
        db_session.commit()
        
        # Second ingest without xG (None values)
        provider_match2 = ProviderMatch(
            provider="ryzellx",
            source_id="match_123",
            fetched_at=datetime.now(timezone.utc),
            home_team_id="team_home",
            home_team_name="Arsenal",
            away_team_id="team_away",
            away_team_name="Chelsea",
            scheduled_at=datetime(2024, 1, 15, 15, 0, tzinfo=timezone.utc),
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=1,
        )
        match2 = ingester.ingest_match(provider_match2)
        db_session.commit()
        
        # xG should be preserved (not overwritten with None)
        db_session.refresh(match2)
        assert match2.home_xg == 2.3
        assert match2.away_xg == 1.1
    
    def test_ingest_match_stats_preserves_xg(self, db_session):
        """Test that match statistics ingestion preserves xG."""
        ingester = MatchIngester(db_session)
        
        # Create a match first
        provider_match = ProviderMatch(
            provider="ryzellx",
            source_id="match_123",
            fetched_at=datetime.now(timezone.utc),
            home_team_id="team_home",
            home_team_name="Arsenal",
            away_team_id="team_away",
            away_team_name="Chelsea",
            scheduled_at=datetime(2024, 1, 15, 15, 0, tzinfo=timezone.utc),
            status=MatchStatus.FINISHED,
        )
        match = ingester.ingest_match(provider_match)
        db_session.commit()
        
        # Ingest stats with xG
        provider_stats1 = ProviderMatchStats(
            provider="ryzellx",
            source_id="stats_home_123",
            fetched_at=datetime.now(timezone.utc),
            match_id="match_123",
            team_id="team_home",
            team_name="Arsenal",
            xg=2.5,
            shots_total=15,
        )
        stats1 = ingester.ingest_match_stats(provider_stats1, match_db_id=match.id)
        db_session.commit()
        
        # Ingest stats again with xG=None
        provider_stats2 = ProviderMatchStats(
            provider="ryzellx",
            source_id="stats_home_123",
            fetched_at=datetime.now(timezone.utc),
            match_id="match_123",
            team_id="team_home",
            team_name="Arsenal",
            xg=None,  # Missing in this update
            shots_total=15,
        )
        stats2 = ingester.ingest_match_stats(provider_stats2, match_db_id=match.id)
        db_session.commit()
        
        # xG should be preserved
        db_session.refresh(stats2)
        assert stats2.xg == 2.5
    
    def test_different_providers_create_separate_matches(self, db_session):
        """Test that same match ID from different providers creates separate records."""
        ingester = MatchIngester(db_session)
        
        # Match from ryzellx
        provider_match1 = ProviderMatch(
            provider="ryzellx",
            source_id="match_123",
            fetched_at=datetime.now(timezone.utc),
            home_team_id="team_home",
            home_team_name="Arsenal",
            away_team_id="team_away",
            away_team_name="Chelsea",
            scheduled_at=datetime(2024, 1, 15, 15, 0, tzinfo=timezone.utc),
            status=MatchStatus.SCHEDULED,
        )
        match1 = ingester.ingest_match(provider_match1)
        db_session.commit()
        
        # Same match ID from fotmob
        provider_match2 = ProviderMatch(
            provider="fotmob",
            source_id="match_123",
            fetched_at=datetime.now(timezone.utc),
            home_team_id="team_home",
            home_team_name="Arsenal",
            away_team_id="team_away",
            away_team_name="Chelsea",
            scheduled_at=datetime(2024, 1, 15, 15, 0, tzinfo=timezone.utc),
            status=MatchStatus.SCHEDULED,
        )
        match2 = ingester.ingest_match(provider_match2)
        db_session.commit()
        
        # Should be different database records
        assert match1.id != match2.id
        assert match1.provider_source.name == "ryzellx"
        assert match2.provider_source.name == "fotmob"
    
    def test_ingest_match_preserves_all_fields_from_none_overwrite(self, db_session):
        """Test that ALL fields are protected from None-overwrite, not just preserve_fields.
        
        This test verifies the fix for the critical bug where fields outside PRESERVE_MATCH_FIELDS
        (like venue_name, round, season) were being overwritten with None.
        """
        ingester = MatchIngester(db_session)
        
        # First ingest with full data including venue_name, round, season
        provider_match1 = ProviderMatch(
            provider="ryzellx",
            source_id="match_123",
            fetched_at=datetime.now(timezone.utc),
            home_team_id="team_home",
            home_team_name="Arsenal",
            away_team_id="team_away",
            away_team_name="Chelsea",
            scheduled_at=datetime(2024, 1, 15, 15, 0, tzinfo=timezone.utc),
            status=MatchStatus.SCHEDULED,
            venue_name="Emirates Stadium",
            round=4,  # Matchweek 4
            season="2023/24",
            minute=None,
        )
        match1 = ingester.ingest_match(provider_match1)
        db_session.commit()
        
        # Verify initial data
        assert match1.venue_name == "Emirates Stadium"
        assert match1.round == 4
        assert match1.season == "2023/24"
        
        # Second ingest with these fields missing (None)
        provider_match2 = ProviderMatch(
            provider="ryzellx",
            source_id="match_123",
            fetched_at=datetime.now(timezone.utc),
            home_team_id="team_home",
            home_team_name="Arsenal",
            away_team_id="team_away",
            away_team_name="Chelsea",
            scheduled_at=datetime(2024, 1, 15, 15, 0, tzinfo=timezone.utc),
            status=MatchStatus.LIVE,  # Updated status
            venue_name=None,  # Missing in this update
            round=None,  # Missing in this update
            season=None,  # Missing in this update
            minute=45,  # New data
        )
        match2 = ingester.ingest_match(provider_match2)
        db_session.commit()
        
        # Critical test: venue_name, round, season should be preserved (NOT overwritten with None)
        db_session.refresh(match2)
        assert match2.venue_name == "Emirates Stadium", "venue_name should not be overwritten with None"
        assert match2.round == 4, "round should not be overwritten with None"
        assert match2.season == "2023/24", "season should not be overwritten with None"
        
        # But new non-None values should be updated
        assert match2.status == MatchStatus.LIVE, "status should be updated"
        assert match2.minute == 45, "minute should be updated"

