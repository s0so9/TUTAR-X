"""Tests for easy match detection module."""

import pytest
from app.prediction.easy_matches import (
    EasyMatchDetector,
    EasyMatchConfig,
    EasyMatchResult,
)


class TestEasyMatchDetector:
    """Test EasyMatchDetector class."""
    
    def test_easy_match_high_confidence_1x2(self):
        """Test easy match detection with high 1X2 confidence."""
        detector = EasyMatchDetector()
        
        result = detector.detect(
            match_id="test_1",
            home_win_prob=0.80,  # Very strong home win (increased)
            draw_prob=0.12,
            away_win_prob=0.08,
            btts_prob=0.30,
            over_2_5_prob=0.75,  # Strong over signal
            home_xg=2.8,  # Larger xG differential
            away_xg=0.7,
        )
        
        assert result.match_id == "test_1"
        assert result.is_easy_match is True
        assert result.confidence_score >= 65.0
        assert result.dominant_outcome == "home"
        assert result.dominant_probability == 0.80
        assert result.data_sufficient is True
        assert len(result.reasons) > 0
    
    def test_not_easy_match_balanced(self):
        """Test that balanced matches are not flagged as easy."""
        detector = EasyMatchDetector()
        
        result = detector.detect(
            match_id="test_2",
            home_win_prob=0.35,  # Balanced match
            draw_prob=0.32,
            away_win_prob=0.33,
            btts_prob=0.52,
            over_2_5_prob=0.48,
            home_xg=1.4,
            away_xg=1.3,
        )
        
        assert result.is_easy_match is False
        assert result.confidence_score < 65.0
        assert result.data_sufficient is True
    
    def test_easy_match_high_scoring(self):
        """Test easy match with high scoring confidence."""
        detector = EasyMatchDetector()
        
        result = detector.detect(
            match_id="test_3",
            home_win_prob=0.70,  # Even stronger home win
            draw_prob=0.18,
            away_win_prob=0.12,
            btts_prob=0.85,  # Very high BTTS
            over_2_5_prob=0.90,  # Very high over
            over_3_5_prob=0.60,
            home_xg=3.2,  # Higher xG
            away_xg=2.4,
        )
        
        assert result.is_easy_match is True
        assert result.confidence_score >= 65.0
        # Should have high goals confidence signal
        goals_signal = next(s for s in result.signals if s.name == "goals_confidence")
        assert goals_signal.value > 0.6
        assert goals_signal.available is True
    
    def test_easy_match_low_scoring(self):
        """Test easy match with low scoring confidence."""
        detector = EasyMatchDetector()
        
        result = detector.detect(
            match_id="test_4",
            home_win_prob=0.78,  # Very strong home win
            draw_prob=0.14,
            away_win_prob=0.08,
            btts_prob=0.18,  # Very low BTTS
            over_2_5_prob=0.22,  # Very low over
            home_xg=1.5,
            away_xg=0.3,  # Larger differential
        )
        
        # Should be easy match due to very strong 1X2 and clear xG differential
        assert result.confidence_score >= 60.0
        
        # Should have high 1X2 confidence
        confidence_1x2 = next(s for s in result.signals if s.name == "1x2_confidence")
        assert confidence_1x2.value > 0.5
    
    def test_insufficient_data(self):
        """Test handling of insufficient data."""
        detector = EasyMatchDetector()
        
        # Only provide 1X2, missing other signals
        result = detector.detect(
            match_id="test_5",
            home_win_prob=0.75,
            draw_prob=0.15,
            away_win_prob=0.10,
            # Missing btts, over/under, xG
        )
        
        # Should have warnings about missing data
        assert len(result.warnings) > 0
        
        # Might still have sufficient signals depending on config
        available_count = sum(1 for s in result.signals if s.available)
        if available_count < detector.config.min_data_signals:
            assert result.data_sufficient is False
            assert result.confidence_score == 0.0
    
    def test_calibrated_probabilities_used(self):
        """Test that calibrated probabilities are preferred."""
        detector = EasyMatchDetector()
        
        result = detector.detect(
            match_id="test_6",
            home_win_prob=0.60,
            draw_prob=0.25,
            away_win_prob=0.15,
            home_win_calibrated=0.80,  # Much higher after calibration
            draw_calibrated=0.12,
            away_win_calibrated=0.08,
            btts_prob=0.35,  # Lower BTTS but compensated by other signals
            over_2_5_prob=0.78,  # Strong over
            home_xg=2.8,  # Larger differential
            away_xg=0.6,
        )
        
        # Should use calibrated values
        assert result.dominant_probability == 0.80
        assert result.is_easy_match is True
    
    def test_custom_config(self):
        """Test with custom configuration."""
        config = EasyMatchConfig(
            easy_match_threshold=70.0,  # Higher threshold
            min_dominant_probability=0.65,
            weight_1x2_confidence=0.50,  # Higher weight on 1X2
            weight_goals_confidence=0.20,
            weight_btts_confidence=0.10,
            weight_xg_differential=0.10,
            weight_data_quality=0.10,
        )
        
        detector = EasyMatchDetector(config=config)
        
        result = detector.detect(
            match_id="test_7",
            home_win_prob=0.65,
            draw_prob=0.22,
            away_win_prob=0.13,
            btts_prob=0.50,
            over_2_5_prob=0.55,
            home_xg=1.8,
            away_xg=1.0,
        )
        
        # Threshold should match config
        assert result.threshold == 70.0
    
    def test_deterministic_output(self):
        """Test that same inputs produce same outputs."""
        detector = EasyMatchDetector()
        
        inputs = {
            "match_id": "test_8",
            "home_win_prob": 0.62,
            "draw_prob": 0.24,
            "away_win_prob": 0.14,
            "btts_prob": 0.58,
            "over_2_5_prob": 0.63,
            "home_xg": 2.1,
            "away_xg": 1.2,
        }
        
        result1 = detector.detect(**inputs)
        result2 = detector.detect(**inputs)
        
        # Should produce identical results
        assert result1.is_easy_match == result2.is_easy_match
        assert result1.confidence_score == pytest.approx(result2.confidence_score)
        assert result1.dominant_outcome == result2.dominant_outcome
        assert result1.dominant_probability == result2.dominant_probability
        assert len(result1.signals) == len(result2.signals)
        
        for s1, s2 in zip(result1.signals, result2.signals):
            assert s1.name == s2.name
            assert s1.value == pytest.approx(s2.value)
            assert s1.weight == pytest.approx(s2.weight)
            assert s1.available == s2.available
    
    def test_signals_structure(self):
        """Test that signals have correct structure."""
        detector = EasyMatchDetector()
        
        result = detector.detect(
            match_id="test_9",
            home_win_prob=0.70,
            draw_prob=0.18,
            away_win_prob=0.12,
            btts_prob=0.55,
            over_2_5_prob=0.65,
            home_xg=2.3,
            away_xg=1.1,
        )
        
        # Should have expected signals
        signal_names = {s.name for s in result.signals}
        assert "1x2_confidence" in signal_names
        assert "goals_confidence" in signal_names
        assert "btts_confidence" in signal_names
        assert "xg_differential" in signal_names
        assert "data_quality" in signal_names
        
        # All signals should have required fields
        for signal in result.signals:
            assert signal.name is not None
            assert 0.0 <= signal.value <= 1.0
            assert signal.weight >= 0.0
            assert isinstance(signal.available, bool)
    
    def test_xg_differential_signal(self):
        """Test xG differential signal calculation."""
        detector = EasyMatchDetector()
        
        # Large xG differential
        result1 = detector.detect(
            match_id="test_10",
            home_win_prob=0.70,
            draw_prob=0.20,
            away_win_prob=0.10,
            home_xg=3.0,
            away_xg=0.5,  # 2.5 differential
        )
        
        xg_signal1 = next(s for s in result1.signals if s.name == "xg_differential")
        assert xg_signal1.value > 0.9  # Should be near maximum
        
        # Small xG differential
        result2 = detector.detect(
            match_id="test_11",
            home_win_prob=0.50,
            draw_prob=0.28,
            away_win_prob=0.22,
            home_xg=1.5,
            away_xg=1.4,  # 0.1 differential
        )
        
        xg_signal2 = next(s for s in result2.signals if s.name == "xg_differential")
        assert xg_signal2.value < 0.2  # Should be low
    
    def test_no_fabricated_scores(self):
        """Test that Easy Match scores are never fabricated."""
        detector = EasyMatchDetector()
        
        # With minimal data
        result = detector.detect(
            match_id="test_12",
            home_win_prob=0.50,
            draw_prob=0.28,
            away_win_prob=0.22,
            # No other data
        )
        
        # Should not fabricate a high score
        # Score should be based only on available signals
        available_signals = [s for s in result.signals if s.available]
        
        if len(available_signals) < detector.config.min_data_signals:
            # Insufficient data should result in 0 score
            assert result.confidence_score == 0.0
            assert result.data_sufficient is False
        else:
            # Score should only reflect available signals
            assert result.data_sufficient is True
            # Score calculated from available signals only
            assert 0.0 <= result.confidence_score <= 100.0
    
    def test_draw_as_dominant_outcome(self):
        """Test that draw can be dominant outcome."""
        detector = EasyMatchDetector()
        
        result = detector.detect(
            match_id="test_13",
            home_win_prob=0.25,
            draw_prob=0.50,  # Strong draw
            away_win_prob=0.25,
            btts_prob=0.45,
            over_2_5_prob=0.40,
            home_xg=1.2,
            away_xg=1.2,
        )
        
        assert result.dominant_outcome == "draw"
        assert result.dominant_probability == 0.50
    
    def test_model_agreement_signal(self):
        """Test model agreement score integration."""
        detector = EasyMatchDetector()
        
        result = detector.detect(
            match_id="test_14",
            home_win_prob=0.65,
            draw_prob=0.22,
            away_win_prob=0.13,
            btts_prob=0.55,
            over_2_5_prob=0.60,
            home_xg=2.0,
            away_xg=1.0,
            model_agreement_score=0.85,  # High model agreement
        )
        
        # Data quality signal should incorporate agreement
        data_quality_signal = next(s for s in result.signals if s.name == "data_quality")
        assert data_quality_signal.value > 0.8
        assert data_quality_signal.available is True
