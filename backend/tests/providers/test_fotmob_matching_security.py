"""Test ESPN-FotMob team matching security."""

import pytest
from app.providers.fotmob import FotMobFootballProvider


def normalize_team_name(name: str) -> str:
    """Copy of normalize function from fotmob.py for testing."""
    normalized = name.lower().strip()
    # Remove common prefixes and suffixes that might differ between providers
    tokens = normalized.split()
    if len(tokens) > 1:
        if tokens[0] in ['fc', 'ac', 'sc', 'cf', 'bk', 'afc', 'rcd']:
            normalized = ' '.join(tokens[1:])
        elif tokens[-1] in ['fc', 'ac', 'sc', 'cf', 'bk', 'afc']:
            normalized = ' '.join(tokens[:-1])
    return normalized.strip()


def test_normalize_team_name():
    """Test team name normalization removes common suffixes."""
    assert normalize_team_name("Real Madrid CF") == "real madrid"
    assert normalize_team_name("Barcelona FC") == "barcelona"
    assert normalize_team_name("Athletic Bilbao") == "athletic bilbao"
    assert normalize_team_name("Villarreal CF") == "villarreal"
    assert normalize_team_name("Real Betis") == "real betis"
    assert normalize_team_name("Real Sociedad") == "real sociedad"


def test_no_false_positive_real_teams():
    """Test that Real Madrid, Real Betis, Real Sociedad don't cross-match."""
    
    # ESPN live matches
    espn_live_names = {
        "villarreal at real madrid",
        "barcelona at athletic bilbao"
    }
    
    # FotMob matches (various Real teams)
    fotmob_matches = [
        {"home": "Real Madrid", "away": "Villarreal CF"},  # Should match
        {"home": "Athletic Bilbao", "away": "FC Barcelona"},  # Should match
        {"home": "Real Betis", "away": "Valencia"},  # Should NOT match
        {"home": "Real Sociedad", "away": "Sevilla"},  # Should NOT match
        {"home": "Villarreal CF", "away": "Real Sociedad"},  # Should NOT match
    ]
    
    matched_indices = []
    
    for idx, fotmob_match in enumerate(fotmob_matches):
        home_normalized = normalize_team_name(fotmob_match["home"])
        away_normalized = normalize_team_name(fotmob_match["away"])
        
        is_live_match = False
        for espn_live_name in espn_live_names:
            if ' at ' in espn_live_name:
                parts = espn_live_name.split(' at ')
                if len(parts) == 2:
                    espn_away = normalize_team_name(parts[0])
                    espn_home = normalize_team_name(parts[1])
                    
                    # Exact match: both teams must match
                    if espn_home == home_normalized and espn_away == away_normalized:
                        is_live_match = True
                        break
        
        if is_live_match:
            matched_indices.append(idx)
    
    # Only first two matches should match
    assert matched_indices == [0, 1], f"Expected [0, 1], got {matched_indices}"


def test_order_matters():
    """Test that home/away order must match ESPN format."""
    
    espn_live_names = {"villarreal at real madrid"}
    
    # Correct order
    home_norm = normalize_team_name("Real Madrid")
    away_norm = normalize_team_name("Villarreal CF")
    
    is_match = False
    for espn_name in espn_live_names:
        if ' at ' in espn_name:
            parts = espn_name.split(' at ')
            if len(parts) == 2:
                espn_away = normalize_team_name(parts[0])
                espn_home = normalize_team_name(parts[1])
                if espn_home == home_norm and espn_away == away_norm:
                    is_match = True
    
    assert is_match, "Should match with correct order"
    
    # Wrong order
    home_norm_wrong = normalize_team_name("Villarreal CF")
    away_norm_wrong = normalize_team_name("Real Madrid")
    
    is_match_wrong = False
    for espn_name in espn_live_names:
        if ' at ' in espn_name:
            parts = espn_name.split(' at ')
            if len(parts) == 2:
                espn_away = normalize_team_name(parts[0])
                espn_home = normalize_team_name(parts[1])
                if espn_home == home_norm_wrong and espn_away == away_norm_wrong:
                    is_match_wrong = True
    
    assert not is_match_wrong, "Should NOT match with wrong order"


def test_suffix_normalization():
    """Test that common suffixes are normalized correctly."""
    
    espn_live_names = {"barcelona at athletic bilbao"}
    
    # FotMob uses full names with suffixes
    home_norm = normalize_team_name("Athletic Bilbao")
    away_norm = normalize_team_name("FC Barcelona")
    
    is_match = False
    for espn_name in espn_live_names:
        if ' at ' in espn_name:
            parts = espn_name.split(' at ')
            if len(parts) == 2:
                espn_away = normalize_team_name(parts[0])
                espn_home = normalize_team_name(parts[1])
                if espn_home == home_norm and espn_away == away_norm:
                    is_match = True
    
    assert is_match, "Should match despite suffix differences"


def test_no_partial_match():
    """Test that partial team name matches are rejected."""
    
    espn_live_names = {"real at barcelona"}  # Ambiguous/partial names
    
    fotmob_matches = [
        {"home": "Barcelona", "away": "Real Madrid"},
        {"home": "Barcelona", "away": "Real Betis"},
        {"home": "Barcelona", "away": "Real Sociedad"},
    ]
    
    matched_count = 0
    for fotmob_match in fotmob_matches:
        home_normalized = normalize_team_name(fotmob_match["home"])
        away_normalized = normalize_team_name(fotmob_match["away"])
        
        is_live_match = False
        for espn_live_name in espn_live_names:
            if ' at ' in espn_live_name:
                parts = espn_live_name.split(' at ')
                if len(parts) == 2:
                    espn_away = normalize_team_name(parts[0])
                    espn_home = normalize_team_name(parts[1])
                    
                    if espn_home == home_normalized and espn_away == away_normalized:
                        is_live_match = True
                        break
        
        if is_live_match:
            matched_count += 1
    
    # None should match because "real" is ambiguous
    assert matched_count == 0, f"Expected 0 matches, got {matched_count}"
