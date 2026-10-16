"""Tests for confidence integration."""

import pytest
from app.prediction.model_orchestrator import (
    ConfidenceIntegration,
    ModelOrchestrationResult,
    ModelOutput,
    ModelStatus,
)
from app.prediction.feature_snapshot import (
    MatchFeatureSnapshot,
    FormMetrics,
    PlayerAvailability,
    LineupStatus,
)
from app.prediction.interfaces import ModelPrediction
from app.prediction.data_quality import DataQualityReport


class TestConfidenceIntegration:
    """Test ConfidenceIntegration class."""
    
    def test_create_default(self):
        """Test creating default confidence integration."""
        integration = ConfidenceIntegration.create_default()
        
        assert integration is not None
        assert integration.engine is not None
    
    def test_assess_with_real_model_agreement(self):
        """Test confidence uses real model agreement from ensemble."""
        integration = ConfidenceIntegration.create_default()
        
        # Create ensemble prediction with HIGH agreement
        ensemble_pred = ModelPrediction(
            model_id="ensemble_v1",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.85,
            metadata={"model_agreement": 0.95}  # HIGH agreement
        )
        
        snapshot = MatchFeatureSnapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
        )
        
        orchestration_result = ModelOrchestrationResult(total_models=2)
        
        assessment = integration.assess_confidence(
            snapshot=snapshot,
            orchestration_result=orchestration_result,
            ensemble_prediction=ensemble_pred,
        )
        
        # Check that assessment uses the real agreement value
        assert assessment.components.model_agreement == 0.95
        
        # High agreement should contribute to higher confidence
        assert assessment.overall_confidence > 0.5
    
    def test_assess_with_low_model_agreement(self):
        """Test confidence reflects low model agreement."""
        integration = ConfidenceIntegration.create_default()
        
        # Create ensemble prediction with LOW agreement
        ensemble_pred = ModelPrediction(
            model_id="ensemble_v1",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.85,
            metadata={"model_agreement": 0.30}  # LOW agreement
        )
        
        snapshot = MatchFeatureSnapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
        )
        
        orchestration_result = ModelOrchestrationResult(total_models=2)
        
        assessment = integration.assess_confidence(
            snapshot=snapshot,
            orchestration_result=orchestration_result,
            ensemble_prediction=ensemble_pred,
        )
        
        # Check that assessment uses the real agreement value
        assert assessment.components.model_agreement == 0.30
    
    def test_assess_with_real_data_quality(self):
        """Test confidence uses real data quality from snapshot."""
        integration = ConfidenceIntegration.create_default()
        
        ensemble_pred = ModelPrediction(
            model_id="ensemble_v1",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.85,
            metadata={"model_agreement": 0.85}
        )
        
        # Create snapshot with HIGH data quality
        data_quality_report = DataQualityReport(
            overall_score=0.92,  # HIGH quality
            checks=[],
            passed=5,
            failed=0,
        )
        
        snapshot = MatchFeatureSnapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
            data_quality_report=data_quality_report,
        )
        
        orchestration_result = ModelOrchestrationResult(total_models=2)
        
        assessment = integration.assess_confidence(
            snapshot=snapshot,
            orchestration_result=orchestration_result,
            ensemble_prediction=ensemble_pred,
        )
        
        # Check that assessment uses the real data quality
        assert assessment.components.data_quality == 0.92
    
    def test_assess_with_sample_size(self):
        """Test confidence reflects actual sample sizes."""
        integration = ConfidenceIntegration.create_default()
        
        ensemble_pred = ModelPrediction(
            model_id="ensemble_v1",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.85,
            metadata={"model_agreement": 0.85}
        )
        
        # Large sample size
        snapshot = MatchFeatureSnapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
            home_form=FormMetrics(matches_analyzed=25),
            away_form=FormMetrics(matches_analyzed=30),
        )
        
        orchestration_result = ModelOrchestrationResult(total_models=2)
        
        assessment = integration.assess_confidence(
            snapshot=snapshot,
            orchestration_result=orchestration_result,
            ensemble_prediction=ensemble_pred,
        )
        
        # Large sample should give reasonable sample_size_score
        assert assessment.components.sample_size_score > 0.3
    
    def test_assess_with_small_sample_size(self):
        """Test confidence reflects small sample size."""
        integration = ConfidenceIntegration.create_default()
        
        ensemble_pred = ModelPrediction(
            model_id="ensemble_v1",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.85,
            metadata={"model_agreement": 0.85}
        )
        
        # Small sample size
        snapshot = MatchFeatureSnapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
            home_form=FormMetrics(matches_analyzed=3),
            away_form=FormMetrics(matches_analyzed=2),
        )
        
        orchestration_result = ModelOrchestrationResult(total_models=2)
        
        assessment = integration.assess_confidence(
            snapshot=snapshot,
            orchestration_result=orchestration_result,
            ensemble_prediction=ensemble_pred,
        )
        
        # Small sample should give low sample_size_score
        assert assessment.components.sample_size_score < 0.6
    
    def test_assess_with_lineup_certainty(self):
        """Test confidence uses lineup status."""
        integration = ConfidenceIntegration.create_default()
        
        ensemble_pred = ModelPrediction(
            model_id="ensemble_v1",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.85,
            metadata={"model_agreement": 0.85}
        )
        
        # Confirmed lineups
        snapshot = MatchFeatureSnapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
            home_player_availability=PlayerAvailability(
                lineup_status=LineupStatus.CONFIRMED
            ),
            away_player_availability=PlayerAvailability(
                lineup_status=LineupStatus.CONFIRMED
            ),
        )
        
        orchestration_result = ModelOrchestrationResult(total_models=2)
        
        assessment = integration.assess_confidence(
            snapshot=snapshot,
            orchestration_result=orchestration_result,
            ensemble_prediction=ensemble_pred,
        )
        
        # Confirmed lineups should give high certainty
        assert assessment.components.lineup_certainty >= 0.9
    
    def test_no_hardcoded_model_agreement(self):
        """Test that model_agreement is NEVER hardcoded to 1.0."""
        integration = ConfidenceIntegration.create_default()
        
        # Ensemble with moderate agreement
        ensemble_pred = ModelPrediction(
            model_id="ensemble_v1",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.85,
            metadata={"model_agreement": 0.65}  # Moderate
        )
        
        snapshot = MatchFeatureSnapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
        )
        
        orchestration_result = ModelOrchestrationResult(total_models=2)
        
        assessment = integration.assess_confidence(
            snapshot=snapshot,
            orchestration_result=orchestration_result,
            ensemble_prediction=ensemble_pred,
        )
        
        # Must use the actual value, not hardcoded 1.0
        assert assessment.components.model_agreement == 0.65
        assert assessment.components.model_agreement != 1.0
    
    def test_no_hardcoded_data_quality(self):
        """Test that data_quality is NEVER hardcoded to 0.7."""
        integration = ConfidenceIntegration.create_default()
        
        ensemble_pred = ModelPrediction(
            model_id="ensemble_v1",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.85,
            metadata={"model_agreement": 0.85}
        )
        
        # Specific data quality
        data_quality_report = DataQualityReport(
            overall_score=0.55,
            checks=[],
            passed=3,
            failed=2,
        )
        
        snapshot = MatchFeatureSnapshot(
            match_id="match_123",
            home_team_id="team_home",
            away_team_id="team_away",
            data_quality_report=data_quality_report,
        )
        
        orchestration_result = ModelOrchestrationResult(total_models=2)
        
        assessment = integration.assess_confidence(
            snapshot=snapshot,
            orchestration_result=orchestration_result,
            ensemble_prediction=ensemble_pred,
        )
        
        # Must use the actual value, not hardcoded 0.7
        assert assessment.components.data_quality == 0.55
        assert assessment.components.data_quality != 0.7
