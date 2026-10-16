"""Tests for odds calculation and team matching logic.

Mock tests that don't require real API calls.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock

from app.providers.odds_api_provider import TheOddsAPIProvider
from app.services.odds_updater_service import OddsUpdaterService
from app.utils.team_name_normalizer import (
    normalize_team_name,
    teams_match,
    calculate_team_similarity,
    get_canonical_name
)


class TestTeamNameNormalization:
    """Test team name normalization and matching."""
    
    def test_normalize_basic(self):
        """Test basic normalization."""
        assert normalize_team_name("Manchester United FC") == "manchester united"
        assert normalize_team_name("Real Madrid CF") == "real madrid"
        assert normalize_team_name("FC Barcelona") == "barcelona"
    
    def test_normalize_turkish_characters(self):
        """Test Turkish character normalization."""
        assert normalize_team_name("Galatasaray SK") == "galatasaray"
        assert normalize_team_name("Fenerbahçe") == "fenerbahce"
        assert normalize_team_name("Beşiktaş JK") == "besiktas"
        assert normalize_team_name("Trabzonspor AŞ") == "trabzonspor"
    
    def test_normalize_removes_suffixes(self):
        """Test suffix removal."""
        assert normalize_team_name("Arsenal FC") == "arsenal"
        assert normalize_team_name("Chelsea Football Club") == "chelsea"
        assert normalize_team_name("Juventus AC") == "juventus"
        assert normalize_team_name("Bayern München") == "bayern munchen"
    
    def test_teams_match_exact(self):
        """Test exact team matching after normalization."""
        assert teams_match("Manchester United FC", "Manchester United")
        assert teams_match("Galatasaray SK", "Galatasaray")
        assert teams_match("FC Barcelona", "Barcelona")
    
    def test_teams_match_variations(self):
        """Test team matching with variations."""
        assert teams_match("Arsenal FC", "Arsenal")
        assert teams_match("Barcelona FC", "FC Barcelona")
        assert teams_match("Fenerbahce", "Fenerbahçe SK")
    
    def test_teams_dont_match_different(self):
        """Test that different teams don't match."""
        assert not teams_match("Arsenal", "Chelsea")
        assert not teams_match("Barcelona", "Real Madrid")
        assert not teams_match("Liverpool", "Everton")
    
    def test_calculate_similarity(self):
        """Test similarity calculation."""
        # High similarity - same team with suffix
        assert calculate_team_similarity("Manchester United", "Manchester United FC") > 0.8
        assert calculate_team_similarity("Real Madrid", "Real Madrid CF") > 0.8
        
        # Medium similarity - partial match
        score = calculate_team_similarity("Arsenal FC", "Arsenal London")
        assert 0.3 < score < 0.7
        
        # Low similarity - different teams
        assert calculate_team_similarity("Arsenal", "Barcelona") < 0.3
    
    def test_canonical_names(self):
        """Test canonical name resolution."""
        assert get_canonical_name("Manchester City FC") == "manchester city"
        assert get_canonical_name("Arsenal FC") == "arsenal"
        assert get_canonical_name("Galatasaray SK") == "galatasaray"


class TestOddsCalculation:
    """Test odds calculation logic."""
    
    def test_calculate_average_simple(self):
        """Test simple average calculation."""
        # Mock provider
        provider = TheOddsAPIProvider()
        
        # Mock event data
        mock_event = {
            'id': 'test_event_1',
            'home_team': 'Arsenal',
            'away_team': 'Chelsea',
            'commence_time': '2026-10-15T15:00:00Z',
            'bookmakers': [
                {
                    'key': 'bet365',
                    'title': 'Bet365',
                    'last_update': '2026-10-10T12:00:00Z',
                    'markets': [
                        {
                            'key': 'h2h',
                            'outcomes': [
                                {'name': 'Arsenal', 'price': 2.10},
                                {'name': 'Draw', 'price': 3.50},
                                {'name': 'Chelsea', 'price': 3.20}
                            ]
                        }
                    ]
                },
                {
                    'key': 'unibet',
                    'title': 'Unibet',
                    'last_update': '2026-10-10T12:00:00Z',
                    'markets': [
                        {
                            'key': 'h2h',
                            'outcomes': [
                                {'name': 'Arsenal', 'price': 2.20},
                                {'name': 'Draw', 'price': 3.40},
                                {'name': 'Chelsea', 'price': 3.10}
                            ]
                        }
                    ]
                }
            ]
        }
        
        # Mock the get_odds method
        with patch.object(provider, 'get_odds', return_value=[mock_event]):
            with patch.object(provider, 'is_available', return_value=True):
                result = provider.calculate_average_odds('Arsenal', 'Chelsea', 'soccer_epl')
        
        assert result is not None
        assert result['match_found'] is True
        assert result['home_win'] is not None
        assert result['home_win']['average_odds'] == 2.15  # (2.10 + 2.20) / 2
        assert result['home_win']['bookmaker_count'] == 2
        assert result['draw']['average_odds'] == 3.45  # (3.50 + 3.40) / 2
        assert result['away_win']['average_odds'] == 3.15  # (3.20 + 3.10) / 2
    
    def test_calculate_average_with_missing_bookmaker(self):
        """Test average when one bookmaker has incomplete data."""
        provider = TheOddsAPIProvider()
        
        mock_event = {
            'id': 'test_event_2',
            'home_team': 'Liverpool',
            'away_team': 'Everton',
            'commence_time': '2026-10-15T15:00:00Z',
            'bookmakers': [
                {
                    'key': 'bet365',
                    'title': 'Bet365',
                    'last_update': '2026-10-10T12:00:00Z',
                    'markets': [
                        {
                            'key': 'h2h',
                            'outcomes': [
                                {'name': 'Liverpool', 'price': 1.50},
                                {'name': 'Draw', 'price': 4.00},
                                {'name': 'Everton', 'price': 6.50}
                            ]
                        }
                    ]
                },
                {
                    'key': 'unibet',
                    'title': 'Unibet',
                    'last_update': '2026-10-10T12:00:00Z',
                    'markets': [
                        {
                            'key': 'h2h',
                            'outcomes': [
                                {'name': 'Liverpool', 'price': 1.55},
                                # Draw missing
                                {'name': 'Everton', 'price': 6.00}
                            ]
                        }
                    ]
                }
            ]
        }
        
        with patch.object(provider, 'get_odds', return_value=[mock_event]):
            with patch.object(provider, 'is_available', return_value=True):
                result = provider.calculate_average_odds('Liverpool', 'Everton', 'soccer_epl')
        
        assert result is not None
        assert result['match_found'] is True
        assert result['home_win']['bookmaker_count'] == 2
        assert result['draw']['bookmaker_count'] == 1  # Only one bookmaker has draw
        assert result['away_win']['bookmaker_count'] == 2
    
    def test_match_not_found(self):
        """Test when match is not found in API response."""
        provider = TheOddsAPIProvider()
        
        mock_events = [
            {
                'id': 'test_event_3',
                'home_team': 'Arsenal',
                'away_team': 'Chelsea',
                'commence_time': '2026-10-15T15:00:00Z',
                'bookmakers': []
            }
        ]
        
        with patch.object(provider, 'get_odds', return_value=mock_events):
            with patch.object(provider, 'is_available', return_value=True):
                result = provider.calculate_average_odds('Liverpool', 'Manchester City', 'soccer_epl')
        
        assert result is not None
        assert result['match_found'] is False
        assert result['home_team'] == 'Liverpool'
        assert result['away_team'] == 'Manchester City'


class TestQuotaControl:
    """Test API quota control logic."""
    
    def test_quota_check_sufficient(self):
        """Test quota check when quota is sufficient."""
        provider = TheOddsAPIProvider()
        
        mock_response = Mock()
        mock_response.headers = {'x-requests-remaining': '150'}
        mock_response.status_code = 200
        mock_response.json.return_value = []
        
        with patch('requests.get', return_value=mock_response):
            with patch.object(provider, 'is_available', return_value=True):
                has_quota, remaining = provider.check_quota()
        
        assert has_quota is True
        assert remaining == 150
    
    def test_quota_check_insufficient(self):
        """Test quota check when quota is too low."""
        provider = TheOddsAPIProvider()
        
        mock_response = Mock()
        mock_response.headers = {'x-requests-remaining': '30'}
        mock_response.status_code = 200
        mock_response.json.return_value = []
        
        with patch('requests.get', return_value=mock_response):
            with patch.object(provider, 'is_available', return_value=True):
                with patch('app.config.settings.the_odds_api_min_remaining_requests', 50):
                    has_quota, remaining = provider.check_quota()
        
        assert has_quota is False
        assert remaining == 30
    
    def test_get_odds_skips_on_low_quota(self):
        """Test that get_odds skips fetch when quota is low."""
        provider = TheOddsAPIProvider()
        
        with patch.object(provider, 'is_available', return_value=True):
            with patch.object(provider, 'check_quota', return_value=(False, 30)):
                with patch.object(provider, '_get_from_cache', return_value=None):
                    result = provider.get_odds('soccer_epl')
        
        assert result is None
    
    def test_get_odds_uses_cache_no_quota_check(self):
        """Test that cached data is returned without quota check."""
        provider = TheOddsAPIProvider()
        
        mock_cached_data = [{'id': 'cached_event'}]
        
        with patch.object(provider, 'is_available', return_value=True):
            with patch.object(provider, '_get_from_cache', return_value=mock_cached_data):
                # check_quota should not be called
                with patch.object(provider, 'check_quota') as mock_check:
                    result = provider.get_odds('soccer_epl')
                    mock_check.assert_not_called()
        
        assert result == mock_cached_data


class TestMatchFinding:
    """Test match finding logic in odds updater service."""
    
    def test_find_match_with_exact_names(self):
        """Test finding match with exact team names."""
        # Mock database session
        mock_db = Mock()
        
        # Mock Match object
        mock_match = Mock()
        mock_match.id = 'match_123'
        mock_match.home_team.name = 'Arsenal'
        mock_match.away_team.name = 'Chelsea'
        mock_match.scheduled_at = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)
        
        # Mock query result
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_match]
        
        service = OddsUpdaterService(mock_db)
        
        commence_time = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)
        match_id = service._find_match_id('Arsenal', 'Chelsea', commence_time)
        
        assert match_id == 'match_123'
    
    def test_find_match_with_variations(self):
        """Test finding match with team name variations."""
        mock_db = Mock()
        
        mock_match = Mock()
        mock_match.id = 'match_456'
        mock_match.home_team.name = 'Manchester United'
        mock_match.away_team.name = 'Liverpool FC'
        mock_match.scheduled_at = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)
        
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_match]
        
        service = OddsUpdaterService(mock_db)
        
        commence_time = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)
        match_id = service._find_match_id('Man United', 'Liverpool', commence_time)
        
        assert match_id == 'match_456'
    
    def test_find_match_no_match_low_similarity(self):
        """Test that no match is returned when similarity is too low."""
        mock_db = Mock()
        
        mock_match = Mock()
        mock_match.id = 'match_789'
        mock_match.home_team.name = 'Arsenal'
        mock_match.away_team.name = 'Chelsea'
        mock_match.scheduled_at = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)
        
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_match]
        
        service = OddsUpdaterService(mock_db)
        
        commence_time = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)
        # Try to match completely different teams
        match_id = service._find_match_id('Barcelona', 'Real Madrid', commence_time)
        
        assert match_id is None
    
    def test_find_match_no_matches_in_time_window(self):
        """Test when no matches exist in time window."""
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        
        service = OddsUpdaterService(mock_db)
        
        commence_time = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)
        match_id = service._find_match_id('Arsenal', 'Chelsea', commence_time)
        
        assert match_id is None


class TestConfigurableSports:
    """Test configurable sports list functionality."""
    
    @patch('app.services.odds_updater_service.get_db')
    @patch('app.services.odds_updater_service.settings')
    def test_update_all_odds_with_configured_sports(self, mock_settings, mock_get_db):
        """Test that update_all_odds uses configured sports."""
        from app.services.odds_updater_service import update_all_odds
        
        mock_settings.the_odds_api_sports = "soccer_epl,soccer_spain_la_liga,soccer_germany_bundesliga"
        
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        
        with patch.object(OddsUpdaterService, 'update_odds_for_sport') as mock_update:
            mock_update.return_value = {
                'success': True,
                'events_processed': 10,
                'odds_created': 50,
                'odds_updated': 20,
                'averages_calculated': 30,
                'errors': []
            }
            
            result = update_all_odds()
        
        # Should be called 3 times (one for each sport)
        assert mock_update.call_count == 3
        assert result['total_events'] == 30  # 10 * 3
    
    @patch('app.services.odds_updater_service.get_db')
    @patch('app.services.odds_updater_service.settings')
    def test_update_all_odds_empty_config(self, mock_settings, mock_get_db):
        """Test handling of empty sports configuration."""
        from app.services.odds_updater_service import update_all_odds
        
        mock_settings.the_odds_api_sports = ""
        
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        
        result = update_all_odds()
        
        assert result['success'] is False
        assert 'No sports configured' in result['error']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
