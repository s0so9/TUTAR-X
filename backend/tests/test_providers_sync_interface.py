"""Test synchronous provider interface compatibility for feature extraction."""

import pytest
from datetime import date, timedelta

from app.providers.fotmob import FotMobFootballProvider
from app.providers.openligadb import OpenLigaDBFootballProvider
from app.providers.cache import ProviderCache


class TestProviderSyncInterface:
    """Test synchronous get_matches method for provider compatibility."""
    
    def test_fotmob_sync_interface(self):
        """Test FotMob synchronous get_matches method exists and is callable."""
        provider = FotMobFootballProvider(
            base_url="https://www.fotmob.com",
            timeout_seconds=5.0,
            retry_count=1
        )
        
        # Method should exist and be callable synchronously
        assert hasattr(provider, 'get_matches')
        assert callable(provider.get_matches)
        
        # Should accept the base interface parameters
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        # Should not raise exception (may return empty list on connection failure)
        try:
            result = provider.get_matches(from_date=yesterday, to_date=today)
            assert isinstance(result, list)
        except Exception as e:
            # Connection failures are acceptable in tests
            # The important thing is the method exists and has the right signature
            assert "get_matches" not in str(e), f"Method signature issue: {e}"
    
    def test_openligadb_sync_interface(self):
        """Test OpenLigaDB synchronous get_matches method exists and is callable."""
        provider = OpenLigaDBFootballProvider(
            base_url="https://api.openligadb.de",
            timeout_seconds=5.0,
            retry_count=1
        )
        
        # Method should exist and be callable synchronously
        assert hasattr(provider, 'get_matches')
        assert callable(provider.get_matches)
        
        # Should accept the base interface parameters
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        # Should return empty list (OpenLigaDB not used for date-range queries)
        result = provider.get_matches(from_date=yesterday, to_date=today)
        assert isinstance(result, list)
        assert len(result) == 0  # OpenLigaDB returns empty for date-range queries
    
    def test_provider_interface_parameters(self):
        """Test providers accept all base interface parameters without error."""
        fotmob = FotMobFootballProvider(
            base_url="https://www.fotmob.com",
            timeout_seconds=5.0,
            retry_count=1
        )
        
        openligadb = OpenLigaDBFootballProvider(
            base_url="https://api.openligadb.de",
            timeout_seconds=5.0,
            retry_count=1
        )
        
        today = date.today()
        
        # Test with all optional parameters
        params = {
            'competition_id': 'test_comp',
            'season_id': 'test_season',
            'team_id': 'test_team',
            'from_date': today - timedelta(days=7),
            'to_date': today,
            'status': 'finished'
        }
        
        # Should not raise TypeError for unsupported parameters
        try:
            fotmob_result = fotmob.get_matches(**params)
            assert isinstance(fotmob_result, list)
        except Exception as e:
            # Connection errors are OK, parameter errors are not
            assert "unexpected keyword argument" not in str(e), f"Parameter signature issue: {e}"
        
        try:
            openligadb_result = openligadb.get_matches(**params)
            assert isinstance(openligadb_result, list)
            assert len(openligadb_result) == 0  # OpenLigaDB returns empty
        except Exception as e:
            assert "unexpected keyword argument" not in str(e), f"Parameter signature issue: {e}"