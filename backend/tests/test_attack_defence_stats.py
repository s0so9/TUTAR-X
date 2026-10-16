"""Test for attack/defence statistical calculation fixes.

Verifies that:
1. xG and xGA are not double-counted when available in multiple sources
2. Each statistic uses its own appropriate denominator (sample size)
3. Missing values are not treated as zeros in averages
"""

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.database.models import Match, MatchStatistic, ProviderSource
from app.database.repository import MatchStatisticRepository
from app.features.attack_defence import AttackDefenceFeatureCalculator
from app.domain.enums import MatchStatus


@pytest.fixture
def provider_source(db_session: Session) -> ProviderSource:
    """Create a test provider source."""
    provider = ProviderSource(
        id=str(uuid.uuid4()),
        name="test-provider",
        is_active=True
    )
    db_session.add(provider)
    db_session.commit()
    return provider


def test_xga_not_double_counted(db_session: Session, provider_source: ProviderSource):
    """Test that xGA from match and statistics is not counted twice."""
    
    team_id = str(uuid.uuid4())
    opponent_id = str(uuid.uuid4())
    match_id = str(uuid.uuid4())
    
    # Create match with xGA in match object (away_xg when team is home)
    match = Match(
        id=match_id,
        provider_source_id=provider_source.id,
        provider_id="match-001",
        home_team_id=team_id,
        away_team_id=opponent_id,
        scheduled_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        status=MatchStatus.FINISHED,
        home_score=2,
        away_score=1,
        home_xg=1.8,
        away_xg=1.2,  # This is xGA for home team
    )
    db_session.add(match)
    
    # Create statistic with SAME xGA value
    stat = MatchStatistic(
        id=str(uuid.uuid4()),
        provider_source_id=provider_source.id,
        provider_id="stat-001",
        match_id=match_id,
        team_id=team_id,
        xg=1.8,
        xg_against=1.2,  # Same value as match.away_xg
    )
    db_session.add(stat)
    db_session.commit()
    
    # Calculate features
    calc = AttackDefenceFeatureCalculator(db_session, min_matches=1)
    features = calc.calculate_from_matches(
        matches=[match],
        team_id=team_id,
        before_datetime=datetime(2024, 1, 2, tzinfo=timezone.utc)
    )
    
    # xGA should be 1.2, not 2.4 (double counted)
    assert features.xga_per_match == pytest.approx(1.2, abs=0.01)
    assert features.xg_sample_size == 1  # Only counted once


def test_shots_on_target_separate_denominator(db_session: Session, provider_source: ProviderSource):
    """Test that shots_on_target uses its own sample size, not shots_total count."""
    
    team_id = str(uuid.uuid4())
    other_team_id = str(uuid.uuid4())
    
    # Create 3 matches with different data availability
    matches = []
    
    # Match 1: Has shots_total only
    match1_id = str(uuid.uuid4())
    match1 = Match(
        id=match1_id,
        provider_source_id=provider_source.id,
        provider_id="match-001",
        home_team_id=team_id,
        away_team_id=other_team_id,
        scheduled_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        status=MatchStatus.FINISHED,
        home_score=1,
        away_score=0,
    )
    stat1 = MatchStatistic(
        id=str(uuid.uuid4()),
        provider_source_id=provider_source.id,
        provider_id="stat-001",
        match_id=match1_id,
        team_id=team_id,
        shots_total=10,
        shots_on_target=None,  # Missing
    )
    matches.append(match1)
    db_session.add(match1)
    db_session.add(stat1)
    
    # Match 2: Has both
    match2_id = str(uuid.uuid4())
    match2 = Match(
        id=match2_id,
        provider_source_id=provider_source.id,
        provider_id="match-002",
        home_team_id=team_id,
        away_team_id=other_team_id,
        scheduled_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        status=MatchStatus.FINISHED,
        home_score=2,
        away_score=1,
    )
    stat2 = MatchStatistic(
        id=str(uuid.uuid4()),
        provider_source_id=provider_source.id,
        provider_id="stat-002",
        match_id=match2_id,
        team_id=team_id,
        shots_total=15,
        shots_on_target=6,
    )
    matches.append(match2)
    db_session.add(match2)
    db_session.add(stat2)
    
    # Match 3: Has shots_on_target only
    match3_id = str(uuid.uuid4())
    match3 = Match(
        id=match3_id,
        provider_source_id=provider_source.id,
        provider_id="match-003",
        home_team_id=team_id,
        away_team_id=other_team_id,
        scheduled_at=datetime(2024, 1, 3, tzinfo=timezone.utc),
        status=MatchStatus.FINISHED,
        home_score=0,
        away_score=0,
    )
    stat3 = MatchStatistic(
        id=str(uuid.uuid4()),
        provider_source_id=provider_source.id,
        provider_id="stat-003",
        match_id=match3_id,
        team_id=team_id,
        shots_total=None,  # Missing
        shots_on_target=4,
    )
    matches.append(match3)
    db_session.add(match3)
    db_session.add(stat3)
    
    db_session.commit()
    
    # Calculate features
    calc = AttackDefenceFeatureCalculator(db_session, min_matches=1)
    features = calc.calculate_from_matches(
        matches=matches,
        team_id=team_id,
        before_datetime=datetime(2024, 1, 4, tzinfo=timezone.utc)
    )
    
    # shots_per_match should be (10+15)/2 = 12.5 (only matches 1 and 2)
    assert features.shots_per_match == pytest.approx(12.5, abs=0.01)
    
    # shots_on_target_per_match should be (6+4)/2 = 5.0 (only matches 2 and 3)
    assert features.shots_on_target_per_match == pytest.approx(5.0, abs=0.01)


def test_missing_xg_returns_none_not_zero(db_session: Session, provider_source: ProviderSource):
    """Test that when no xG data exists, xg_per_match is None, not 0.0."""
    
    team_id = str(uuid.uuid4())
    other_team_id = str(uuid.uuid4())
    
    # Create matches without xG data
    matches = []
    for i in range(5):
        match = Match(
            id=str(uuid.uuid4()),
            provider_source_id=provider_source.id,
            provider_id=f"match-{i}",
            home_team_id=team_id,
            away_team_id=other_team_id,
            scheduled_at=datetime(2024, 1, i+1, tzinfo=timezone.utc),
            status=MatchStatus.FINISHED,
            home_score=1,
            away_score=0,
            # No xG data
        )
        matches.append(match)
        db_session.add(match)
    
    db_session.commit()
    
    # Calculate features
    calc = AttackDefenceFeatureCalculator(db_session, min_matches=1)
    features = calc.calculate_from_matches(
        matches=matches,
        team_id=team_id,
        before_datetime=datetime(2024, 1, 10, tzinfo=timezone.utc)
    )
    
    # xG should be None (unavailable), not 0.0
    assert features.xg_per_match is None
    assert features.xga_per_match is None
    assert features.xg_sample_size == 0
    
    # But goals should still be calculated
    assert features.goals_per_match == pytest.approx(1.0)


def test_xg_only_counted_once_per_match(db_session: Session, provider_source: ProviderSource):
    """Test that xG is counted once even when in both match and statistics."""
    
    team_id = str(uuid.uuid4())
    other_team_id = str(uuid.uuid4())
    
    # Create 2 matches with xG in both sources
    matches = []
    
    for i in range(2):
        match_id = str(uuid.uuid4())
        match = Match(
            id=match_id,
            provider_source_id=provider_source.id,
            provider_id=f"match-{i}",
            home_team_id=team_id,
            away_team_id=other_team_id,
            scheduled_at=datetime(2024, 1, i+1, tzinfo=timezone.utc),
            status=MatchStatus.FINISHED,
            home_score=2,
            away_score=1,
            home_xg=1.5 + i * 0.1,  # 1.5, 1.6
            away_xg=0.8,
        )
        matches.append(match)
        db_session.add(match)
        
        # Add statistics with SAME xG values
        stat = MatchStatistic(
            id=str(uuid.uuid4()),
            provider_source_id=provider_source.id,
            provider_id=f"stat-{i}",
            match_id=match_id,
            team_id=team_id,
            xg=1.5 + i * 0.1,  # Should not be counted again
            xg_against=0.8,
        )
        db_session.add(stat)
    
    db_session.commit()
    
    # Calculate features
    calc = AttackDefenceFeatureCalculator(db_session, min_matches=1)
    features = calc.calculate_from_matches(
        matches=matches,
        team_id=team_id,
        before_datetime=datetime(2024, 1, 10, tzinfo=timezone.utc)
    )
    
    # xG should be (1.5 + 1.6) / 2 = 1.55, not doubled
    assert features.xg_per_match == pytest.approx(1.55, abs=0.01)
    assert features.xg_sample_size == 2
    
    # xGA should be 0.8, not 1.6
    assert features.xga_per_match == pytest.approx(0.8, abs=0.01)


def test_valid_zero_values_not_lost(db_session: Session, provider_source: ProviderSource):
    """Test that legitimate zero values (e.g., 0 shots on target) are preserved."""
    
    team_id = str(uuid.uuid4())
    other_team_id = str(uuid.uuid4())
    match_id = str(uuid.uuid4())
    
    match = Match(
        id=match_id,
        provider_source_id=provider_source.id,
        provider_id="match-001",
        home_team_id=team_id,
        away_team_id=other_team_id,
        scheduled_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        status=MatchStatus.FINISHED,
        home_score=0,  # Valid zero
        away_score=3,
    )
    db_session.add(match)
    
    stat = MatchStatistic(
        id=str(uuid.uuid4()),
        provider_source_id=provider_source.id,
        provider_id="stat-001",
        match_id=match_id,
        team_id=team_id,
        shots_total=8,
        shots_on_target=0,  # Valid zero - all shots off target
    )
    db_session.add(stat)
    db_session.commit()
    
    # Calculate features
    calc = AttackDefenceFeatureCalculator(db_session, min_matches=1)
    features = calc.calculate_from_matches(
        matches=[match],
        team_id=team_id,
        before_datetime=datetime(2024, 1, 2, tzinfo=timezone.utc)
    )
    
    # Zero goals should be preserved
    assert features.goals_per_match == pytest.approx(0.0)
    
    # Zero shots on target should be preserved (not treated as missing)
    assert features.shots_on_target_per_match == pytest.approx(0.0)
    assert features.shots_per_match == pytest.approx(8.0)
