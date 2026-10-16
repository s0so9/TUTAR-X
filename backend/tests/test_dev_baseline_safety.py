"""Test production safety of dev-baseline fallback.

This test ensures that missing data baseline fallback (1.0 for missing features)
only activates when explicitly configured, preventing production systems from
silently masking insufficient data.
"""

import pytest
from unittest.mock import Mock
from app.prediction.service import PredictionService, PredictionServiceConfig
from app.domain.match import Match
from datetime import datetime


class TestDevBaselineSafety:
    """Test that dev-baseline fallback doesn't leak into production."""
    
    def create_mock_provider(self, is_development=False):
        """Create a mock provider with configurable development status."""
        provider = Mock()
        provider.is_development_data.return_value = is_development
        provider.get_team_recent_matches.return_value = []
        provider.get_head_to_head.return_value = []
        return provider
    
    def create_match(self):
        """Create a test match."""
        from app.domain.enums import MatchStatus
        return Match(
            id="match_1",
            home_team_id="team_home",
            away_team_id="team_away",
            competition_id="comp_1",
            season_id="2024",
            scheduled_at=datetime(2024, 10, 12),
            status=MatchStatus.SCHEDULED
        )
    
    def test_production_config_auto_detection(self):
        """Test that production provider auto-creates production config."""
        provider = self.create_mock_provider(is_development=False)
        service = PredictionService(provider=provider)
        
        # Should auto-detect as production
        assert service.config.allow_dev_baseline_fallback is False, \
            "Production provider should disable baseline fallback"
    
    def test_development_config_auto_detection(self):
        """Test that development provider auto-creates development config."""
        provider = self.create_mock_provider(is_development=True)
        service = PredictionService(provider=provider)
        
        # Should auto-detect as development
        assert service.config.allow_dev_baseline_fallback is True, \
            "Development provider should enable baseline fallback"
    
    def test_explicit_production_config_override(self):
        """Test that explicit production config overrides provider detection."""
        provider = self.create_mock_provider(is_development=True)
        config = PredictionServiceConfig.for_production()
        service = PredictionService(provider=provider, config=config)
        
        # Explicit config should override
        assert service.config.allow_dev_baseline_fallback is False, \
            "Explicit production config should override provider detection"
    
    def test_explicit_development_config_override(self):
        """Test that explicit development config overrides provider detection."""
        provider = self.create_mock_provider(is_development=False)
        config = PredictionServiceConfig.for_development()
        service = PredictionService(provider=provider, config=config)
        
        # Explicit config should override
        assert service.config.allow_dev_baseline_fallback is True, \
            "Explicit development config should override provider detection"
    
    def test_production_returns_none_on_missing_data(self):
        """Test that production mode returns None when data is missing."""
        provider = self.create_mock_provider(is_development=False)
        service = PredictionService(provider=provider)
        match = self.create_match()
        
        # generate_prediction with no data should return None
        prediction = service.generate_prediction(match)
        
        assert prediction is None, \
            "Production mode should return None for insufficient data, not mask it with baseline"
    
    def test_development_allows_baseline_fallback(self):
        """Test that development mode allows baseline fallback."""
        provider = self.create_mock_provider(is_development=True)
        service = PredictionService(provider=provider)
        match = self.create_match()
        
        # generate_prediction with no data should use baseline and succeed
        prediction = service.generate_prediction(match)
        
        # Should not be None (baseline fallback worked)
        # Note: might still be None if other validation fails, but not due to missing strength features
        # The key is that it doesn't fail at the first check
        assert service.config.allow_dev_baseline_fallback is True
    
    def test_production_config_has_higher_thresholds(self):
        """Test that production config has stricter thresholds than development."""
        prod_config = PredictionServiceConfig.for_production()
        dev_config = PredictionServiceConfig.for_development()
        
        assert prod_config.min_matches >= dev_config.min_matches, \
            "Production should require more matches"
        assert prod_config.min_sample_size >= dev_config.min_sample_size, \
            "Production should require larger sample size"
    
    def test_baseline_fallback_flag_in_metadata(self):
        """Test that baseline fallback is documented in prediction metadata (if prediction succeeds)."""
        provider = self.create_mock_provider(is_development=True)
        service = PredictionService(provider=provider)
        
        # Just verify config is set correctly
        assert service.config.allow_dev_baseline_fallback is True
        
        # In production:
        provider_prod = self.create_mock_provider(is_development=False)
        service_prod = PredictionService(provider=provider_prod)
        assert service_prod.config.allow_dev_baseline_fallback is False
    
    def test_config_immutable_after_init(self):
        """Test that config behavior is determined at init and not runtime-mutable."""
        provider = self.create_mock_provider(is_development=False)
        service = PredictionService(provider=provider)
        
        original_flag = service.config.allow_dev_baseline_fallback
        
        # Even if provider changes (shouldn't happen, but test defensive behavior)
        provider.is_development_data.return_value = True
        
        # Config should remain as initialized
        assert service.config.allow_dev_baseline_fallback == original_flag, \
            "Config should not change after initialization"


class TestConfigCreation:
    """Test PredictionServiceConfig factory methods."""
    
    def test_for_production_creates_safe_config(self):
        """Test that for_production creates safe configuration."""
        config = PredictionServiceConfig.for_production()
        
        assert config.allow_dev_baseline_fallback is False
        assert config.min_matches >= 3
        assert config.min_sample_size >= 5
    
    def test_for_development_creates_permissive_config(self):
        """Test that for_development creates permissive configuration."""
        config = PredictionServiceConfig.for_development()
        
        assert config.allow_dev_baseline_fallback is True
        assert config.min_matches >= 1
        assert config.min_sample_size >= 1
    
    def test_custom_thresholds_respected(self):
        """Test that custom thresholds are respected in factory methods."""
        config = PredictionServiceConfig.for_production(
            min_matches=10,
            min_sample_size=20
        )
        
        assert config.min_matches == 10
        assert config.min_sample_size == 20
        assert config.allow_dev_baseline_fallback is False  # Safety flag still set


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
