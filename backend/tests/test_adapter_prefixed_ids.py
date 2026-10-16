"""Tests for ProviderManagerAdapter prefixed match ID routing.

These tests verify that the adapter correctly handles match IDs in the format
"{provider}_{source_id}" by routing them directly to the specific provider.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from app.providers.adapter import ProviderManagerAdapter
from app.providers.manager import ProviderManager
from app.providers.models import ProviderMatch
from app.domain.match import MatchStatus


@pytest.fixture
def mock_provider_match():
    """Create a sample ProviderMatch for testing."""
    return ProviderMatch(
        provider="fotmob",
        source_id="5181855",
        fetched_at=datetime.now(),
        competition_id="47",
        competition_name="Premier League",
        season="2024/2025",
        home_team_id="8456",
        home_team_name="Chelsea",
        away_team_id="8650",
        away_team_name="Nottingham Forest",
        scheduled_at=datetime(2024, 10, 6, 15, 0, 0),
        status=MatchStatus.SCHEDULED,
        home_score=None,
        away_score=None,
        home_score_ht=None,
        away_score_ht=None,
        minute=None,
        added_time=None,
        outcome=None,
        round=7,
        venue_name="Stamford Bridge"
    )


class TestPrefixedMatchIDRouting:
    """Tests for prefixed match ID routing in ProviderManagerAdapter."""
    
    def test_prefixed_fotmob_id_routes_to_fotmob_provider(self, mock_provider_match):
        """Test that fotmob_5181855 routes directly to fotmob provider."""
        # Create mock fotmob provider
        mock_fotmob = Mock()
        mock_fotmob.get_match = AsyncMock(return_value=mock_provider_match)
        
        # Create ProviderManager with mock fotmob
        manager = Mock(spec=ProviderManager)
        manager._providers = {'fotmob': mock_fotmob}
        
        # Create adapter
        adapter = ProviderManagerAdapter(manager)
        
        # Call get_match with prefixed ID
        result = adapter.get_match("fotmob_5181855")
        
        # Verify fotmob provider was called with numeric ID
        mock_fotmob.get_match.assert_called_once()
        call_args = mock_fotmob.get_match.call_args
        assert call_args[0][0] == "5181855"
        
        # Verify result is mapped to domain Match
        assert result is not None
        assert result.id == "fotmob_5181855"
        assert result.home_team_id == "8456"
        assert result.away_team_id == "8650"
    
    def test_prefixed_ryzellx_id_routes_to_ryzellx_provider(self):
        """Test that ryzellx_12345 routes directly to ryzellx provider."""
        # Create mock provider match
        provider_match = ProviderMatch(
            provider="ryzellx",
            source_id="12345",
            fetched_at=datetime.now(),
            competition_id="PL",
            competition_name="Premier League",
            season="2024/2025",
            home_team_id="CHE",
            home_team_name="Chelsea",
            away_team_id="NFO",
            away_team_name="Nottingham Forest",
            scheduled_at=datetime(2024, 10, 6, 15, 0, 0),
            status=MatchStatus.SCHEDULED,
            home_score=None,
            away_score=None,
            home_score_ht=None,
            away_score_ht=None,
            minute=None,
            added_time=None,
            outcome=None,
            round=7
        )
        
        # Create mock ryzellx provider
        mock_ryzellx = Mock()
        mock_ryzellx.get_match = AsyncMock(return_value=provider_match)
        
        # Create ProviderManager with mock ryzellx
        manager = Mock(spec=ProviderManager)
        manager._providers = {'ryzellx': mock_ryzellx}
        
        # Create adapter
        adapter = ProviderManagerAdapter(manager)
        
        # Call get_match with prefixed ID
        result = adapter.get_match("ryzellx_12345")
        
        # Verify ryzellx provider was called with numeric ID
        mock_ryzellx.get_match.assert_called_once()
        call_args = mock_ryzellx.get_match.call_args
        assert call_args[0][0] == "12345"
        
        # Verify result
        assert result is not None
        assert result.id == "ryzellx_12345"
    
    def test_unprefixed_id_falls_back_to_provider_manager(self):
        """Test that unprefixed IDs use ProviderManager routing."""
        # Create mock provider match
        provider_match = ProviderMatch(
            provider="fotmob",
            source_id="12345",
            fetched_at=datetime.now(),
            competition_id="47",
            competition_name="Premier League",
            season="2024/2025",
            home_team_id="8456",
            home_team_name="Chelsea",
            away_team_id="8650",
            away_team_name="Nottingham Forest",
            scheduled_at=datetime(2024, 10, 6, 15, 0, 0),
            status=MatchStatus.SCHEDULED,
            home_score=None,
            away_score=None,
            home_score_ht=None,
            away_score_ht=None,
            minute=None,
            added_time=None,
            outcome=None,
            round=7
        )
        
        # Create mock ProviderManager
        manager = Mock(spec=ProviderManager)
        manager.get_match = AsyncMock(return_value=(
            provider_match,
            {'selected_provider': 'fotmob', 'attempted_providers': ['sofascore', 'ryzellx', 'fotmob']}
        ))
        manager._providers = {}
        
        # Create adapter
        adapter = ProviderManagerAdapter(manager)
        
        # Call get_match with unprefixed ID
        result = adapter.get_match("12345")
        
        # Verify ProviderManager.get_match was called
        manager.get_match.assert_called_once_with("12345")
        
        # Verify result
        assert result is not None
    
    def test_invalid_provider_prefix_falls_back_to_manager(self):
        """Test that invalid provider prefix falls back to ProviderManager."""
        # Create mock provider match
        provider_match = ProviderMatch(
            provider="fotmob",
            source_id="12345",
            fetched_at=datetime.now(),
            competition_id="47",
            competition_name="Premier League",
            season="2024/2025",
            home_team_id="8456",
            home_team_name="Chelsea",
            away_team_id="8650",
            away_team_name="Nottingham Forest",
            scheduled_at=datetime(2024, 10, 6, 15, 0, 0),
            status=MatchStatus.SCHEDULED,
            home_score=None,
            away_score=None,
            home_score_ht=None,
            away_score_ht=None,
            minute=None,
            added_time=None,
            outcome=None,
            round=7
        )
        
        # Create mock ProviderManager
        manager = Mock(spec=ProviderManager)
        manager.get_match = AsyncMock(return_value=(
            provider_match,
            {'selected_provider': 'fotmob', 'attempted_providers': ['sofascore', 'ryzellx', 'fotmob']}
        ))
        manager._providers = {}
        
        # Create adapter
        adapter = ProviderManagerAdapter(manager)
        
        # Call get_match with invalid provider prefix
        result = adapter.get_match("invalid_12345")
        
        # Verify ProviderManager.get_match was called (fallback)
        manager.get_match.assert_called_once_with("invalid_12345")
        
        # Verify result
        assert result is not None
    
    def test_provider_not_available_falls_back_to_manager(self):
        """Test that unavailable provider falls back to ProviderManager."""
        # Create mock provider match
        provider_match = ProviderMatch(
            provider="ryzellx",
            source_id="12345",
            fetched_at=datetime.now(),
            competition_id="PL",
            competition_name="Premier League",
            season="2024/2025",
            home_team_id="CHE",
            home_team_name="Chelsea",
            away_team_id="NFO",
            away_team_name="Nottingham Forest",
            scheduled_at=datetime(2024, 10, 6, 15, 0, 0),
            status=MatchStatus.SCHEDULED,
            home_score=None,
            away_score=None,
            home_score_ht=None,
            away_score_ht=None,
            minute=None,
            added_time=None,
            outcome=None,
            round=7
        )
        
        # Create mock ProviderManager without fotmob
        manager = Mock(spec=ProviderManager)
        manager.get_match = AsyncMock(return_value=(
            provider_match,
            {'selected_provider': 'ryzellx', 'attempted_providers': ['ryzellx']}
        ))
        manager._providers = {'ryzellx': Mock()}  # No fotmob provider
        
        # Create adapter
        adapter = ProviderManagerAdapter(manager)
        
        # Call get_match with fotmob prefix but provider not available
        result = adapter.get_match("fotmob_12345")
        
        # Verify ProviderManager.get_match was called (fallback)
        manager.get_match.assert_called_once_with("fotmob_12345")
        
        # Verify result
        assert result is not None
    
    def test_provider_returns_none(self):
        """Test that None from provider returns None from adapter."""
        # Create mock fotmob provider that returns None
        mock_fotmob = Mock()
        mock_fotmob.get_match = AsyncMock(return_value=None)
        
        # Create ProviderManager
        manager = Mock(spec=ProviderManager)
        manager._providers = {'fotmob': mock_fotmob}
        
        # Create adapter
        adapter = ProviderManagerAdapter(manager)
        
        # Call get_match
        result = adapter.get_match("fotmob_99999")
        
        # Verify result is None
        assert result is None
    
    def test_metadata_set_for_direct_provider_call(self, mock_provider_match):
        """Test that metadata is correctly set for direct provider calls."""
        # Create mock fotmob provider
        mock_fotmob = Mock()
        mock_fotmob.get_match = AsyncMock(return_value=mock_provider_match)
        
        # Create ProviderManager
        manager = Mock(spec=ProviderManager)
        manager._providers = {'fotmob': mock_fotmob}
        
        # Create adapter
        adapter = ProviderManagerAdapter(manager)
        
        # Call get_match
        result = adapter.get_match("fotmob_5181855")
        
        # Verify metadata
        assert result is not None
        assert adapter.get_provider_name() == "fotmob"
        assert adapter._last_metadata['routing_type'] == 'direct_prefixed_id'
        assert adapter._last_metadata['attempted_providers'] == ['fotmob']
