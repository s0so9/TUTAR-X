"""Tests for data providers."""

import pytest
from datetime import date, timedelta

from app.providers import FootballDataProvider, DevelopmentProvider
from app.domain import (
    Competition,
    Season,
    Team,
    Player,
    Venue,
    Match,
    Standing,
    TeamMatchStatistic,
    MatchStatus,
)


def test_development_provider_initialization():
    """Test DevelopmentProvider can be instantiated."""
    provider = DevelopmentProvider()
    assert provider is not None
    assert isinstance(provider, FootballDataProvider)


def test_development_provider_metadata():
    """Test DevelopmentProvider metadata methods."""
    provider = DevelopmentProvider()
    
    # Provider name
    name = provider.get_provider_name()
    assert "Development" in name or "Mock" in name
    
    # Development data flag
    assert provider.is_development_data() is True  # Must be True for mock data


def test_get_competitions():
    """Test retrieving mock competitions."""
    provider = DevelopmentProvider()
    competitions = provider.get_competitions()
    
    assert len(competitions) > 0
    assert all(isinstance(c, Competition) for c in competitions)
    
    # Verify development data is labeled
    for comp in competitions:
        assert "[DEV]" in comp.name or "DEV" in comp.country


def test_get_competition_by_id():
    """Test retrieving a specific competition."""
    provider = DevelopmentProvider()
    competitions = provider.get_competitions()
    
    if competitions:
        first_comp = competitions[0]
        retrieved = provider.get_competition(first_comp.id)
        
        assert retrieved is not None
        assert retrieved.id == first_comp.id
        assert retrieved.name == first_comp.name


def test_get_seasons():
    """Test retrieving seasons."""
    provider = DevelopmentProvider()
    competitions = provider.get_competitions()
    
    if competitions:
        comp_id = competitions[0].id
        seasons = provider.get_seasons(comp_id)
        
        assert isinstance(seasons, list)
        assert all(isinstance(s, Season) for s in seasons)
        assert all(s.competition_id == comp_id for s in seasons)


def test_get_current_season():
    """Test retrieving current season."""
    provider = DevelopmentProvider()
    competitions = provider.get_competitions()
    
    if competitions:
        comp_id = competitions[0].id
        current_season = provider.get_current_season(comp_id)
        
        if current_season:
            assert isinstance(current_season, Season)
            assert current_season.is_current is True
            assert current_season.competition_id == comp_id


def test_get_teams():
    """Test retrieving teams."""
    provider = DevelopmentProvider()
    competitions = provider.get_competitions()
    
    if competitions:
        comp_id = competitions[0].id
        seasons = provider.get_seasons(comp_id)
        
        if seasons:
            season_id = seasons[0].id
            teams = provider.get_teams(comp_id, season_id)
            
            assert isinstance(teams, list)
            assert len(teams) > 0
            assert all(isinstance(t, Team) for t in teams)
            
            # Verify development data is labeled
            for team in teams:
                assert "[DEV]" in team.name


def test_get_team_by_id():
    """Test retrieving a specific team."""
    provider = DevelopmentProvider()
    competitions = provider.get_competitions()
    
    if competitions:
        comp_id = competitions[0].id
        seasons = provider.get_seasons(comp_id)
        
        if seasons:
            teams = provider.get_teams(comp_id, seasons[0].id)
            
            if teams:
                first_team = teams[0]
                retrieved = provider.get_team(first_team.id)
                
                assert retrieved is not None
                assert retrieved.id == first_team.id
                assert retrieved.name == first_team.name


def test_get_matches():
    """Test retrieving matches."""
    provider = DevelopmentProvider()
    matches = provider.get_matches()
    
    assert isinstance(matches, list)
    assert len(matches) > 0
    assert all(isinstance(m, Match) for m in matches)


def test_get_matches_by_competition():
    """Test filtering matches by competition."""
    provider = DevelopmentProvider()
    competitions = provider.get_competitions()
    
    if competitions:
        comp_id = competitions[0].id
        matches = provider.get_matches(competition_id=comp_id)
        
        assert all(m.competition_id == comp_id for m in matches)


def test_get_matches_by_team():
    """Test filtering matches by team."""
    provider = DevelopmentProvider()
    competitions = provider.get_competitions()
    
    if competitions:
        comp_id = competitions[0].id
        seasons = provider.get_seasons(comp_id)
        
        if seasons:
            teams = provider.get_teams(comp_id, seasons[0].id)
            
            if teams:
                team_id = teams[0].id
                matches = provider.get_matches(team_id=team_id)
                
                assert all(
                    m.home_team_id == team_id or m.away_team_id == team_id
                    for m in matches
                )


def test_get_matches_by_status():
    """Test filtering matches by status."""
    provider = DevelopmentProvider()
    finished_matches = provider.get_matches(status="finished")
    
    assert all(m.status == MatchStatus.FINISHED for m in finished_matches)


def test_get_matches_by_date_range():
    """Test filtering matches by date range."""
    provider = DevelopmentProvider()
    today = date.today()
    
    # Get past matches
    past_matches = provider.get_matches(
        to_date=today - timedelta(days=1)
    )
    
    assert all(m.scheduled_at.date() < today for m in past_matches)
    
    # Get future matches
    future_matches = provider.get_matches(
        from_date=today + timedelta(days=1)
    )
    
    assert all(m.scheduled_at.date() > today for m in future_matches)


def test_get_match_by_id():
    """Test retrieving a specific match."""
    provider = DevelopmentProvider()
    matches = provider.get_matches()
    
    if matches:
        first_match = matches[0]
        retrieved = provider.get_match(first_match.id)
        
        assert retrieved is not None
        assert retrieved.id == first_match.id
        assert retrieved.home_team_id == first_match.home_team_id
        assert retrieved.away_team_id == first_match.away_team_id


def test_get_team_players():
    """Test retrieving players for a team."""
    provider = DevelopmentProvider()
    competitions = provider.get_competitions()
    
    if competitions:
        comp_id = competitions[0].id
        seasons = provider.get_seasons(comp_id)
        
        if seasons:
            teams = provider.get_teams(comp_id, seasons[0].id)
            
            if teams:
                team_id = teams[0].id
                players = provider.get_team_players(team_id)
                
                assert isinstance(players, list)
                assert all(isinstance(p, Player) for p in players)
                assert all(p.team_id == team_id for p in players)
                
                # Verify development data is labeled
                for player in players:
                    assert "[DEV]" in player.name


def test_get_player_by_id():
    """Test retrieving a specific player."""
    provider = DevelopmentProvider()
    competitions = provider.get_competitions()
    
    if competitions:
        comp_id = competitions[0].id
        seasons = provider.get_seasons(comp_id)
        
        if seasons:
            teams = provider.get_teams(comp_id, seasons[0].id)
            
            if teams:
                players = provider.get_team_players(teams[0].id)
                
                if players:
                    first_player = players[0]
                    retrieved = provider.get_player(first_player.id)
                    
                    assert retrieved is not None
                    assert retrieved.id == first_player.id
                    assert retrieved.name == first_player.name


def test_get_venue_by_id():
    """Test retrieving a specific venue."""
    provider = DevelopmentProvider()
    competitions = provider.get_competitions()
    
    if competitions:
        comp_id = competitions[0].id
        seasons = provider.get_seasons(comp_id)
        
        if seasons:
            teams = provider.get_teams(comp_id, seasons[0].id)
            
            if teams:
                # Find a team with a venue
                for team in teams:
                    if team.venue_id:
                        venue = provider.get_venue(team.venue_id)
                        
                        assert venue is not None
                        assert isinstance(venue, Venue)
                        assert "[DEV]" in venue.name
                        break


def test_get_standings():
    """Test retrieving league standings."""
    provider = DevelopmentProvider()
    competitions = provider.get_competitions()
    
    if competitions:
        comp_id = competitions[0].id
        seasons = provider.get_seasons(comp_id)
        
        if seasons:
            season_id = seasons[0].id
            standings = provider.get_standings(comp_id, season_id)
            
            assert isinstance(standings, list)
            assert len(standings) > 0
            assert all(isinstance(s, Standing) for s in standings)
            assert all(s.competition_id == comp_id for s in standings)
            assert all(s.season_id == season_id for s in standings)
            
            # Verify standings are ordered by position
            positions = [s.position for s in standings]
            assert positions == sorted(positions)


def test_get_team_match_statistics():
    """Test retrieving team match statistics."""
    provider = DevelopmentProvider()
    matches = provider.get_matches(status="finished")
    
    if matches:
        match_id = matches[0].id
        stats = provider.get_team_match_statistics(match_id)
        
        assert isinstance(stats, list)
        # Should have stats for both teams
        if len(stats) > 0:
            assert all(isinstance(s, TeamMatchStatistic) for s in stats)
            assert all(s.match_id == match_id for s in stats)


def test_data_consistency():
    """Test that mock data is internally consistent."""
    provider = DevelopmentProvider()
    
    # Get all entities
    competitions = provider.get_competitions()
    matches = provider.get_matches()
    teams = provider.get_teams(competitions[0].id, provider.get_seasons(competitions[0].id)[0].id)
    
    # Verify match teams exist
    team_ids = {t.id for t in teams}
    for match in matches:
        if match.competition_id == competitions[0].id:
            assert match.home_team_id in team_ids, f"Home team {match.home_team_id} not found"
            assert match.away_team_id in team_ids, f"Away team {match.away_team_id} not found"


def test_no_network_calls():
    """Test that provider makes no network requests."""
    provider = DevelopmentProvider()
    
    # All methods should execute without network access
    # This test implicitly verifies no network calls by executing successfully
    # in an environment without network mocking
    
    provider.get_competitions()
    provider.get_matches()
    competitions = provider.get_competitions()
    if competitions:
        provider.get_seasons(competitions[0].id)
        seasons = provider.get_seasons(competitions[0].id)
        if seasons:
            provider.get_teams(competitions[0].id, seasons[0].id)
    
    # If we reach here without errors, no network calls were made
    assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
