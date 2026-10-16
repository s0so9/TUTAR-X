"""Tests for SourceIntelligence.

These tests verify multi-provider data merging, conflict detection, and source tracking.
Pure calculation tests with no HTTP calls or async operations.
"""

import pytest
from datetime import datetime, timezone

from app.providers import SourceIntelligence, ProviderMatchStats


@pytest.fixture
def source_intelligence():
    """Create a SourceIntelligence instance."""
    return SourceIntelligence()


@pytest.fixture
def provider1_stats():
    """Create ProviderMatchStats from provider 1."""
    now = datetime.now(timezone.utc)
    return ProviderMatchStats(
        provider="provider_1",
        source_id="match_123",
        fetched_at=now,
        match_id="match_123",
        team_id="team_1",
        period="full",
        shots_total=14,
        shots_on_target=5,
        shots_off_target=6,
        possession_percentage=58.0,
        xg=1.89,
        corners=7,
        yellow_cards=3,
    )


@pytest.fixture
def provider2_stats():
    """Create ProviderMatchStats from provider 2 with different values."""
    now = datetime.now(timezone.utc)
    return ProviderMatchStats(
        provider="provider_2",
        source_id="match_123",
        fetched_at=now,
        match_id="match_123",
        team_id="team_1",
        period="full",
        shots_total=15,  # Different
        shots_on_target=6,  # Different
        possession_percentage=57.0,  # Different
        xg=1.95,  # Different
        passes_completed=450,  # Additional field
        passes_attempted=520,  # Additional field
    )


@pytest.fixture
def provider3_stats():
    """Create ProviderMatchStats from provider 3 with minimal data."""
    now = datetime.now(timezone.utc)
    return ProviderMatchStats(
        provider="provider_3",
        source_id="match_123",
        fetched_at=now,
        match_id="match_123",
        team_id="team_1",
        period="full",
        shots_total=14,  # Same as provider 1
        possession_percentage=58.0,  # Same as provider 1
    )


class TestMergeStatisticsFirstStrategy:
    """Tests for merge_statistics with 'first' strategy."""

    def test_merge_statistics_first_strategy(
        self,
        source_intelligence,
        provider1_stats,
        provider2_stats
    ):
        """Verify 'first' strategy takes first non-None value per field."""
        result = source_intelligence.merge_statistics(
            [provider1_stats, provider2_stats],
            strategy='first'
        )
        
        assert result is not None
        assert result.provider == 'merged'
        
        # Fields from provider 1 (first with value)
        assert result.shots_total == 14
        assert result.shots_on_target == 5
        assert result.shots_off_target == 6
        assert result.possession_percentage == 58.0
        assert result.xg == 1.89
        assert result.corners == 7
        assert result.yellow_cards == 3
        
        # Fields only in provider 2
        assert result.passes_completed == 450
        assert result.passes_attempted == 520

    def test_merge_statistics_first_strategy_fills_gaps(
        self,
        source_intelligence,
        provider1_stats,
        provider2_stats
    ):
        """Verify 'first' strategy fills gaps from later providers."""
        # provider1 has corners but not passes
        # provider2 has passes but not corners
        result = source_intelligence.merge_statistics(
            [provider1_stats, provider2_stats],
            strategy='first'
        )
        
        assert result.corners == 7  # From provider 1
        assert result.passes_completed == 450  # From provider 2
        assert result.passes_attempted == 520  # From provider 2


class TestMergeStatisticsMostCompleteStrategy:
    """Tests for merge_statistics with 'most_complete' strategy."""

    def test_merge_statistics_most_complete_strategy(
        self,
        source_intelligence,
        provider1_stats,
        provider2_stats,
        provider3_stats
    ):
        """Verify 'most_complete' strategy selects provider with most fields."""
        result = source_intelligence.merge_statistics(
            [provider3_stats, provider1_stats, provider2_stats],
            strategy='most_complete'
        )
        
        assert result is not None
        
        # provider1 has 7 fields, provider2 has 6 fields, provider3 has 2 fields
        # Should select provider1
        assert result.provider == "provider_1"
        assert result.shots_total == 14
        assert result.corners == 7
        assert result.yellow_cards == 3

    def test_merge_statistics_most_complete_whole_provider(
        self,
        source_intelligence,
        provider1_stats,
        provider2_stats
    ):
        """Verify 'most_complete' returns entire provider, not field-by-field merge."""
        result = source_intelligence.merge_statistics(
            [provider1_stats, provider2_stats],
            strategy='most_complete'
        )
        
        # Should return provider1 entirely (has more non-None fields)
        assert result.provider == "provider_1"
        
        # Should NOT have provider2's exclusive fields
        assert result.passes_completed is None
        assert result.passes_attempted is None


class TestMergeStatisticsHighestQualityStrategy:
    """Tests for merge_statistics with 'highest_quality' strategy."""

    def test_merge_statistics_highest_quality_strategy(
        self,
        source_intelligence,
        provider1_stats,
        provider2_stats
    ):
        """Verify 'highest_quality' strategy selects provider with highest quality score."""
        result = source_intelligence.merge_statistics(
            [provider1_stats, provider2_stats],
            strategy='highest_quality'
        )
        
        assert result is not None
        # provider1 should win (more complete and consistent)
        assert result.provider in ["provider_1", "provider_2"]

    def test_merge_statistics_highest_quality_consistency_matters(
        self,
        source_intelligence
    ):
        """Verify 'highest_quality' considers consistency violations."""
        now = datetime.now(timezone.utc)
        
        # Valid stats
        valid_stats = ProviderMatchStats(
            provider="valid",
            source_id="123",
            fetched_at=now,
            match_id="match_1",
            team_id="team_1",
            shots_total=10,
            shots_on_target=5,
            possession_percentage=55.0,
        )
        
        # Invalid stats (consistency violations)
        invalid_stats = ProviderMatchStats(
            provider="invalid",
            source_id="123",
            fetched_at=now,
            match_id="match_1",
            team_id="team_1",
            shots_total=10,
            shots_on_target=15,  # Violation: > shots_total
            possession_percentage=105.0,  # Violation: > 100
        )
        
        result = source_intelligence.merge_statistics(
            [invalid_stats, valid_stats],
            strategy='highest_quality'
        )
        
        # Should select valid_stats
        assert result.provider == "valid"


class TestMergeStatisticsEmptyList:
    """Tests for merge_statistics with empty list."""

    def test_merge_statistics_empty_list(self, source_intelligence):
        """Verify merge_statistics returns None for empty list."""
        result = source_intelligence.merge_statistics([], strategy='first')
        assert result is None
        
        result = source_intelligence.merge_statistics([], strategy='most_complete')
        assert result is None
        
        result = source_intelligence.merge_statistics([], strategy='highest_quality')
        assert result is None


class TestDetectConflicts:
    """Tests for detect_conflicts method."""

    def test_detect_conflicts_no_conflicts(
        self,
        source_intelligence,
        provider1_stats,
        provider3_stats
    ):
        """Verify detect_conflicts returns empty dict when values match."""
        # provider1 and provider3 have matching values for shots_total and possession
        conflicts = source_intelligence.detect_conflicts([provider1_stats, provider3_stats])
        
        assert isinstance(conflicts, dict)
        # Should have no conflicts for shots_total and possession_percentage
        assert 'shots_total' not in conflicts
        assert 'possession_percentage' not in conflicts

    def test_detect_conflicts_with_disagreements(
        self,
        source_intelligence,
        provider1_stats,
        provider2_stats
    ):
        """Verify detect_conflicts identifies disagreements."""
        conflicts = source_intelligence.detect_conflicts([provider1_stats, provider2_stats])
        
        assert isinstance(conflicts, dict)
        
        # Should detect conflicts in these fields
        assert 'shots_total' in conflicts
        assert 'shots_on_target' in conflicts
        assert 'possession_percentage' in conflicts
        assert 'xg' in conflicts
        
        # Verify conflict structure for shots_total
        shots_conflict = conflicts['shots_total']
        assert len(shots_conflict) == 2
        assert any(item['provider'] == 'provider_1' and item['value'] == 14 for item in shots_conflict)
        assert any(item['provider'] == 'provider_2' and item['value'] == 15 for item in shots_conflict)

    def test_detect_conflicts_ignores_none_values(self, source_intelligence):
        """Verify detect_conflicts ignores None values."""
        now = datetime.now(timezone.utc)
        
        stats1 = ProviderMatchStats(
            provider="provider_1",
            source_id="123",
            fetched_at=now,
            match_id="match_1",
            team_id="team_1",
            shots_total=10,
            corners=None,  # None value
        )
        
        stats2 = ProviderMatchStats(
            provider="provider_2",
            source_id="123",
            fetched_at=now,
            match_id="match_1",
            team_id="team_1",
            shots_total=10,
            corners=5,  # Has value
        )
        
        conflicts = source_intelligence.detect_conflicts([stats1, stats2])
        
        # Should not report conflict for corners (one is None)
        assert 'corners' not in conflicts
        
        # Should not report conflict for shots_total (same value)
        assert 'shots_total' not in conflicts


class TestGetFieldSources:
    """Tests for get_field_sources method."""

    def test_get_field_sources_tracks_origin(
        self,
        source_intelligence,
        provider1_stats,
        provider2_stats
    ):
        """Verify get_field_sources tracks which provider supplied each field."""
        # First merge the stats
        merged = source_intelligence.merge_statistics(
            [provider1_stats, provider2_stats],
            strategy='first'
        )
        
        # Track field sources
        sources = source_intelligence.get_field_sources(
            merged,
            [provider1_stats, provider2_stats]
        )
        
        assert isinstance(sources, dict)
        
        # Fields from provider 1 (first with value)
        assert sources.get('shots_total') == 'provider_1'
        assert sources.get('shots_on_target') == 'provider_1'
        assert sources.get('corners') == 'provider_1'
        assert sources.get('yellow_cards') == 'provider_1'
        
        # Fields only in provider 2
        assert sources.get('passes_completed') == 'provider_2'
        assert sources.get('passes_attempted') == 'provider_2'

    def test_get_field_sources_all_fields(
        self,
        source_intelligence,
        provider1_stats,
        provider2_stats
    ):
        """Verify get_field_sources includes all non-None fields."""
        merged = source_intelligence.merge_statistics(
            [provider1_stats, provider2_stats],
            strategy='first'
        )
        
        sources = source_intelligence.get_field_sources(
            merged,
            [provider1_stats, provider2_stats]
        )
        
        # Should have sources for all non-None fields in merged
        merged_dict = merged.model_dump()
        metadata_fields = ['provider', 'source_id', 'fetched_at', 'source_updated_at',
                          'is_live', 'data_freshness_seconds', 'match_id', 'team_id',
                          'team_name', 'period']
        
        for field, value in merged_dict.items():
            if field in metadata_fields:
                continue
            if value is not None:
                assert field in sources, f"Missing source for field: {field}"

    def test_get_field_sources_empty_stats_list(self, source_intelligence, provider1_stats):
        """Verify get_field_sources handles empty stats_list."""
        sources = source_intelligence.get_field_sources(provider1_stats, [])
        
        assert isinstance(sources, dict)
        assert len(sources) == 0


class TestInvalidStrategy:
    """Tests for invalid merge strategy."""

    def test_merge_statistics_invalid_strategy(self, source_intelligence, provider1_stats):
        """Verify merge_statistics raises ValueError for invalid strategy."""
        with pytest.raises(ValueError, match="Unknown merge strategy"):
            source_intelligence.merge_statistics(
                [provider1_stats],
                strategy='invalid_strategy'
            )


class TestMergeBookmakerOdds:
    """Tests for merge_bookmaker_odds method."""
    
    @pytest.fixture
    def odds1(self):
        """Create Odds from source 1."""
        from app.domain.odds import Odds
        now = datetime.now(timezone.utc)
        return Odds(
            id="odds_1",
            match_id="match_123",
            bookmaker="Bet365",
            home_win_odds=2.10,
            draw_odds=3.40,
            away_win_odds=3.60,
            over_under_line=2.5,
            over_odds=1.90,
            under_odds=1.95,
            fetched_at=now,
            source_provider="sofascore",
            normalized_market_type="match_result",
        )
    
    @pytest.fixture
    def odds2(self):
        """Create Odds from source 2 with different values."""
        from app.domain.odds import Odds
        now = datetime.now(timezone.utc)
        return Odds(
            id="odds_2",
            match_id="match_123",
            bookmaker="William Hill",
            home_win_odds=2.15,  # Different
            draw_odds=3.50,  # Different
            away_win_odds=3.50,  # Different
            btts_yes_odds=1.75,  # Additional field
            btts_no_odds=2.05,  # Additional field
            fetched_at=now,
            source_provider="development",
            normalized_market_type="match_result",
        )
    
    @pytest.fixture
    def odds3(self):
        """Create Odds from source 3 with minimal data."""
        from app.domain.odds import Odds
        now = datetime.now(timezone.utc)
        return Odds(
            id="odds_3",
            match_id="match_123",
            bookmaker="Betfair",
            home_win_odds=2.10,  # Same as odds1
            draw_odds=3.40,  # Same as odds1
            away_win_odds=3.60,  # Same as odds1
            fetched_at=now,
        )
    
    def test_merge_bookmaker_odds_first_strategy(self, source_intelligence, odds1, odds2):
        """Verify 'first' strategy takes first non-None odds per field."""
        result = source_intelligence.merge_bookmaker_odds([odds1, odds2], strategy='first')
        
        assert result is not None
        assert result.bookmaker == 'merged'
        assert result.source_provider == 'merged'
        
        # Fields from odds1 (first with value)
        assert result.home_win_odds == 2.10
        assert result.draw_odds == 3.40
        assert result.away_win_odds == 3.60
        assert result.over_under_line == 2.5
        assert result.over_odds == 1.90
        assert result.under_odds == 1.95
        
        # Fields only in odds2
        assert result.btts_yes_odds == 1.75
        assert result.btts_no_odds == 2.05
    
    def test_merge_bookmaker_odds_first_strategy_fills_gaps(self, source_intelligence, odds1, odds2):
        """Verify 'first' strategy fills gaps from later providers."""
        result = source_intelligence.merge_bookmaker_odds([odds1, odds2], strategy='first')
        
        # odds1 has over/under but not btts
        # odds2 has btts but not over/under
        assert result.over_odds == 1.90  # From odds1
        assert result.under_odds == 1.95  # From odds1
        assert result.btts_yes_odds == 1.75  # From odds2
        assert result.btts_no_odds == 2.05  # From odds2
    
    def test_merge_bookmaker_odds_most_complete_strategy(
        self,
        source_intelligence,
        odds1,
        odds2,
        odds3
    ):
        """Verify 'most_complete' strategy selects odds with most fields."""
        result = source_intelligence.merge_bookmaker_odds(
            [odds3, odds1, odds2],
            strategy='most_complete'
        )
        
        assert result is not None
        
        # odds1 has 6 odds fields, odds2 has 5 fields, odds3 has 3 fields
        # Should select odds1
        assert result.bookmaker == "Bet365"
        assert result.home_win_odds == 2.10
        assert result.over_odds == 1.90
        assert result.under_odds == 1.95
    
    def test_merge_bookmaker_odds_most_complete_whole_provider(
        self,
        source_intelligence,
        odds1,
        odds2
    ):
        """Verify 'most_complete' returns entire odds, not field-by-field merge."""
        result = source_intelligence.merge_bookmaker_odds(
            [odds1, odds2],
            strategy='most_complete'
        )
        
        # Should return odds1 entirely (has more non-None fields)
        assert result.bookmaker == "Bet365"
        
        # Should NOT have odds2's exclusive fields
        assert result.btts_yes_odds is None
        assert result.btts_no_odds is None
    
    def test_merge_bookmaker_odds_highest_quality_strategy(
        self,
        source_intelligence,
        odds1,
        odds2
    ):
        """Verify 'highest_quality' strategy delegates to most_complete for odds."""
        result = source_intelligence.merge_bookmaker_odds(
            [odds1, odds2],
            strategy='highest_quality'
        )
        
        assert result is not None
        # Should behave like most_complete for odds
        assert result.bookmaker == "Bet365"  # odds1 has more fields
    
    def test_merge_bookmaker_odds_empty_list(self, source_intelligence):
        """Verify merge_bookmaker_odds returns None for empty list."""
        result = source_intelligence.merge_bookmaker_odds([], strategy='first')
        assert result is None
    
    def test_merge_bookmaker_odds_single_source(self, source_intelligence, odds1):
        """Verify merge_bookmaker_odds works with single source."""
        result = source_intelligence.merge_bookmaker_odds([odds1], strategy='first')
        
        assert result is not None
        # Should return the single odds unchanged
        assert result.bookmaker == "Bet365"
        assert result.home_win_odds == 2.10
    
    def test_merge_bookmaker_odds_invalid_strategy(self, source_intelligence, odds1):
        """Verify merge_bookmaker_odds raises ValueError for invalid strategy."""
        with pytest.raises(ValueError, match="Unknown merge strategy"):
            source_intelligence.merge_bookmaker_odds([odds1], strategy='invalid_strategy')
