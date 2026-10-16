"""Tests for DataQualityEngine.

These tests verify the data quality validation and scoring logic.
Pure calculation tests with no HTTP calls or async operations.
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.providers import DataQualityEngine, ProviderMatchStats, ProviderMetadata


@pytest.fixture
def quality_engine():
    """Create a DataQualityEngine instance."""
    return DataQualityEngine()


@pytest.fixture
def complete_stats():
    """Create a ProviderMatchStats with all fields populated."""
    now = datetime.now(timezone.utc)
    return ProviderMatchStats(
        provider="test_provider",
        source_id="12345",
        fetched_at=now,
        match_id="match_1",
        team_id="team_1",
        period="full",
        goals_scored=2,
        goals_conceded=1,
        xg=1.89,
        xg_against=0.76,
        shots_total=14,
        shots_on_target=5,
        shots_off_target=6,
        shots_blocked=3,
        possession_percentage=58.0,
        passes_completed=450,
        passes_attempted=520,
        pass_accuracy=86.5,
        corners=7,
        free_kicks=12,
        offsides=2,
        yellow_cards=3,
        red_cards=0,
        fouls_committed=11,
        tackles=18,
        interceptions=9,
        clearances=14,
        saves=3,
    )


@pytest.fixture
def incomplete_stats():
    """Create a ProviderMatchStats with only some fields populated."""
    now = datetime.now(timezone.utc)
    return ProviderMatchStats(
        provider="test_provider",
        source_id="12345",
        fetched_at=now,
        match_id="match_1",
        team_id="team_1",
        period="full",
        shots_total=10,
        shots_on_target=4,
        possession_percentage=45.0,
        # Most fields left as None
    )


@pytest.fixture
def recent_metadata():
    """Create metadata with recent timestamp (fresh data)."""
    now = datetime.now(timezone.utc)
    return ProviderMetadata(
        provider="test_provider",
        source_id="12345",
        fetched_at=now,
    )


@pytest.fixture
def stale_metadata():
    """Create metadata with old timestamp (stale data)."""
    now = datetime.now(timezone.utc)
    ten_minutes_ago = now - timedelta(minutes=10)
    return ProviderMetadata(
        provider="test_provider",
        source_id="12345",
        fetched_at=ten_minutes_ago,
    )


class TestCheckCompleteness:
    """Tests for check_completeness method."""

    def test_check_completeness_all_fields_present(self, quality_engine, complete_stats):
        """Verify completeness check with all fields present."""
        result = quality_engine.check_completeness(complete_stats)
        
        assert 'available' in result
        assert 'expected' in result
        assert 'ratio' in result
        assert 'missing_fields' in result
        
        assert result['available'] == result['expected']
        assert result['ratio'] == 1.0
        assert len(result['missing_fields']) == 0

    def test_check_completeness_missing_fields(self, quality_engine, incomplete_stats):
        """Verify completeness check with missing fields."""
        result = quality_engine.check_completeness(incomplete_stats)
        
        assert result['available'] < result['expected']
        assert 0.0 < result['ratio'] < 1.0
        assert len(result['missing_fields']) > 0
        
        # Verify some expected missing fields
        assert 'goals_scored' in result['missing_fields']
        assert 'xg' in result['missing_fields']
        assert 'corners' in result['missing_fields']
        
        # Verify available fields are counted correctly
        assert result['available'] == 3  # shots_total, shots_on_target, possession_percentage


class TestCheckConsistency:
    """Tests for check_consistency method."""

    def test_check_consistency_valid_stats(self, quality_engine, complete_stats):
        """Verify consistency check with valid statistics."""
        result = quality_engine.check_consistency(complete_stats)
        
        assert 'violations' in result
        assert 'is_consistent' in result
        
        assert result['is_consistent'] is True
        assert len(result['violations']) == 0

    def test_check_consistency_shots_violation(self, quality_engine):
        """Verify consistency check detects shot violations."""
        now = datetime.now(timezone.utc)
        
        # shots_on_target > shots_total
        invalid_stats = ProviderMatchStats(
            provider="test",
            source_id="123",
            fetched_at=now,
            match_id="match_1",
            team_id="team_1",
            shots_total=10,
            shots_on_target=15,  # Invalid: more than total
        )
        
        result = quality_engine.check_consistency(invalid_stats)
        
        assert result['is_consistent'] is False
        assert len(result['violations']) > 0
        assert any('shots_on_target' in v for v in result['violations'])

    def test_check_consistency_possession_violation(self, quality_engine):
        """Verify consistency check detects possession violations."""
        now = datetime.now(timezone.utc)
        
        # possession > 100
        invalid_stats = ProviderMatchStats(
            provider="test",
            source_id="123",
            fetched_at=now,
            match_id="match_1",
            team_id="team_1",
            possession_percentage=105.0,  # Invalid: > 100
        )
        
        result = quality_engine.check_consistency(invalid_stats)
        
        assert result['is_consistent'] is False
        assert len(result['violations']) > 0
        assert any('possession_percentage' in v for v in result['violations'])

    def test_check_consistency_negative_values(self, quality_engine):
        """Verify consistency check detects negative values."""
        now = datetime.now(timezone.utc)
        
        # Negative xG
        invalid_stats = ProviderMatchStats(
            provider="test",
            source_id="123",
            fetched_at=now,
            match_id="match_1",
            team_id="team_1",
            xg=-1.5,  # Invalid: negative
        )
        
        result = quality_engine.check_consistency(invalid_stats)
        
        assert result['is_consistent'] is False
        assert len(result['violations']) > 0
        assert any('xg' in v and '< 0' in v for v in result['violations'])


class TestCheckFreshness:
    """Tests for check_freshness method."""

    def test_check_freshness_recent_data(self, quality_engine, recent_metadata):
        """Verify freshness check with recent data."""
        result = quality_engine.check_freshness(recent_metadata, max_age_seconds=300)
        
        assert result is True

    def test_check_freshness_stale_data(self, quality_engine, stale_metadata):
        """Verify freshness check with stale data."""
        result = quality_engine.check_freshness(stale_metadata, max_age_seconds=300)
        
        assert result is False


class TestDetectSourceConflicts:
    """Tests for detect_source_conflicts method."""

    def test_detect_source_conflicts_no_conflicts(self, quality_engine):
        """Verify conflict detection with no conflicts."""
        now = datetime.now(timezone.utc)
        
        stats1 = ProviderMatchStats(
            provider="provider_1",
            source_id="123",
            fetched_at=now,
            match_id="match_1",
            team_id="team_1",
            shots_total=10,
            possession_percentage=55.0,
        )
        
        stats2 = ProviderMatchStats(
            provider="provider_2",
            source_id="123",
            fetched_at=now,
            match_id="match_1",
            team_id="team_1",
            shots_total=10,  # Same value
            possession_percentage=55.0,  # Same value
        )
        
        result = quality_engine.detect_source_conflicts([stats1, stats2])
        
        assert 'conflicts' in result
        assert 'has_conflicts' in result
        assert result['has_conflicts'] is False
        assert len(result['conflicts']) == 0

    def test_detect_source_conflicts_with_disagreement(self, quality_engine):
        """Verify conflict detection with disagreements."""
        now = datetime.now(timezone.utc)
        
        stats1 = ProviderMatchStats(
            provider="provider_1",
            source_id="123",
            fetched_at=now,
            match_id="match_1",
            team_id="team_1",
            shots_total=14,
            possession_percentage=58.0,
        )
        
        stats2 = ProviderMatchStats(
            provider="provider_2",
            source_id="123",
            fetched_at=now,
            match_id="match_1",
            team_id="team_1",
            shots_total=15,  # Different value
            possession_percentage=57.0,  # Different value
        )
        
        result = quality_engine.detect_source_conflicts([stats1, stats2])
        
        assert result['has_conflicts'] is True
        assert len(result['conflicts']) == 2
        
        # Find conflicts by field
        conflicts_by_field = {c['field']: c for c in result['conflicts']}
        
        assert 'shots_total' in conflicts_by_field
        assert 'possession_percentage' in conflicts_by_field
        
        # Verify shots_total conflict
        shots_conflict = conflicts_by_field['shots_total']
        assert len(shots_conflict['values']) == 2
        assert any(v['provider'] == 'provider_1' and v['value'] == 14 for v in shots_conflict['values'])
        assert any(v['provider'] == 'provider_2' and v['value'] == 15 for v in shots_conflict['values'])


class TestCalculateQualityScore:
    """Tests for calculate_quality_score method."""

    def test_calculate_quality_score_perfect(self, quality_engine, complete_stats):
        """Verify quality score calculation with perfect data."""
        completeness = quality_engine.check_completeness(complete_stats)
        consistency = quality_engine.check_consistency(complete_stats)
        freshness = True
        
        result = quality_engine.calculate_quality_score(
            completeness,
            consistency,
            freshness
        )
        
        assert 'overall' in result
        assert 'completeness' in result
        assert 'consistency' in result
        assert 'freshness' in result
        
        assert result['completeness'] == 100.0
        assert result['consistency'] == 100.0
        assert result['freshness'] == 100.0
        assert result['overall'] == 100.0

    def test_calculate_quality_score_incomplete(self, quality_engine, incomplete_stats):
        """Verify quality score calculation with incomplete data."""
        completeness = quality_engine.check_completeness(incomplete_stats)
        consistency = quality_engine.check_consistency(incomplete_stats)
        freshness = True
        
        result = quality_engine.calculate_quality_score(
            completeness,
            consistency,
            freshness
        )
        
        # Completeness should be low
        assert result['completeness'] < 50.0
        # Consistency should still be 100 (valid values)
        assert result['consistency'] == 100.0
        # Freshness should be 100
        assert result['freshness'] == 100.0
        # Overall should be between 0 and 100
        assert 0.0 <= result['overall'] < 100.0

    def test_calculate_quality_score_inconsistent(self, quality_engine):
        """Verify quality score calculation with inconsistent data."""
        now = datetime.now(timezone.utc)
        
        # Create stats with violations
        inconsistent_stats = ProviderMatchStats(
            provider="test",
            source_id="123",
            fetched_at=now,
            match_id="match_1",
            team_id="team_1",
            shots_total=10,
            shots_on_target=15,  # Violation
            shots_off_target=8,  # Violation
            xg=-1.0,  # Violation
        )
        
        completeness = quality_engine.check_completeness(inconsistent_stats)
        consistency = quality_engine.check_consistency(inconsistent_stats)
        freshness = True
        
        result = quality_engine.calculate_quality_score(
            completeness,
            consistency,
            freshness
        )
        
        # Consistency should be penalized (3 violations = 60 points deduction)
        assert result['consistency'] < 100.0
        # Overall should be reduced
        assert result['overall'] < 100.0

    def test_quality_score_formula_deterministic(self, quality_engine):
        """Verify quality score formula is deterministic and reproducible."""
        now = datetime.now(timezone.utc)
        
        stats = ProviderMatchStats(
            provider="test",
            source_id="123",
            fetched_at=now,
            match_id="match_1",
            team_id="team_1",
            shots_total=12,
            shots_on_target=5,
            possession_percentage=52.0,
            xg=1.5,
        )
        
        # Calculate score twice
        completeness = quality_engine.check_completeness(stats)
        consistency = quality_engine.check_consistency(stats)
        freshness = True
        
        result1 = quality_engine.calculate_quality_score(completeness, consistency, freshness)
        result2 = quality_engine.calculate_quality_score(completeness, consistency, freshness)
        
        # Results should be identical
        assert result1['overall'] == result2['overall']
        assert result1['completeness'] == result2['completeness']
        assert result1['consistency'] == result2['consistency']
        assert result1['freshness'] == result2['freshness']
        
        # Verify formula: overall = (completeness * 0.4) + (consistency * 0.4) + (freshness * 0.2)
        expected_overall = (
            result1['completeness'] * 0.4 +
            result1['consistency'] * 0.4 +
            result1['freshness'] * 0.2
        )
        assert abs(result1['overall'] - expected_overall) < 0.01  # Allow small float precision error
