"""Tests for PredictionVersion frozen picks and result tracking - FEAT-004."""

import pytest
from datetime import datetime

from app.prediction.prediction_version import (
    PredictionVersion,
    PredictionVersionManager,
    PredictionStage
)


class TestFrozenPickFields:
    """Test frozen pick field storage and retrieval."""
    
    def test_create_version_with_best_tip_populates_frozen_fields(self):
        """Test that BestTip dict correctly populates frozen pick fields."""
        manager = PredictionVersionManager()
        
        # Simulate BestTip dict structure
        best_tip_dict = {
            "market": "HOME_WIN",
            "selection": "Home Win",
            "probability": 0.65,
            "confidence": 0.75,
            "model_agreement": 0.85,
            "data_quality": 0.80,
            "bookmaker_odds": 2.10,
            "fair_odds": 1.54,
            "edge": 0.15,
            "value_classification": "VALUE",
            "risk_level": "MEDIUM",
            "selection_score": 0.82,
            "selector_reason": "High probability with positive edge",
            "timestamp": "2026-06-15T12:00:00",
            "pipeline_version": "1.0.0",
            "pass_decision": False
        }
        
        prediction_data = {
            "home_win_prob": 0.65,
            "draw_prob": 0.25,
            "away_win_prob": 0.10,
            "mensione_pick": best_tip_dict
        }
        
        version = manager.create_version(
            match_id="match_best_tip",
            stage=PredictionStage.KICKOFF,
            prediction_data=prediction_data,
            confidence_score=0.75,
            mensione_pick=best_tip_dict
        )
        
        # Verify frozen pick fields are populated
        assert version.selected_market == "HOME_WIN"
        assert version.selection_text == "Home Win"
        assert version.selection_probability == 0.65
        assert version.selection_confidence == 0.75
        assert version.selection_odds == 2.10
        assert version.selection_fair_odds == 1.54
        assert version.selection_edge == 0.15
        assert version.value_classification == "VALUE"
        assert version.risk_level == "MEDIUM"
        
        # Verify result tracking fields remain None
        assert version.actual_result is None
        assert version.profit_loss is None
        assert version.settled_at is None
    
    def test_create_version_with_pass_decision_leaves_frozen_fields_none(self):
        """Test that PassDecision dict leaves frozen pick fields as None."""
        manager = PredictionVersionManager()
        
        # Simulate PassDecision dict structure
        pass_decision_dict = {
            "pass_decision": True,
            "match_id": "match_pass",
            "pass_reason": "no_qualifying_market",
            "evaluated_markets_count": 12,
            "best_market_details": {
                "market": "HOME_WIN",
                "probability": 0.48,
                "confidence": 0.35
            },
            "timestamp": "2026-06-15T12:00:00",
            "pipeline_version": "1.0.0"
        }
        
        prediction_data = {
            "home_win_prob": 0.48,
            "draw_prob": 0.30,
            "away_win_prob": 0.22,
            "mensione_pick": pass_decision_dict
        }
        
        version = manager.create_version(
            match_id="match_pass",
            stage=PredictionStage.KICKOFF,
            prediction_data=prediction_data,
            confidence_score=0.35,
            mensione_pick=pass_decision_dict
        )
        
        # Verify all frozen pick fields remain None for PASS
        assert version.selected_market is None
        assert version.selection_text is None
        assert version.selection_probability is None
        assert version.selection_confidence is None
        assert version.selection_odds is None
        assert version.selection_fair_odds is None
        assert version.selection_edge is None
        assert version.value_classification is None
        assert version.risk_level is None
        
        # Verify result tracking fields remain None
        assert version.actual_result is None
        assert version.profit_loss is None
        assert version.settled_at is None
    
    def test_create_version_without_mensione_pick_leaves_frozen_fields_none(self):
        """Test that create_version without mensione_pick leaves frozen fields as None."""
        manager = PredictionVersionManager()
        
        prediction_data = {
            "home_win_prob": 0.50,
            "draw_prob": 0.30,
            "away_win_prob": 0.20
        }
        
        # Call create_version WITHOUT mensione_pick parameter
        version = manager.create_version(
            match_id="match_no_pick",
            stage=PredictionStage.KICKOFF,
            prediction_data=prediction_data,
            confidence_score=0.60
        )
        
        # Verify all frozen pick fields remain None
        assert version.selected_market is None
        assert version.selection_text is None
        assert version.selection_probability is None
        assert version.selection_confidence is None
        assert version.selection_odds is None
        assert version.selection_fair_odds is None
        assert version.selection_edge is None
        assert version.value_classification is None
        assert version.risk_level is None
        
        # Verify result tracking fields remain None
        assert version.actual_result is None
        assert version.profit_loss is None
        assert version.settled_at is None
    
    def test_frozen_pick_preserves_all_fields(self):
        """Test that all frozen pick fields are preserved exactly as provided."""
        manager = PredictionVersionManager()
        
        # Test with comprehensive BestTip data
        best_tip = {
            "market": "OVER_2_5",
            "selection": "Over 2.5 Goals",
            "probability": 0.72,
            "confidence": 0.68,
            "model_agreement": 0.90,
            "data_quality": 0.85,
            "bookmaker_odds": 1.95,
            "fair_odds": 1.39,
            "edge": 0.21,
            "value_classification": "STRONG_VALUE",
            "risk_level": "LOW",
            "selection_score": 0.88,
            "selector_reason": "Strong model agreement with excellent edge",
            "timestamp": "2026-06-20T18:30:00",
            "pipeline_version": "1.0.0",
            "pass_decision": False
        }
        
        version = manager.create_version(
            match_id="match_comprehensive",
            stage=PredictionStage.LINEUP_CONFIRMED,
            prediction_data={"mensione_pick": best_tip},
            confidence_score=0.68,
            mensione_pick=best_tip
        )
        
        # Verify exact preservation of all fields
        assert version.selected_market == "OVER_2_5"
        assert version.selection_text == "Over 2.5 Goals"
        assert version.selection_probability == 0.72
        assert version.selection_confidence == 0.68
        assert version.selection_odds == 1.95  # bookmaker_odds stored as selection_odds
        assert version.selection_fair_odds == 1.39
        assert version.selection_edge == 0.21
        assert version.value_classification == "STRONG_VALUE"
        assert version.risk_level == "LOW"
    
    def test_frozen_pick_with_no_bookmaker_odds(self):
        """Test frozen pick when bookmaker_odds is None (no odds available)."""
        manager = PredictionVersionManager()
        
        best_tip = {
            "market": "BTTS_YES",
            "selection": "Both Teams to Score",
            "probability": 0.58,
            "confidence": 0.55,
            "bookmaker_odds": None,  # No odds available
            "fair_odds": 1.72,
            "edge": None,  # No edge calculation possible
            "value_classification": "NEUTRAL",
            "risk_level": "MEDIUM"
        }
        
        version = manager.create_version(
            match_id="match_no_odds",
            stage=PredictionStage.KICKOFF,
            prediction_data={"mensione_pick": best_tip},
            confidence_score=0.55,
            mensione_pick=best_tip
        )
        
        # Verify None values are preserved
        assert version.selected_market == "BTTS_YES"
        assert version.selection_odds is None
        assert version.selection_edge is None
        assert version.value_classification == "NEUTRAL"


class TestResultTrackingFields:
    """Test result tracking field initialization and stub methods."""
    
    def test_result_tracking_fields_initially_none(self):
        """Test that result tracking fields are None after create_version."""
        manager = PredictionVersionManager()
        
        best_tip = {
            "market": "AWAY_WIN",
            "selection": "Away Win",
            "probability": 0.55,
            "confidence": 0.60,
            "bookmaker_odds": 2.50,
            "fair_odds": 1.82,
            "edge": 0.15,
            "value_classification": "VALUE",
            "risk_level": "MEDIUM"
        }
        
        version = manager.create_version(
            match_id="match_result_tracking",
            stage=PredictionStage.KICKOFF,
            prediction_data={"mensione_pick": best_tip},
            confidence_score=0.60,
            mensione_pick=best_tip
        )
        
        # Verify result tracking fields are all None initially
        assert version.actual_result is None
        assert version.profit_loss is None
        assert version.settled_at is None
    
    def test_settle_prediction_raises_not_implemented(self):
        """Test that settle_prediction() raises ValueError when result is missing."""
        # This test was updated after Phase 6 implementation
        # Settlement is now implemented, but we test error handling
        manager = PredictionVersionManager()
        
        best_tip = {
            "market": "HOME_WIN",
            "selection": "Home Win",
            "probability": 0.55,
            "confidence": 0.60,
            "bookmaker_odds": 2.50,
            "fair_odds": 1.82,
            "edge": 0.15,
            "value_classification": "VALUE",
            "risk_level": "MEDIUM"
        }
        
        version = manager.create_version(
            match_id="match_settle",
            stage=PredictionStage.KICKOFF,
            prediction_data={"home_win_prob": 0.50},
            confidence_score=0.60,
            mensione_pick=best_tip
        )
        
        # Attempt to settle without provider should raise ValueError
        from app.providers.base import FootballDataProvider
        
        class MockProvider(FootballDataProvider):
            def get_provider_name(self): return "mock"
            def is_development_data(self): return True
            def get_competitions(self): return []
            def get_competition(self, competition_id): return None
            def get_seasons(self, competition_id): return []
            def get_current_season(self, competition_id): return None
            def get_teams(self, competition_id, season_id): return []
            def get_team(self, team_id): return None
            def get_matches(self, **kwargs): return []
            def get_match(self, match_id): return None
        
        provider = MockProvider()
        
        # Should raise ValueError because match not found
        with pytest.raises(ValueError, match="not found"):
            manager.settle_prediction(
                version_id=version.version_id,
                provider=provider,
                stake=1.0
            )
    
    def test_get_settled_picks_by_market_raises_not_implemented(self):
        """Test that get_settled_picks_by_market() returns empty list."""
        # This test was updated after Phase 7 implementation
        # Method is now implemented
        manager = PredictionVersionManager()
        
        # Should return empty list, not raise error
        result = manager.get_settled_picks_by_market(
            market_type="HOME_WIN",
            start_date=datetime(2026, 1, 1),
            end_date=datetime(2026, 12, 31)
        )
        
        assert result == []


class TestFrozenPickIntegration:
    """Test integration between frozen picks and existing versioning functionality."""
    
    def test_frozen_pick_preserved_across_version_retrieval(self):
        """Test that frozen pick data survives get_versions() retrieval."""
        manager = PredictionVersionManager()
        
        best_tip = {
            "market": "HOME_OR_DRAW",
            "selection": "Home or Draw",
            "probability": 0.78,
            "confidence": 0.70,
            "bookmaker_odds": 1.40,
            "fair_odds": 1.28,
            "edge": 0.07,
            "value_classification": "VALUE",
            "risk_level": "LOW"
        }
        
        original_version = manager.create_version(
            match_id="match_retrieve",
            stage=PredictionStage.TWENTY_FOUR_HOURS_BEFORE,
            prediction_data={"mensione_pick": best_tip},
            confidence_score=0.70,
            mensione_pick=best_tip
        )
        
        # Retrieve versions
        versions = manager.get_versions("match_retrieve")
        assert len(versions) == 1
        
        retrieved_version = versions[0]
        
        # Verify frozen pick data is preserved
        assert retrieved_version.version_id == original_version.version_id
        assert retrieved_version.selected_market == "HOME_OR_DRAW"
        assert retrieved_version.selection_text == "Home or Draw"
        assert retrieved_version.selection_probability == 0.78
        assert retrieved_version.selection_confidence == 0.70
        assert retrieved_version.selection_odds == 1.40
        assert retrieved_version.selection_fair_odds == 1.28
        assert retrieved_version.selection_edge == 0.07
        assert retrieved_version.value_classification == "VALUE"
        assert retrieved_version.risk_level == "LOW"
    
    def test_frozen_pick_preserved_with_stage_retrieval(self):
        """Test that frozen pick data survives get_version_by_stage() retrieval."""
        manager = PredictionVersionManager()
        
        best_tip = {
            "market": "UNDER_3_5",
            "selection": "Under 3.5 Goals",
            "probability": 0.68,
            "confidence": 0.62,
            "bookmaker_odds": 1.75,
            "fair_odds": 1.47,
            "edge": 0.11,
            "value_classification": "VALUE",
            "risk_level": "MEDIUM"
        }
        
        manager.create_version(
            match_id="match_stage_retrieve",
            stage=PredictionStage.SEVEN_DAYS_BEFORE,
            prediction_data={"mensione_pick": best_tip},
            confidence_score=0.62,
            mensione_pick=best_tip
        )
        
        # Retrieve by stage
        stage_version = manager.get_version_by_stage(
            "match_stage_retrieve",
            PredictionStage.SEVEN_DAYS_BEFORE
        )
        
        assert stage_version is not None
        assert stage_version.selected_market == "UNDER_3_5"
        assert stage_version.selection_probability == 0.68
        assert stage_version.risk_level == "MEDIUM"
    
    def test_multiple_versions_with_different_frozen_picks(self):
        """Test that different stages can have different frozen picks."""
        manager = PredictionVersionManager()
        
        # 7 days before: HOME_WIN
        pick_7d = {
            "market": "HOME_WIN",
            "selection": "Home Win",
            "probability": 0.55,
            "confidence": 0.50,
            "bookmaker_odds": 2.20,
            "fair_odds": 1.82,
            "edge": 0.10,
            "value_classification": "VALUE",
            "risk_level": "MEDIUM"
        }
        
        v_7d = manager.create_version(
            match_id="match_evolution",
            stage=PredictionStage.SEVEN_DAYS_BEFORE,
            prediction_data={"mensione_pick": pick_7d},
            confidence_score=0.50,
            mensione_pick=pick_7d
        )
        
        # 24h before: PASS decision
        pick_24h = {
            "pass_decision": True,
            "match_id": "match_evolution",
            "pass_reason": "negative_value",
            "evaluated_markets_count": 15
        }
        
        v_24h = manager.create_version(
            match_id="match_evolution",
            stage=PredictionStage.TWENTY_FOUR_HOURS_BEFORE,
            prediction_data={"mensione_pick": pick_24h},
            confidence_score=0.40,
            mensione_pick=pick_24h
        )
        
        # Kickoff: OVER_2_5
        pick_kickoff = {
            "market": "OVER_2_5",
            "selection": "Over 2.5 Goals",
            "probability": 0.70,
            "confidence": 0.68,
            "bookmaker_odds": 1.85,
            "fair_odds": 1.43,
            "edge": 0.16,
            "value_classification": "VALUE",
            "risk_level": "LOW"
        }
        
        v_kickoff = manager.create_version(
            match_id="match_evolution",
            stage=PredictionStage.KICKOFF,
            prediction_data={"mensione_pick": pick_kickoff},
            confidence_score=0.68,
            mensione_pick=pick_kickoff
        )
        
        # Verify each stage has correct frozen pick
        versions = manager.get_versions("match_evolution")
        assert len(versions) == 3
        
        # 7d version has HOME_WIN pick
        assert versions[0].selected_market == "HOME_WIN"
        assert versions[0].selection_probability == 0.55
        
        # 24h version has PASS (all fields None)
        assert versions[1].selected_market is None
        assert versions[1].selection_probability is None
        
        # Kickoff version has OVER_2_5 pick
        assert versions[2].selected_market == "OVER_2_5"
        assert versions[2].selection_probability == 0.70
    
    def test_frozen_pick_immutability_external_modification(self):
        """Test that modifying source mensione_pick dict doesn't affect stored version."""
        manager = PredictionVersionManager()
        
        # Create mutable pick dict
        best_tip = {
            "market": "DRAW",
            "selection": "Draw",
            "probability": 0.40,
            "confidence": 0.50,
            "bookmaker_odds": 3.50,
            "fair_odds": 2.50,
            "edge": 0.11,
            "value_classification": "VALUE",
            "risk_level": "MEDIUM"
        }
        
        version = manager.create_version(
            match_id="match_immutable",
            stage=PredictionStage.KICKOFF,
            prediction_data={"mensione_pick": best_tip},
            confidence_score=0.50,
            mensione_pick=best_tip
        )
        
        # Modify original dict
        best_tip["market"] = "HOME_WIN"
        best_tip["probability"] = 0.99
        best_tip["bookmaker_odds"] = 1.10
        
        # Verify stored version unchanged
        retrieved = manager.get_latest_version("match_immutable")
        assert retrieved.selected_market == "DRAW"
        assert retrieved.selection_probability == 0.40
        assert retrieved.selection_odds == 3.50
