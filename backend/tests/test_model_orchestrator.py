"""Tests for model orchestrator."""

import pytest
from datetime import datetime
from app.prediction.model_orchestrator import (
    ModelOrchestrator,
    ModelOutput,
    ModelOrchestrationResult,
    ModelStatus,
)
from app.prediction.feature_snapshot import (
    MatchFeatureSnapshot,
    TeamStrengthMetrics,
    FormMetrics,
)
from app.prediction.interfaces import (
    PredictionModel,
    ModelPrediction,
    ModelAvailability,
    PredictionModelMetadata,
)
from app.domain.enums import ModelType


# Mock models for testing


class MockSuccessfulModel(PredictionModel):
    """Mock model that always succeeds."""
    
    def predict(self, features, match_context=None):
        return ModelPrediction(
            model_id="mock_success",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.85,
        )
    
    def get_metadata(self):
        return PredictionModelMetadata(
            model_id="mock_success",
            model_type=ModelType.POISSON,
            version="1.0.0",
            description="Mock successful model",
            required_features=["home_goals_per_match"],
            min_samples_required=0,
        )
    
    def check_requirements(self, features):
        has_required = features.get("home_goals_per_match") is not None
        missing = [] if has_required else ["home_goals_per_match"]
        return has_required, missing


class MockUnavailableModel(PredictionModel):
    """Mock model that returns unavailable."""
    
    def predict(self, features, match_context=None):
        return ModelAvailability(
            model_id="mock_unavailable",
            available=False,
            reason="Test unavailability",
            missing_features=["special_feature"],
        )
    
    def get_metadata(self):
        return PredictionModelMetadata(
            model_id="mock_unavailable",
            model_type=ModelType.ELO,
            version="1.0.0",
            description="Mock unavailable model",
            required_features=["special_feature"],
            min_samples_required=0,
        )
    
    def check_requirements(self, features):
        return False, ["special_feature"]


class MockFailingModel(PredictionModel):
    """Mock model that raises exception."""
    
    def predict(self, features, match_context=None):
        raise RuntimeError("Test failure")
    
    def get_metadata(self):
        return PredictionModelMetadata(
            model_id="mock_failing",
            model_type=ModelType.MONTE_CARLO,
            version="1.0.0",
            description="Mock failing model",
            required_features=[],
            min_samples_required=0,
        )
    
    def check_requirements(self, features):
        return True, []


class TestModelOutput:
    """Test ModelOutput dataclass."""
    
    def test_successful_output(self):
        """Test successful model output."""
        prediction = ModelPrediction(
            model_id="test_model",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.85,
        )
        
        output = ModelOutput(
            model_id="test_model",
            model_version="1.0.0",
            status=ModelStatus.SUPPORTED_RUN,
            prediction=prediction,
            execution_time_ms=50.0,
        )
        
        assert output.is_successful
        assert not output.is_unavailable
        assert not output.is_failed
        assert output.prediction is not None
        assert output.execution_time_ms == 50.0
    
    def test_unavailable_output(self):
        """Test unavailable model output."""
        availability = ModelAvailability(
            model_id="test_model",
            available=False,
            reason="Missing data",
            missing_features=["feature_x"],
        )
        
        output = ModelOutput(
            model_id="test_model",
            model_version="1.0.0",
            status=ModelStatus.UNAVAILABLE_MISSING_INPUTS,
            availability=availability,
        )
        
        assert not output.is_successful
        assert output.is_unavailable
        assert not output.is_failed
        assert output.availability is not None
    
    def test_failed_output(self):
        """Test failed model output."""
        output = ModelOutput(
            model_id="test_model",
            model_version="1.0.0",
            status=ModelStatus.FAILED,
            error_message="Test error",
            error_traceback="Traceback...",
        )
        
        assert not output.is_successful
        assert not output.is_unavailable
        assert output.is_failed
        assert output.error_message == "Test error"


class TestModelOrchestrationResult:
    """Test ModelOrchestrationResult dataclass."""
    
    def test_empty_result(self):
        """Test empty orchestration result."""
        result = ModelOrchestrationResult(total_models=0)
        
        assert not result.has_predictions
        assert result.success_rate == 0.0
        assert len(result.get_all_outputs()) == 0
    
    def test_result_with_predictions(self):
        """Test result with successful predictions."""
        output1 = ModelOutput(
            model_id="model1",
            model_version="1.0",
            status=ModelStatus.SUPPORTED_RUN,
        )
        output2 = ModelOutput(
            model_id="model2",
            model_version="1.0",
            status=ModelStatus.UNAVAILABLE_MISSING_INPUTS,
        )
        
        result = ModelOrchestrationResult(
            total_models=2,
            successful_predictions=[output1],
            unavailable_models=[output2],
            participating_model_ids=["model1"],
        )
        
        assert result.has_predictions
        assert result.success_rate == 0.5
        assert len(result.get_all_outputs()) == 2
        assert "model1" in result.participating_model_ids


class TestModelOrchestrator:
    """Test ModelOrchestrator class."""
    
    def test_register_model(self):
        """Test registering a model."""
        orchestrator = ModelOrchestrator()
        model = MockSuccessfulModel()
        
        orchestrator.register_model(model)
        
        registered = orchestrator.get_registered_models()
        assert "mock_success" in registered
        assert len(registered) == 1
    
    def test_register_multiple_models(self):
        """Test registering multiple models."""
        orchestrator = ModelOrchestrator()
        
        orchestrator.register_model(MockSuccessfulModel())
        orchestrator.register_model(MockUnavailableModel())
        orchestrator.register_model(MockFailingModel())
        
        registered = orchestrator.get_registered_models()
        assert len(registered) == 3
        assert "mock_success" in registered
        assert "mock_unavailable" in registered
        assert "mock_failing" in registered
    
    def test_run_successful_model(self):
        """Test running a successful model."""
        orchestrator = ModelOrchestrator()
        orchestrator.register_model(MockSuccessfulModel())
        
        snapshot = MatchFeatureSnapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
            home_strength=TeamStrengthMetrics(goals_scored_per_match=1.5),
        )
        
        result = orchestrator.run_all(snapshot)
        
        assert result.total_models == 1
        assert len(result.successful_predictions) == 1
        assert len(result.unavailable_models) == 0
        assert len(result.failed_models) == 0
        assert result.has_predictions
        assert result.success_rate == 1.0
    
    def test_run_unavailable_model(self):
        """Test running a model with missing requirements."""
        orchestrator = ModelOrchestrator()
        orchestrator.register_model(MockUnavailableModel())
        
        snapshot = MatchFeatureSnapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
        )
        
        result = orchestrator.run_all(snapshot)
        
        assert result.total_models == 1
        assert len(result.successful_predictions) == 0
        assert len(result.unavailable_models) == 1
        assert len(result.failed_models) == 0
        assert not result.has_predictions
    
    def test_run_failing_model(self):
        """Test running a model that raises exception."""
        orchestrator = ModelOrchestrator()
        orchestrator.register_model(MockFailingModel())
        
        snapshot = MatchFeatureSnapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
        )
        
        result = orchestrator.run_all(snapshot)
        
        assert result.total_models == 1
        assert len(result.successful_predictions) == 0
        assert len(result.unavailable_models) == 0
        assert len(result.failed_models) == 1
        assert not result.has_predictions
        
        failed_output = result.failed_models[0]
        assert failed_output.error_message == "Test failure"
        assert failed_output.error_traceback is not None
    
    def test_partial_failure_does_not_kill_pipeline(self):
        """Test that failure of one model doesn't prevent others from running."""
        orchestrator = ModelOrchestrator()
        orchestrator.register_model(MockSuccessfulModel())
        orchestrator.register_model(MockFailingModel())
        orchestrator.register_model(MockUnavailableModel())
        
        snapshot = MatchFeatureSnapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
            home_strength=TeamStrengthMetrics(goals_scored_per_match=1.5),
        )
        
        result = orchestrator.run_all(snapshot)
        
        # Should have executed all 3 models
        assert result.total_models == 3
        assert len(result.successful_predictions) == 1
        assert len(result.unavailable_models) == 1
        assert len(result.failed_models) == 1
        
        # Pipeline should continue despite failures
        assert result.has_predictions
        assert result.success_rate == 1.0 / 3.0
    
    def test_create_default_registry(self):
        """Test creating default orchestrator with all models."""
        orchestrator = ModelOrchestrator.create_default_registry()
        
        registered = orchestrator.get_registered_models()
        
        # Should have 7 standard models
        assert len(registered) == 7
        
        # Check key models are registered
        assert any("poisson" in model_id.lower() for model_id in registered)
        assert any("elo" in model_id.lower() for model_id in registered)
        assert any("monte_carlo" in model_id.lower() for model_id in registered)
    
    def test_orchestration_preserves_metadata(self):
        """Test that orchestration preserves snapshot metadata."""
        orchestrator = ModelOrchestrator()
        orchestrator.register_model(MockSuccessfulModel())
        
        snapshot = MatchFeatureSnapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
            home_strength=TeamStrengthMetrics(goals_scored_per_match=1.5),
        )
        
        result = orchestrator.run_all(snapshot)
        
        assert result.execution_metadata["match_id"] == "match_123"
        assert result.execution_metadata["snapshot_version"] == "1.0.0"
        assert result.orchestration_timestamp is not None
