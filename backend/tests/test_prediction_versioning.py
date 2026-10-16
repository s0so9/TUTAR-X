"""Tests for prediction versioning and immutability."""

import pytest
from datetime import datetime
from typing import List

from app.prediction.prediction_version import (
    PredictionVersion,
    PredictionVersionManager,
    PredictionStage
)


class TestPredictionVersioning:
    """Test prediction version management."""
    
    def test_create_version_basic(self):
        """Test basic version creation."""
        manager = PredictionVersionManager()
        
        prediction_data = {
            "home_win_prob": 0.45,
            "draw_prob": 0.30,
            "away_win_prob": 0.25
        }
        
        version = manager.create_version(
            match_id="match_123",
            stage=PredictionStage.KICKOFF,
            prediction_data=prediction_data,
            confidence_score=0.75
        )
        
        assert version.match_id == "match_123"
        assert version.stage == PredictionStage.KICKOFF
        assert version.confidence_score == 0.75
        assert version.prediction_data["home_win_prob"] == 0.45
    
    def test_get_versions_returns_chronological_order(self):
        """Test that get_versions returns versions in chronological order."""
        manager = PredictionVersionManager()
        
        # Create multiple versions
        v1 = manager.create_version(
            match_id="match_123",
            stage=PredictionStage.SEVEN_DAYS_BEFORE,
            prediction_data={"test": 1},
            allow_stage_overwrite=True
        )
        
        v2 = manager.create_version(
            match_id="match_123",
            stage=PredictionStage.TWENTY_FOUR_HOURS_BEFORE,
            prediction_data={"test": 2},
            allow_stage_overwrite=True
        )
        
        versions = manager.get_versions("match_123")
        
        assert len(versions) == 2
        assert versions[0].version_id == v1.version_id
        assert versions[1].version_id == v2.version_id
    
    def test_immutability_enforcement_rejects_duplicate_stage(self):
        """Test that duplicate stage writes are rejected by default (immutability).
        
        This test verifies Finding #4 from FEAT-005 review:
        When allow_stage_overwrite=False (default), attempting to create
        a second version at the same stage should raise ValueError.
        """
        manager = PredictionVersionManager()
        
        # Create first version at KICKOFF stage
        v1 = manager.create_version(
            match_id="match_456",
            stage=PredictionStage.KICKOFF,
            prediction_data={"home_win_prob": 0.45},
            confidence_score=0.75
        )
        
        assert v1 is not None
        assert v1.stage == PredictionStage.KICKOFF
        
        # Attempt to create second version at same stage should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            manager.create_version(
                match_id="match_456",
                stage=PredictionStage.KICKOFF,
                prediction_data={"home_win_prob": 0.50},  # Different data
                confidence_score=0.80
            )
        
        assert "already exists" in str(exc_info.value).lower()
        assert "match_456" in str(exc_info.value)
        
        # Verify only one version exists
        versions = manager.get_versions("match_456")
        assert len(versions) == 1
        assert versions[0].version_id == v1.version_id
        assert versions[0].prediction_data["home_win_prob"] == 0.45  # Original data unchanged
    
    def test_immutability_enforcement_allows_overwrite_when_flagged(self):
        """Test that allow_stage_overwrite=True permits duplicate stages."""
        manager = PredictionVersionManager()
        
        # Create first version
        v1 = manager.create_version(
            match_id="match_789",
            stage=PredictionStage.LINEUP_CONFIRMED,
            prediction_data={"home_win_prob": 0.45},
        )
        
        # Create second version with overwrite flag
        v2 = manager.create_version(
            match_id="match_789",
            stage=PredictionStage.LINEUP_CONFIRMED,
            prediction_data={"home_win_prob": 0.50},
            allow_stage_overwrite=True
        )
        
        # Both versions should exist
        versions = manager.get_versions("match_789")
        assert len(versions) == 2
        assert versions[0].version_id == v1.version_id
        assert versions[1].version_id == v2.version_id
        assert versions[0].prediction_data["home_win_prob"] == 0.45
        assert versions[1].prediction_data["home_win_prob"] == 0.50
    
    def test_immutability_across_different_stages(self):
        """Test that different stages can coexist for same match."""
        manager = PredictionVersionManager()
        
        # Create versions at different stages
        v1 = manager.create_version(
            match_id="match_111",
            stage=PredictionStage.SEVEN_DAYS_BEFORE,
            prediction_data={"home_win_prob": 0.40},
        )
        
        v2 = manager.create_version(
            match_id="match_111",
            stage=PredictionStage.TWENTY_FOUR_HOURS_BEFORE,
            prediction_data={"home_win_prob": 0.43},
        )
        
        v3 = manager.create_version(
            match_id="match_111",
            stage=PredictionStage.KICKOFF,
            prediction_data={"home_win_prob": 0.45},
        )
        
        # All three versions should exist
        versions = manager.get_versions("match_111")
        assert len(versions) == 3
        
        # Verify can retrieve by stage
        v_7d = manager.get_version_by_stage("match_111", PredictionStage.SEVEN_DAYS_BEFORE)
        v_24h = manager.get_version_by_stage("match_111", PredictionStage.TWENTY_FOUR_HOURS_BEFORE)
        v_kick = manager.get_version_by_stage("match_111", PredictionStage.KICKOFF)
        
        assert v_7d.version_id == v1.version_id
        assert v_24h.version_id == v2.version_id
        assert v_kick.version_id == v3.version_id
        
        # Verify data integrity
        assert v_7d.prediction_data["home_win_prob"] == 0.40
        assert v_24h.prediction_data["home_win_prob"] == 0.43
        assert v_kick.prediction_data["home_win_prob"] == 0.45
    
    def test_version_data_immutability_via_copy(self):
        """Test that modifying source data doesn't affect stored version."""
        manager = PredictionVersionManager()
        
        # Create mutable prediction data
        prediction_data = {
            "home_win_prob": 0.45,
            "markets": {"1X2": [0.45, 0.30, 0.25]}
        }
        
        # Create version
        version = manager.create_version(
            match_id="match_222",
            stage=PredictionStage.KICKOFF,
            prediction_data=prediction_data
        )
        
        # Modify original data
        prediction_data["home_win_prob"] = 0.99
        prediction_data["markets"]["1X2"] = [0.99, 0.00, 0.01]
        
        # Retrieve version and verify data unchanged
        stored_version = manager.get_latest_version("match_222")
        assert stored_version.prediction_data["home_win_prob"] == 0.45
        assert stored_version.prediction_data["markets"]["1X2"] == [0.45, 0.30, 0.25]
    
    def test_get_latest_version(self):
        """Test retrieving the most recent version."""
        manager = PredictionVersionManager()
        
        v1 = manager.create_version(
            match_id="match_333",
            stage=PredictionStage.SEVEN_DAYS_BEFORE,
            prediction_data={"version": 1}
        )
        
        v2 = manager.create_version(
            match_id="match_333",
            stage=PredictionStage.KICKOFF,
            prediction_data={"version": 2}
        )
        
        latest = manager.get_latest_version("match_333")
        assert latest.version_id == v2.version_id
        assert latest.prediction_data["version"] == 2
    
    def test_get_version_by_stage_returns_latest_when_duplicates(self):
        """Test that get_version_by_stage returns latest when multiple exist."""
        manager = PredictionVersionManager()
        
        # Create multiple versions at same stage
        v1 = manager.create_version(
            match_id="match_444",
            stage=PredictionStage.KICKOFF,
            prediction_data={"version": 1},
            allow_stage_overwrite=True
        )
        
        v2 = manager.create_version(
            match_id="match_444",
            stage=PredictionStage.KICKOFF,
            prediction_data={"version": 2},
            allow_stage_overwrite=True
        )
        
        # Should return the latest
        stage_version = manager.get_version_by_stage("match_444", PredictionStage.KICKOFF)
        assert stage_version.version_id == v2.version_id
        assert stage_version.prediction_data["version"] == 2


class TestPredictionVersionValidation:
    """Test PredictionVersion validation."""
    
    def test_validation_rejects_invalid_confidence_score(self):
        """Test that confidence_score must be in [0, 1]."""
        with pytest.raises(ValueError) as exc_info:
            PredictionVersion(
                version_id="v1",
                match_id="m1",
                stage=PredictionStage.KICKOFF,
                created_at=datetime.utcnow(),
                prediction_data={},
                confidence_score=1.5  # Invalid
            )
        
        assert "confidence_score" in str(exc_info.value).lower()
    
    def test_validation_rejects_invalid_data_quality_score(self):
        """Test that data_quality_score must be in [0, 1]."""
        with pytest.raises(ValueError) as exc_info:
            PredictionVersion(
                version_id="v1",
                match_id="m1",
                stage=PredictionStage.KICKOFF,
                created_at=datetime.utcnow(),
                prediction_data={},
                data_quality_score=-0.1  # Invalid
            )
        
        assert "data_quality_score" in str(exc_info.value).lower()
    
    def test_validation_converts_string_stage(self):
        """Test that string stage values are converted to enum."""
        version = PredictionVersion(
            version_id="v1",
            match_id="m1",
            stage="kickoff",  # String instead of enum
            created_at=datetime.utcnow(),
            prediction_data={}
        )
        
        assert version.stage == PredictionStage.KICKOFF
        assert isinstance(version.stage, PredictionStage)


class TestPredictionVersionImmutabilityWithPersistence:
    """Test immutability enforcement with database persistence.
    
    This test class addresses Finding #4 from FEAT-005 review:
    "Immutability enforcement untested under database writes"
    
    Verifies that duplicate stage writes are rejected when persistence_service
    is configured with actual database operations.
    """
    
    def test_immutability_with_mock_database_persistence(self):
        """Test that immutability is enforced when using persistence service.
        
        This test uses a mock persistence service to verify the enforcement
        logic without requiring a real database connection.
        """
        # Create mock persistence service
        class MockPersistenceService:
            def __init__(self):
                self.storage = {}
            
            def save_version(self, version: PredictionVersion) -> None:
                """Save version to mock storage."""
                if version.match_id not in self.storage:
                    self.storage[version.match_id] = []
                self.storage[version.match_id].append(version)
            
            def get_versions(self, match_id: str) -> List[PredictionVersion]:
                """Get all versions for match from mock storage."""
                versions = self.storage.get(match_id, [])
                return sorted(versions, key=lambda v: v.created_at)
            
            def delete_version(self, version_id: str) -> bool:
                """Delete version from mock storage."""
                for match_id, versions in self.storage.items():
                    for i, v in enumerate(versions):
                        if v.version_id == version_id:
                            del self.storage[match_id][i]
                            return True
                return False
        
        # Create manager with mock persistence
        mock_persistence = MockPersistenceService()
        manager = PredictionVersionManager(persistence_service=mock_persistence)
        
        # Create first version at KICKOFF stage
        v1 = manager.create_version(
            match_id="match_db_test",
            stage=PredictionStage.KICKOFF,
            prediction_data={"home_win_prob": 0.45, "data_source": "v1"},
            confidence_score=0.75
        )
        
        assert v1 is not None
        assert v1.stage == PredictionStage.KICKOFF
        
        # Verify version was persisted
        persisted_versions = mock_persistence.get_versions("match_db_test")
        assert len(persisted_versions) == 1
        assert persisted_versions[0].version_id == v1.version_id
        
        # Attempt to create second version at same stage should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            manager.create_version(
                match_id="match_db_test",
                stage=PredictionStage.KICKOFF,
                prediction_data={"home_win_prob": 0.50, "data_source": "v2"},
                confidence_score=0.80
            )
        
        assert "already exists" in str(exc_info.value).lower()
        assert "match_db_test" in str(exc_info.value)
        
        # Verify only one version exists in persistence
        persisted_versions = mock_persistence.get_versions("match_db_test")
        assert len(persisted_versions) == 1
        assert persisted_versions[0].version_id == v1.version_id
        assert persisted_versions[0].prediction_data["data_source"] == "v1"  # Original data unchanged
        
    def test_immutability_enforcement_checks_persistence_not_memory(self):
        """Test that immutability check uses persistence service, not in-memory fallback."""
        # Create mock persistence that simulates existing version
        class MockPersistenceWithExisting:
            def __init__(self):
                self.storage = {}
                # Pre-populate with existing version
                existing_version = PredictionVersion(
                    version_id="existing_v1",
                    match_id="match_existing",
                    stage=PredictionStage.LINEUP_CONFIRMED,
                    created_at=datetime(2026, 1, 1, 12, 0, 0),
                    prediction_data={"home_win_prob": 0.40}
                )
                self.storage["match_existing"] = [existing_version]
            
            def save_version(self, version: PredictionVersion) -> None:
                if version.match_id not in self.storage:
                    self.storage[version.match_id] = []
                self.storage[version.match_id].append(version)
            
            def get_versions(self, match_id: str) -> List[PredictionVersion]:
                versions = self.storage.get(match_id, [])
                return sorted(versions, key=lambda v: v.created_at)
            
            def delete_version(self, version_id: str) -> bool:
                for match_id, versions in self.storage.items():
                    for i, v in enumerate(versions):
                        if v.version_id == version_id:
                            del self.storage[match_id][i]
                            return True
                return False
        
        mock_persistence = MockPersistenceWithExisting()
        manager = PredictionVersionManager(persistence_service=mock_persistence)
        
        # Attempt to create version at same stage as existing should fail
        with pytest.raises(ValueError) as exc_info:
            manager.create_version(
                match_id="match_existing",
                stage=PredictionStage.LINEUP_CONFIRMED,
                prediction_data={"home_win_prob": 0.50},
                confidence_score=0.80
            )
        
        assert "already exists" in str(exc_info.value).lower()
        
        # Verify only the original version exists
        versions = mock_persistence.get_versions("match_existing")
        assert len(versions) == 1
        assert versions[0].version_id == "existing_v1"
        assert versions[0].prediction_data["home_win_prob"] == 0.40
