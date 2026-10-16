"""Tests for MatchFeatureSnapshot integration with advanced feature engineering.

Tests:
- MatchFeatureSnapshot has advanced_feature_set field
- Field defaults to None (backward compatible)
- Can assign AdvancedFeatureSet to snapshot
- Backward compatibility without advanced features
- to_dict includes advanced_feature_set
- get_feature_dict unchanged (existing functionality)
- Full round-trip with advanced features
"""

import pytest
from datetime import datetime

from app.prediction.feature_snapshot import MatchFeatureSnapshot
from app.features.advanced_feature_engineering import (
    AdvancedFeatureSet,
    AdvancedFeatureMetadata,
    FeatureAvailability,
    ADVANCED_FEATURE_VERSION,
)


class TestFeatureSnapshotExtension:
    """Test MatchFeatureSnapshot extension for Group 4."""
    
    def test_snapshot_has_advanced_feature_set_field(self):
        """Test MatchFeatureSnapshot has advanced_feature_set field."""
        snapshot = MatchFeatureSnapshot(
            match_id="match_1",
            home_team_id="team_1",
            away_team_id="team_2",
        )
        
        assert hasattr(snapshot, 'advanced_feature_set')
        assert snapshot.advanced_feature_set is None  # Default
    
    def test_snapshot_advanced_feature_set_defaults_none(self):
        """Test advanced_feature_set defaults to None."""
        snapshot = MatchFeatureSnapshot(
            match_id="match_1",
            home_team_id="team_1",
            away_team_id="team_2",
        )
        
        assert snapshot.advanced_feature_set is None
    
    def test_snapshot_backward_compatible_without_advanced_features(self):
        """Test snapshot works without advanced_feature_set."""
        snapshot = MatchFeatureSnapshot(
            match_id="match_1",
            home_team_id="team_1",
            away_team_id="team_2",
            home_team_name="Team One",
            away_team_name="Team Two",
        )
        
        # Should not crash
        assert snapshot.match_id == "match_1"
        assert snapshot.home_team_id == "team_1"
        assert snapshot.away_team_id == "team_2"
        assert snapshot.advanced_feature_set is None
    
    def test_snapshot_advanced_feature_set_assignment(self):
        """Test can assign AdvancedFeatureSet to snapshot."""
        feature_set = AdvancedFeatureSet(
            features={"xg_differential": 0.5, "shot_differential": 2.0},
            feature_metadata={},
            interaction_features=[],
            redundancy_flags={},
            overall_data_quality=0.85,
        )
        
        snapshot = MatchFeatureSnapshot(
            match_id="match_1",
            home_team_id="team_1",
            away_team_id="team_2",
            advanced_feature_set=feature_set,
        )
        
        assert snapshot.advanced_feature_set == feature_set
        assert snapshot.advanced_feature_set.overall_data_quality == 0.85
    
    def test_extract_feature_snapshot_backward_compatible(self):
        """Test extract_feature_snapshot still works without advanced features."""
        from app.prediction.feature_snapshot import extract_feature_snapshot
        
        snapshot = extract_feature_snapshot(
            match_id="match_1",
            home_team_id="team_1",
            away_team_id="team_2",
            home_team_name="Team One",
            away_team_name="Team Two",
        )
        
        assert snapshot is not None
        assert snapshot.match_id == "match_1"
        assert snapshot.advanced_feature_set is None
    
    def test_snapshot_to_dict_includes_advanced_feature_set(self):
        """Test to_dict() includes advanced_feature_set when present."""
        feature_set = AdvancedFeatureSet(
            features={"xg_differential": 0.5},
            feature_metadata={},
            interaction_features=[],
            redundancy_flags={},
            overall_data_quality=0.85,
        )
        
        snapshot = MatchFeatureSnapshot(
            match_id="match_1",
            home_team_id="team_1",
            away_team_id="team_2",
            advanced_feature_set=feature_set,
        )
        
        snapshot_dict = snapshot.to_dict()
        
        assert "advanced_feature_set" in snapshot_dict
        assert snapshot_dict["advanced_feature_set"] is not None
    
    def test_snapshot_get_feature_dict_unchanged(self):
        """Test get_feature_dict() still works without advanced features."""
        snapshot = MatchFeatureSnapshot(
            match_id="match_1",
            home_team_id="team_1",
            away_team_id="team_2",
        )
        
        feature_dict = snapshot.get_feature_dict()
        
        assert isinstance(feature_dict, dict)
        # Should not crash, returns existing feature extraction
    
    def test_snapshot_with_advanced_features_full_round_trip(self):
        """Test full round-trip with advanced features."""
        prediction_timestamp = datetime(2024, 1, 1, 12, 0)
        
        # Create metadata
        metadata = {
            "xg_differential": AdvancedFeatureMetadata(
                feature_name="xg_differential",
                source_module="feature_engineering",
                source_timestamp=None,
                prediction_timestamp=prediction_timestamp,
                historical_window="recent",
                availability=FeatureAvailability.DERIVED,
                data_quality_score=0.9,
                transformation_applied="differential"
            )
        }
        
        # Create feature set
        feature_set = AdvancedFeatureSet(
            features={"xg_differential": 0.5, "shot_differential": 2.0},
            feature_metadata=metadata,
            interaction_features=[],
            redundancy_flags={"xg_metrics": ["xg_differential"]},
            overall_data_quality=0.85,
            feature_version=ADVANCED_FEATURE_VERSION,
            snapshot_timestamp=prediction_timestamp,
            temporal_validity_checked=True,
        )
        
        # Create snapshot
        snapshot = MatchFeatureSnapshot(
            match_id="match_1",
            home_team_id="team_1",
            away_team_id="team_2",
            advanced_feature_set=feature_set,
        )
        
        # Verify
        assert snapshot.advanced_feature_set is not None
        assert snapshot.advanced_feature_set.overall_data_quality == 0.85
        assert snapshot.advanced_feature_set.temporal_validity_checked is True
        assert "xg_differential" in snapshot.advanced_feature_set.features
        assert snapshot.advanced_feature_set.features["xg_differential"] == 0.5
        assert snapshot.advanced_feature_set.feature_version == ADVANCED_FEATURE_VERSION
    
    def test_snapshot_multiple_snapshots_independent(self):
        """Test multiple snapshots with different feature sets are independent."""
        feature_set_1 = AdvancedFeatureSet(
            features={"xg_differential": 0.5},
            feature_metadata={},
            interaction_features=[],
            redundancy_flags={},
            overall_data_quality=0.8,
        )
        
        feature_set_2 = AdvancedFeatureSet(
            features={"xg_differential": -0.3},
            feature_metadata={},
            interaction_features=[],
            redundancy_flags={},
            overall_data_quality=0.9,
        )
        
        snapshot_1 = MatchFeatureSnapshot(
            match_id="match_1",
            home_team_id="team_1",
            away_team_id="team_2",
            advanced_feature_set=feature_set_1,
        )
        
        snapshot_2 = MatchFeatureSnapshot(
            match_id="match_2",
            home_team_id="team_3",
            away_team_id="team_4",
            advanced_feature_set=feature_set_2,
        )
        
        # Should be independent
        assert snapshot_1.advanced_feature_set.overall_data_quality == 0.8
        assert snapshot_2.advanced_feature_set.overall_data_quality == 0.9
        assert snapshot_1.advanced_feature_set.features["xg_differential"] == 0.5
        assert snapshot_2.advanced_feature_set.features["xg_differential"] == -0.3
    
    def test_snapshot_validate_no_fabricated_data_still_works(self):
        """Test validate_no_fabricated_data method still works."""
        snapshot = MatchFeatureSnapshot(
            match_id="match_1",
            home_team_id="team_1",
            away_team_id="team_2",
        )
        
        warnings = snapshot.validate_no_fabricated_data()
        
        # Should return list (empty or with warnings)
        assert isinstance(warnings, list)
