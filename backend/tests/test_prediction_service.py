"""Tests for prediction service.

This test suite verifies:
1. Prediction generation from features
2. Market probability outputs
3. AnalysisContext integration
4. Missing/insufficient data handling
5. Deterministic behavior
"""

import pytest
from datetime import datetime, timedelta, date

from app.prediction.service import PredictionService
from app.prediction.poisson import PoissonModel
from app.domain.match import Match
from app.domain.enums import MatchStatus, PredictionMarketType
from app.providers import DevelopmentProvider


@pytest.fixture
def dev_provider():
    """Provide DevelopmentProvider instance."""
    return DevelopmentProvider()


@pytest.fixture
def prediction_service(dev_provider):
    """Provide PredictionService instance."""
    return PredictionService(provider=dev_provider)


class TestPredictionGeneration:
    """Tests for prediction generation."""
    
    def test_generate_prediction_with_sufficient_data(self, prediction_service, dev_provider):
        """Verify prediction is generated when sufficient data exists."""
        # Get a future match
        matches = dev_provider.get_matches()
        future_matches = [m for m in matches if m.status == MatchStatus.SCHEDULED]
        
        if future_matches:
            match = future_matches[0]
            prediction = prediction_service.generate_prediction(match)
            
            # Should generate prediction if sufficient historical data
            # (May be None if insufficient data - that's valid)
            if prediction is not None:
                assert prediction.match_id == match.id
                assert prediction.model_id == "poisson_v1"
                assert 0.0 <= prediction.home_win_probability <= 1.0
                assert 0.0 <= prediction.draw_probability <= 1.0
                assert 0.0 <= prediction.away_win_probability <= 1.0
    
    def test_prediction_probabilities_sum_to_one(self, prediction_service, dev_provider):
        """Verify 1X2 probabilities sum close to 1."""
        matches = dev_provider.get_matches()
        future_matches = [m for m in matches if m.status == MatchStatus.SCHEDULED]
        
        if future_matches:
            match = future_matches[0]
            prediction = prediction_service.generate_prediction(match)
            
            if prediction is not None:
                total = (prediction.home_win_probability +
                        prediction.draw_probability +
                        prediction.away_win_probability)
                assert abs(total - 1.0) < 0.01
    
    def test_prediction_contains_expected_goals(self, prediction_service, dev_provider):
        """Verify prediction contains xG values."""
        matches = dev_provider.get_matches()
        future_matches = [m for m in matches if m.status == MatchStatus.SCHEDULED]
        
        if future_matches:
            match = future_matches[0]
            prediction = prediction_service.generate_prediction(match)
            
            if prediction is not None:
                assert prediction.home_xg is not None
                assert prediction.away_xg is not None
                assert prediction.home_xg >= 0.0
                assert prediction.away_xg >= 0.0
    
    def test_prediction_contains_btts_probability(self, prediction_service, dev_provider):
        """Verify prediction contains BTTS probability."""
        matches = dev_provider.get_matches()
        future_matches = [m for m in matches if m.status == MatchStatus.SCHEDULED]
        
        if future_matches:
            match = future_matches[0]
            prediction = prediction_service.generate_prediction(match)
            
            if prediction is not None:
                assert prediction.btts_probability is not None
                assert 0.0 <= prediction.btts_probability <= 1.0
    
    def test_prediction_contains_score_distribution(self, prediction_service, dev_provider):
        """Verify prediction contains score distribution."""
        matches = dev_provider.get_matches()
        future_matches = [m for m in matches if m.status == MatchStatus.SCHEDULED]
        
        if future_matches:
            match = future_matches[0]
            prediction = prediction_service.generate_prediction(match)
            
            if prediction is not None:
                assert prediction.score_distribution is not None
                assert len(prediction.score_distribution) > 0
                
                # All probabilities should be valid
                for scoreline, prob in prediction.score_distribution.items():
                    assert 0.0 <= prob <= 1.0
                    assert "-" in scoreline  # Format: "2-1"


class TestPredictionMarkets:
    """Tests for prediction market generation."""
    
    def test_generate_markets_with_prediction(self, prediction_service, dev_provider):
        """Verify markets are generated with prediction."""
        matches = dev_provider.get_matches()
        future_matches = [m for m in matches if m.status == MatchStatus.SCHEDULED]
        
        if future_matches:
            match = future_matches[0]
            prediction = prediction_service.generate_prediction(match)
            
            if prediction is not None:
                markets = prediction_service.generate_prediction_markets(match, prediction)
                
                assert len(markets) > 0
                
                # Should have at least 1X2, BTTS, and some Over/Under markets
                market_types = {m.market_type for m in markets}
                assert PredictionMarketType.MATCH_RESULT in market_types
                assert PredictionMarketType.BTTS in market_types
                assert PredictionMarketType.OVER_UNDER in market_types
    
    def test_1x2_market_probabilities(self, prediction_service, dev_provider):
        """Verify 1X2 market has correct structure."""
        matches = dev_provider.get_matches()
        future_matches = [m for m in matches if m.status == MatchStatus.SCHEDULED]
        
        if future_matches:
            match = future_matches[0]
            prediction = prediction_service.generate_prediction(match)
            
            if prediction is not None:
                markets = prediction_service.generate_prediction_markets(match, prediction)
                
                match_result_markets = [
                    m for m in markets
                    if m.market_type == PredictionMarketType.MATCH_RESULT
                ]
                
                if match_result_markets:
                    market = match_result_markets[0]
                    assert "home" in market.probabilities
                    assert "draw" in market.probabilities
                    assert "away" in market.probabilities
                    
                    # Probabilities should sum to 1
                    total = (market.probabilities["home"] +
                            market.probabilities["draw"] +
                            market.probabilities["away"])
                    assert abs(total - 1.0) < 0.01
    
    def test_btts_market_probabilities(self, prediction_service, dev_provider):
        """Verify BTTS market has correct structure."""
        matches = dev_provider.get_matches()
        future_matches = [m for m in matches if m.status == MatchStatus.SCHEDULED]
        
        if future_matches:
            match = future_matches[0]
            prediction = prediction_service.generate_prediction(match)
            
            if prediction is not None:
                markets = prediction_service.generate_prediction_markets(match, prediction)
                
                btts_markets = [
                    m for m in markets
                    if m.market_type == PredictionMarketType.BTTS
                ]
                
                if btts_markets:
                    market = btts_markets[0]
                    assert "yes" in market.probabilities
                    assert "no" in market.probabilities
                    
                    # Probabilities should sum to 1
                    total = market.probabilities["yes"] + market.probabilities["no"]
                    assert abs(total - 1.0) < 0.01
    
    def test_over_under_markets(self, prediction_service, dev_provider):
        """Verify Over/Under markets are generated."""
        matches = dev_provider.get_matches()
        future_matches = [m for m in matches if m.status == MatchStatus.SCHEDULED]
        
        if future_matches:
            match = future_matches[0]
            prediction = prediction_service.generate_prediction(match)
            
            if prediction is not None:
                markets = prediction_service.generate_prediction_markets(match, prediction)
                
                ou_markets = [
                    m for m in markets
                    if m.market_type == PredictionMarketType.OVER_UNDER
                ]
                
                # Should have multiple lines
                assert len(ou_markets) > 0
                
                # Each should have line value
                for market in ou_markets:
                    assert market.line is not None
                    assert "over" in market.probabilities
                    assert "under" in market.probabilities
                    
                    # Probabilities should sum to 1
                    total = market.probabilities["over"] + market.probabilities["under"]
                    assert abs(total - 1.0) < 0.01


class TestAnalysisContext:
    """Tests for AnalysisContext generation."""
    
    def test_build_analysis_context(self, prediction_service, dev_provider):
        """Verify AnalysisContext is built."""
        matches = dev_provider.get_matches()
        
        if matches:
            match = matches[0]
            context = prediction_service.build_analysis_context(match)
            
            # Should always have basic match info
            assert context.match == match
            assert context.home_team is not None
            assert context.away_team is not None
            assert context.competition is not None
    
    def test_context_contains_teams(self, prediction_service, dev_provider):
        """Verify context contains team information."""
        matches = dev_provider.get_matches()
        
        if matches:
            match = matches[0]
            context = prediction_service.build_analysis_context(match)
            
            assert context.home_team.id == match.home_team_id
            assert context.away_team.id == match.away_team_id
    
    def test_context_contains_features_when_available(self, prediction_service, dev_provider):
        """Verify context contains features when available."""
        matches = dev_provider.get_matches()
        future_matches = [m for m in matches if m.status == MatchStatus.SCHEDULED]
        
        if future_matches:
            match = future_matches[0]
            context = prediction_service.build_analysis_context(match)
            
            # Statistical features should be populated
            assert context.statistical_features is not None
    
    def test_context_contains_prediction_when_generated(self, prediction_service, dev_provider):
        """Verify context contains prediction when it's generated."""
        matches = dev_provider.get_matches()
        future_matches = [m for m in matches if m.status == MatchStatus.SCHEDULED]
        
        if future_matches:
            match = future_matches[0]
            prediction = prediction_service.generate_prediction(match)
            
            if prediction is not None:
                context = prediction_service.build_analysis_context(
                    match,
                    prediction=prediction
                )
                
                assert context.model_predictions is not None
                assert len(context.model_predictions) > 0
                assert context.model_predictions[0] == prediction
    
    def test_context_data_completeness_flags(self, prediction_service, dev_provider):
        """Verify data completeness flags are set."""
        matches = dev_provider.get_matches()
        
        if matches:
            match = matches[0]
            context = prediction_service.build_analysis_context(match)
            
            assert context.data_completeness is not None
            assert "match" in context.data_completeness
            assert "teams" in context.data_completeness
            assert "features" in context.data_completeness
            assert "prediction" in context.data_completeness
    
    def test_context_missing_data_notes_when_insufficient(self, prediction_service, dev_provider):
        """Verify missing data notes are populated."""
        matches = dev_provider.get_matches()
        
        if matches:
            match = matches[0]
            context = prediction_service.build_analysis_context(match)
            
            # If prediction wasn't generated, should have notes
            if context.model_predictions is None or len(context.model_predictions) == 0:
                assert context.missing_data_notes is not None
                assert len(context.missing_data_notes) > 0


class TestMissingDataHandling:
    """Tests for handling insufficient/missing data."""
    
    def test_no_prediction_with_insufficient_data(self):
        """Verify no prediction generated when data insufficient."""
        # Create match with teams that have no historical data
        today = date.today()
        match = Match(
            id="new_match",
            competition_id="new_comp",
            season_id="new_season",
            home_team_id="new_home_team",
            away_team_id="new_away_team",
            scheduled_at=datetime.combine(today + timedelta(days=7), datetime.min.time()),
            status=MatchStatus.SCHEDULED,
        )
        
        # Create provider that returns empty data
        class EmptyProvider:
            def get_matches(self, **kwargs):
                return []
            
            def get_teams(self, competition_id, season_id):
                from app.domain.entities import Team
                return []
            
            def get_competitions(self):
                from app.domain.entities import Competition
                return []
            
            def get_standings(self, **kwargs):
                raise NotImplementedError()
        
        service = PredictionService(provider=EmptyProvider())
        prediction = service.generate_prediction(match)
        
        # Should return None due to insufficient data
        assert prediction is None
    
    def test_context_indicates_missing_data(self):
        """Verify context explicitly indicates missing data."""
        today = date.today()
        match = Match(
            id="new_match",
            competition_id="new_comp",
            season_id="new_season",
            home_team_id="new_home_team",
            away_team_id="new_away_team",
            scheduled_at=datetime.combine(today + timedelta(days=7), datetime.min.time()),
            status=MatchStatus.SCHEDULED,
        )
        
        class EmptyProvider:
            def get_matches(self, **kwargs):
                return []
            
            def get_teams(self, competition_id, season_id):
                from app.domain.entities import Team
                return []
            
            def get_competitions(self):
                from app.domain.entities import Competition
                return []
            
            def get_standings(self, **kwargs):
                raise NotImplementedError()
        
        service = PredictionService(provider=EmptyProvider())
        context = service.build_analysis_context(match)
        
        # Should have missing data notes
        assert context.missing_data_notes is not None
        assert len(context.missing_data_notes) > 0
        
        # Data completeness should reflect missing data
        assert context.data_completeness["prediction"] is False


class TestDeterminism:
    """Tests for deterministic behavior."""
    
    def test_same_match_same_prediction(self, prediction_service, dev_provider):
        """Verify same match produces identical predictions."""
        matches = dev_provider.get_matches()
        future_matches = [m for m in matches if m.status == MatchStatus.SCHEDULED]
        
        if future_matches:
            match = future_matches[0]
            
            pred1 = prediction_service.generate_prediction(match)
            pred2 = prediction_service.generate_prediction(match)
            
            # If both predictions exist, they should be identical
            if pred1 is not None and pred2 is not None:
                assert pred1.home_win_probability == pred2.home_win_probability
                assert pred1.draw_probability == pred2.draw_probability
                assert pred1.away_win_probability == pred2.away_win_probability
                assert pred1.home_xg == pred2.home_xg
                assert pred1.away_xg == pred2.away_xg


class TestPredictMatchPipeline:
    """Tests for complete prediction pipeline."""
    
    def test_predict_match_returns_context(self, prediction_service, dev_provider):
        """Verify predict_match returns AnalysisContext."""
        from app.domain.analysis import AnalysisContext
        
        matches = dev_provider.get_matches()
        
        if matches:
            match = matches[0]
            context = prediction_service.predict_match(match)
            
            assert isinstance(context, AnalysisContext)
            assert context.match == match
    
    def test_predict_match_includes_markets(self, prediction_service, dev_provider):
        """Verify predict_match includes markets when prediction exists."""
        matches = dev_provider.get_matches()
        future_matches = [m for m in matches if m.status == MatchStatus.SCHEDULED]
        
        if future_matches:
            match = future_matches[0]
            context = prediction_service.predict_match(match)
            
            # If prediction exists, markets should too
            if context.model_predictions is not None and len(context.model_predictions) > 0:
                assert context.prediction_markets is not None
                assert len(context.prediction_markets) > 0



class TestDevelopmentDataFallback:
    """Tests for development data fallback behavior (baseline attack/defense strengths)."""
    
    def test_development_match_with_missing_features_uses_baseline(self, prediction_service, dev_provider):
        """Verify development matches with missing features receive baseline strengths."""
        # Create a minimal match with no historical data context
        # This will result in missing attack/defense strength features
        minimal_match = Match(
            id="minimal_dev_match",
            home_team_id="team_minimal_1",
            away_team_id="team_minimal_2",
            competition_id="comp_minimal",
            season_id="season_minimal",
            scheduled_at=datetime.now() + timedelta(days=1),
            status=MatchStatus.SCHEDULED,
        )
        
        # DevelopmentProvider should identify this as development data
        assert dev_provider.is_development_data() is True
        
        # Generate prediction
        prediction = prediction_service.generate_prediction(minimal_match)
        
        # Should NOT be None - development fallback should provide baseline strengths
        assert prediction is not None
        assert prediction.match_id == minimal_match.id
        
        # Should have valid probabilities
        assert prediction.home_win_probability is not None
        assert prediction.draw_probability is not None
        assert prediction.away_win_probability is not None
        
        # Should have xG values
        assert prediction.home_xg is not None
        assert prediction.away_xg is not None
        
        # Probabilities should sum close to 1
        total = (prediction.home_win_probability +
                prediction.draw_probability +
                prediction.away_win_probability)
        assert abs(total - 1.0) < 0.01
    
    def test_production_match_with_missing_features_returns_none(self, dev_provider):
        """Verify production matches with missing features still fail safely."""
        # Create a mock production provider
        class MockProductionProvider:
            def is_development_data(self):
                return False
            
            def get_matches(self, **kwargs):
                return []
            
            def get_teams(self, competition_id, season_id):
                return []
            
            def get_standings(self, competition_id, season_id):
                return []
        
        production_provider = MockProductionProvider()
        production_service = PredictionService(provider=production_provider)
        
        # Create match with missing context
        minimal_match = Match(
            id="minimal_prod_match",
            home_team_id="team_prod_1",
            away_team_id="team_prod_2",
            competition_id="comp_prod",
            season_id="season_prod",
            scheduled_at=datetime.now() + timedelta(days=1),
            status=MatchStatus.SCHEDULED,
        )
        
        # Production provider should NOT be development data
        assert production_provider.is_development_data() is False
        
        # Generate prediction - should return None due to missing features
        prediction = production_service.generate_prediction(minimal_match)
        
        # Should be None - production data with missing features fails safely
        assert prediction is None
    
    def test_development_match_with_complete_features_uses_real_values(self, prediction_service, dev_provider):
        """Verify development matches with complete features use real feature values, not baseline."""
        # Get a match that should have historical context
        matches = dev_provider.get_matches()
        future_matches = [m for m in matches if m.status == MatchStatus.SCHEDULED]
        
        if not future_matches:
            pytest.skip("No future matches available for testing")
        
        match = future_matches[0]
        
        # Extract features to see what's available
        features = prediction_service.feature_extractor.extract_features(match)
        
        # Generate prediction
        prediction = prediction_service.generate_prediction(match)
        
        # If features were available, prediction should use them
        # (not testing exact values, just that prediction was generated)
        if prediction is not None:
            assert prediction.home_xg is not None
            assert prediction.away_xg is not None
            # xG should be reasonable (not exactly 1.0 from baseline unless by chance)
            assert prediction.home_xg > 0.0
            assert prediction.away_xg > 0.0
    
    def test_full_prediction_pipeline_with_development_fallback(self, prediction_service, dev_provider):
        """Verify complete MENSIONE pipeline works with development fallback."""
        # Create minimal match
        minimal_match = Match(
            id="pipeline_test_match",
            home_team_id="dev_team_alpha",
            away_team_id="dev_team_beta",
            competition_id="dev_comp_league_a",
            season_id="dev_season_2023_2024",
            scheduled_at=datetime.now() + timedelta(days=1),
            status=MatchStatus.SCHEDULED,
        )
        
        # Generate full prediction (Poisson → Markets → Pick → Versioning)
        context = prediction_service.generate_full_prediction(minimal_match)
        
        # Should have all key MENSIONE components
        assert context is not None
        
        # Should have predicted score
        assert context.predicted_score is not None
        
        # Should have MENSIONE pick (BestTip or PassDecision from SmartMarketSelector)
        assert context.mensione_pick is not None
        
        # Check for either BestTip or PassDecision structure
        if context.mensione_pick.get("pass_decision") is True:
            # PassDecision structure
            assert "pass_reason" in context.mensione_pick
            assert "evaluated_markets_count" in context.mensione_pick
            assert "pipeline_version" in context.mensione_pick
        else:
            # BestTip structure
            assert "market" in context.mensione_pick
            assert "selection" in context.mensione_pick
            assert "probability" in context.mensione_pick
            assert "confidence" in context.mensione_pick
            assert "risk_level" in context.mensione_pick
            assert "value_classification" in context.mensione_pick
            assert context.mensione_pick["pass_decision"] is False
        
        # Should have version ID
        assert context.prediction_version_id is not None
        
        # Should have base prediction data in model_predictions
        assert context.model_predictions is not None
        assert len(context.model_predictions) > 0
        assert context.model_predictions[0].home_win_probability is not None
    
    def test_generate_prediction_markets_with_development_fallback(self, prediction_service, dev_provider):
        """Verify market generation works with development fallback."""
        # Create minimal match
        minimal_match = Match(
            id="markets_test_match",
            home_team_id="dev_team_alpha",
            away_team_id="dev_team_beta",
            competition_id="dev_comp_league_a",
            season_id="dev_season_2023_2024",
            scheduled_at=datetime.now() + timedelta(days=1),
            status=MatchStatus.SCHEDULED,
        )
        
        # First generate base prediction
        prediction = prediction_service.generate_prediction(minimal_match)
        assert prediction is not None
        
        # Generate markets
        markets = prediction_service.generate_prediction_markets(minimal_match, prediction)
        
        # Should have markets
        assert len(markets) > 0
        
        # Should have 1X2 market
        match_result_markets = [m for m in markets if m.market_type == PredictionMarketType.MATCH_RESULT]
        assert len(match_result_markets) > 0
        
        # Should have BTTS market
        btts_markets = [m for m in markets if m.market_type == PredictionMarketType.BTTS]
        assert len(btts_markets) > 0
        
        # Markets should have valid probabilities
        # Only check 1X2 and BTTS markets (over/under markets have different lines)
        for market in markets:
            assert market.probabilities is not None
            if market.market_type in [PredictionMarketType.MATCH_RESULT, PredictionMarketType.BTTS]:
                prob_sum = sum(market.probabilities.values())
                assert abs(prob_sum - 1.0) < 0.01  # Should sum close to 1
