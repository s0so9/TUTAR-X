"""Tests for ensemble integration with model orchestrator."""

import pytest
from app.prediction.model_orchestrator import (
    ModelOrchestrator,
    ModelOrchestrationResult,
    ModelOutput,
    ModelStatus,
    EnsembleIntegration,
)
from app.prediction.interfaces import ModelPrediction, ModelAvailability
from app.prediction.ensemble_engine import EnsembleEngine, ReliabilityWeights, StaticWeights


class TestEnsembleIntegration:
    """Test EnsembleIntegration class."""
    
    def test_create_default(self):
        """Test creating default ensemble integration."""
        integration = EnsembleIntegration.create_default()
        
        assert integration is not None
        assert integration.engine is not None
        assert isinstance(integration.engine.strategy, ReliabilityWeights)
    
    def test_combine_with_no_predictions(self):
        """Test ensemble returns unavailable when no successful predictions."""
        integration = EnsembleIntegration.create_default()
        
        # Empty orchestration result
        orchestration_result = ModelOrchestrationResult(
            total_models=0,
            successful_predictions=[],
        )
        
        result = integration.combine_predictions(orchestration_result)
        
        assert isinstance(result, ModelAvailability)
        assert not result.available
        assert "no successful" in result.reason.lower()
    
    def test_combine_with_single_prediction_returns_unavailable(self):
        """Test ensemble returns unavailable with only 1 prediction (needs ≥2)."""
        integration = EnsembleIntegration.create_default()
        
        # Single successful prediction
        pred = ModelPrediction(
            model_id="poisson_v1",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.85,
        )
        
        output = ModelOutput(
            model_id="poisson_v1",
            model_version="1.0.0",
            status=ModelStatus.SUPPORTED_RUN,
            prediction=pred,
        )
        
        orchestration_result = ModelOrchestrationResult(
            total_models=1,
            successful_predictions=[output],
        )
        
        result = integration.combine_predictions(orchestration_result)
        
        # Ensemble engine requires ≥2 models
        assert isinstance(result, ModelAvailability)
        assert "insufficient_models" in result.reason or "at least 2" in result.reason.lower()
    
    def test_combine_with_two_predictions(self):
        """Test ensemble combines two predictions successfully."""
        integration = EnsembleIntegration.create_default()
        
        # Two successful predictions
        pred1 = ModelPrediction(
            model_id="poisson_v1",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.85,
        )
        
        pred2 = ModelPrediction(
            model_id="elo_v1",
            home_score_mean=1.6,
            away_score_mean=1.1,
            home_win_prob=0.50,
            draw_prob=0.28,
            away_win_prob=0.22,
            confidence_score=0.75,
            data_quality_score=0.80,
        )
        
        output1 = ModelOutput(
            model_id="poisson_v1",
            model_version="1.0.0",
            status=ModelStatus.SUPPORTED_RUN,
            prediction=pred1,
        )
        
        output2 = ModelOutput(
            model_id="elo_v1",
            model_version="1.0.0",
            status=ModelStatus.SUPPORTED_RUN,
            prediction=pred2,
        )
        
        orchestration_result = ModelOrchestrationResult(
            total_models=2,
            successful_predictions=[output1, output2],
        )
        
        result = integration.combine_predictions(orchestration_result)
        
        # Should return ensemble prediction
        assert isinstance(result, ModelPrediction)
        assert result.model_id == "ensemble_v1"
        
        # Probabilities should sum to 1.0
        total = result.home_win_prob + result.draw_prob + result.away_win_prob
        assert 0.999 <= total <= 1.001
        
        # Metadata should include ensemble info
        assert "model_agreement" in result.metadata
        assert "model_weights" in result.metadata
        assert "n_models" in result.metadata
        assert result.metadata["n_models"] == 2
    
    def test_model_agreement_calculation(self):
        """Test that model agreement is calculated from actual predictions."""
        integration = EnsembleIntegration.create_default()
        
        # Two predictions with HIGH agreement
        pred1 = ModelPrediction(
            model_id="model1",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.85,
        )
        
        pred2 = ModelPrediction(
            model_id="model2",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.46,  # Very close to pred1
            draw_prob=0.29,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.85,
        )
        
        orchestration_result = ModelOrchestrationResult(
            total_models=2,
            successful_predictions=[
                ModelOutput("model1", "1.0", ModelStatus.SUPPORTED_RUN, prediction=pred1),
                ModelOutput("model2", "1.0", ModelStatus.SUPPORTED_RUN, prediction=pred2),
            ]
        )
        
        result = integration.combine_predictions(orchestration_result)
        
        assert isinstance(result, ModelPrediction)
        agreement = result.metadata["model_agreement"]
        
        # High agreement (predictions very similar)
        assert agreement > 0.9
    
    def test_model_agreement_with_disagreement(self):
        """Test model agreement when predictions disagree."""
        integration = EnsembleIntegration.create_default()
        
        # Two predictions with LOW agreement
        pred1 = ModelPrediction(
            model_id="model1",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.60,  # High home win
            draw_prob=0.25,
            away_win_prob=0.15,
            confidence_score=0.8,
            data_quality_score=0.85,
        )
        
        pred2 = ModelPrediction(
            model_id="model2",
            home_score_mean=1.2,
            away_score_mean=1.5,
            home_win_prob=0.30,  # Low home win (disagrees)
            draw_prob=0.25,
            away_win_prob=0.45,
            confidence_score=0.8,
            data_quality_score=0.85,
        )
        
        orchestration_result = ModelOrchestrationResult(
            total_models=2,
            successful_predictions=[
                ModelOutput("model1", "1.0", ModelStatus.SUPPORTED_RUN, prediction=pred1),
                ModelOutput("model2", "1.0", ModelStatus.SUPPORTED_RUN, prediction=pred2),
            ]
        )
        
        result = integration.combine_predictions(orchestration_result)
        
        assert isinstance(result, ModelPrediction)
        agreement = result.metadata["model_agreement"]
        
        # Low agreement (predictions disagree significantly)
        assert agreement < 0.7
    
    def test_custom_weighting_strategy(self):
        """Test ensemble with custom static weights."""
        # Custom weights: poisson_v1 gets 70%, elo_v1 gets 30%
        static_weights = StaticWeights(weights={
            "poisson_v1": 0.7,
            "elo_v1": 0.3,
        })
        engine = EnsembleEngine(strategy=static_weights)
        integration = EnsembleIntegration(engine=engine)
        
        pred1 = ModelPrediction(
            model_id="poisson_v1",
            home_score_mean=2.0,
            away_score_mean=1.0,
            home_win_prob=0.60,
            draw_prob=0.25,
            away_win_prob=0.15,
            confidence_score=0.8,
            data_quality_score=0.85,
        )
        
        pred2 = ModelPrediction(
            model_id="elo_v1",
            home_score_mean=1.0,
            away_score_mean=2.0,
            home_win_prob=0.20,
            draw_prob=0.30,
            away_win_prob=0.50,
            confidence_score=0.8,
            data_quality_score=0.85,
        )
        
        orchestration_result = ModelOrchestrationResult(
            total_models=2,
            successful_predictions=[
                ModelOutput("poisson_v1", "1.0", ModelStatus.SUPPORTED_RUN, prediction=pred1),
                ModelOutput("elo_v1", "1.0", ModelStatus.SUPPORTED_RUN, prediction=pred2),
            ]
        )
        
        result = integration.combine_predictions(orchestration_result)
        
        assert isinstance(result, ModelPrediction)
        
        # Result should be weighted more toward poisson (70%)
        # Expected: 0.60*0.7 + 0.20*0.3 = 0.42 + 0.06 = 0.48 (before normalization)
        # Since normalized, should be closer to poisson's 0.60 than elo's 0.20
        assert result.home_win_prob > 0.40
