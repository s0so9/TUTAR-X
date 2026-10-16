"""Tests for domain models."""

from datetime import datetime, date
import pytest

from app.domain import (
    # Base
    BaseEntity,
    DataQualityMetadata,
    # Enums
    MatchStatus,
    MatchEventType,
    MatchOutcome,
    PredictionMarketType,
    ModelType,
    InjuryStatus,
    SuspensionType,
    DataSource,
    # Entities
    Competition,
    Season,
    Team,
    Player,
    Venue,
    # Match
    Match,
    MatchEvent,
    Lineup,
    # Statistics
    PlayerMatchStatistic,
    TeamMatchStatistic,
    Standing,
    # Availability
    Injury,
    Suspension,
    # Odds
    Odds,
    # Prediction
    Prediction,
    PredictionMarket,
    Model,
    ModelVersion,
    ModelRun,
    # Backtest
    Backtest,
    BacktestResult,
    # Live
    LiveMatchState,
    FeatureSnapshot,
    # Analysis
    AnalysisContext,
)


def test_competition_model():
    """Test Competition model."""
    comp = Competition(
        id="comp_1",
        name="Premier League",
        country="ENG",
        level=1,
        type="league",
    )
    assert comp.id == "comp_1"
    assert comp.name == "Premier League"
    assert comp.country == "ENG"


def test_team_model():
    """Test Team model."""
    team = Team(
        id="team_1",
        name="Manchester United",
        short_name="Man Utd",
        code="MUN",
        country="ENG",
    )
    assert team.id == "team_1"
    assert team.name == "Manchester United"


def test_match_model():
    """Test Match model."""
    match = Match(
        id="match_1",
        competition_id="comp_1",
        season_id="season_1",
        home_team_id="team_1",
        away_team_id="team_2",
        scheduled_at=datetime(2026, 10, 5, 15, 0),
        status=MatchStatus.SCHEDULED,
        round=7,
    )
    assert match.id == "match_1"
    assert match.status == MatchStatus.SCHEDULED
    assert match.home_team_id == "team_1"


def test_prediction_model():
    """Test Prediction model."""
    prediction = Prediction(
        id="pred_1",
        match_id="match_1",
        model_id="model_1",
        home_win_probability=0.45,
        draw_probability=0.30,
        away_win_probability=0.25,
        home_xg=1.8,
        away_xg=1.3,
        generated_at=datetime.now(),
    )
    assert prediction.home_win_probability == 0.45
    assert prediction.draw_probability == 0.30
    assert prediction.away_win_probability == 0.25
    assert 0.0 <= prediction.home_win_probability <= 1.0


def test_prediction_probability_validation():
    """Test probability validation in Prediction model."""
    # Valid probabilities
    prediction = Prediction(
        id="pred_1",
        match_id="match_1",
        model_id="model_1",
        home_win_probability=0.5,
        draw_probability=0.3,
        away_win_probability=0.2,
        generated_at=datetime.now(),
    )
    assert prediction.home_win_probability == 0.5
    
    # Invalid probability > 1.0
    with pytest.raises(ValueError):
        Prediction(
            id="pred_2",
            match_id="match_1",
            model_id="model_1",
            home_win_probability=1.5,  # Invalid
            generated_at=datetime.now(),
        )


def test_analysis_context_model():
    """Test AnalysisContext model."""
    match = Match(
        id="match_1",
        competition_id="comp_1",
        season_id="season_1",
        home_team_id="team_1",
        away_team_id="team_2",
        scheduled_at=datetime.now(),
    )
    
    home_team = Team(id="team_1", name="Team A")
    away_team = Team(id="team_2", name="Team B")
    competition = Competition(id="comp_1", name="League A")
    
    context = AnalysisContext(
        match=match,
        home_team=home_team,
        away_team=away_team,
        competition=competition,
        home_form_string="WWDLL",
        away_form_string="DWWDL",
        missing_data_notes=["Player xG not available"],
    )
    
    assert context.match.id == "match_1"
    assert context.home_team.name == "Team A"
    assert context.away_team.name == "Team B"
    assert context.home_form_string == "WWDLL"
    assert len(context.missing_data_notes) == 1


def test_injury_model():
    """Test Injury model."""
    injury = Injury(
        id="injury_1",
        player_id="player_1",
        team_id="team_1",
        injury_type="Hamstring",
        status=InjuryStatus.OUT,
        start_date=date(2026, 9, 15),
        expected_return_date=date(2026, 10, 15),
    )
    assert injury.status == InjuryStatus.OUT
    assert injury.injury_type == "Hamstring"


def test_odds_model():
    """Test Odds model."""
    odds = Odds(
        id="odds_1",
        match_id="match_1",
        bookmaker="Bet365",
        home_win_odds=2.10,
        draw_odds=3.40,
        away_win_odds=3.60,
        fetched_at=datetime.now(),
    )
    assert odds.home_win_odds == 2.10
    assert odds.bookmaker == "Bet365"


def test_odds_phase5_fields_optional():
    """Test Phase 5 fields are optional in Odds model."""
    # Should work without Phase 5 fields (backward compatibility)
    odds = Odds(
        id="odds_1",
        match_id="match_1",
        bookmaker="Bet365",
        home_win_odds=2.10,
        draw_odds=3.40,
        away_win_odds=3.60,
        fetched_at=datetime.now(),
    )
    assert odds.source_provider is None
    assert odds.normalized_market_type is None
    assert odds.selection_label is None
    assert odds.odds_timestamp is None
    
    # Should work with Phase 5 fields
    odds_with_phase5 = Odds(
        id="odds_2",
        match_id="match_1",
        bookmaker="Bet365",
        home_win_odds=2.10,
        draw_odds=3.40,
        away_win_odds=3.60,
        fetched_at=datetime.now(),
        source_provider="development",
        normalized_market_type="match_result",
        selection_label="home",
        odds_timestamp=datetime.now(),
    )
    assert odds_with_phase5.source_provider == "development"
    assert odds_with_phase5.normalized_market_type == "match_result"
    assert odds_with_phase5.selection_label == "home"
    assert odds_with_phase5.odds_timestamp is not None


def test_odds_validation_rejects_invalid_odds():
    """Test odds validation rejects odds <= 1.0."""
    # Valid odds > 1.0 should work
    valid_odds = Odds(
        id="odds_1",
        match_id="match_1",
        bookmaker="Bet365",
        home_win_odds=2.10,
        draw_odds=3.40,
        away_win_odds=3.60,
        fetched_at=datetime.now(),
    )
    assert valid_odds.home_win_odds == 2.10
    
    # Invalid odds = 1.0 should fail
    with pytest.raises(ValueError):
        Odds(
            id="odds_2",
            match_id="match_1",
            bookmaker="Bet365",
            home_win_odds=1.0,  # Invalid: must be > 1.0
            fetched_at=datetime.now(),
        )
    
    # Invalid odds < 1.0 should fail
    with pytest.raises(ValueError):
        Odds(
            id="odds_3",
            match_id="match_1",
            bookmaker="Bet365",
            home_win_odds=0.5,  # Invalid: must be > 1.0
            fetched_at=datetime.now(),
        )
    
    # None is acceptable (missing odds)
    odds_with_none = Odds(
        id="odds_4",
        match_id="match_1",
        bookmaker="Bet365",
        home_win_odds=None,  # Valid: missing odds
        draw_odds=3.40,
        away_win_odds=3.60,
        fetched_at=datetime.now(),
    )
    assert odds_with_none.home_win_odds is None


def test_odds_accepts_valid_phase5_data():
    """Test Odds model accepts complete Phase 5 data."""
    timestamp = datetime.now()
    
    odds = Odds(
        id="odds_phase5",
        match_id="match_1",
        bookmaker="Bet365",
        home_win_odds=2.10,
        draw_odds=3.40,
        away_win_odds=3.60,
        over_under_line=2.5,
        over_odds=1.90,
        under_odds=1.95,
        btts_yes_odds=1.85,
        btts_no_odds=1.98,
        fetched_at=timestamp,
        source_provider="sofascore",
        normalized_market_type="match_result",
        selection_label="away",
        odds_timestamp=timestamp,
    )
    
    assert odds.id == "odds_phase5"
    assert odds.source_provider == "sofascore"
    assert odds.normalized_market_type == "match_result"
    assert odds.selection_label == "away"
    assert odds.odds_timestamp == timestamp
    assert odds.home_win_odds == 2.10
    assert odds.over_odds == 1.90
    assert odds.btts_yes_odds == 1.85


def test_backtest_result_model():
    """Test BacktestResult model."""
    result = BacktestResult(
        id="result_1",
        backtest_id="backtest_1",
        market_type=PredictionMarketType.MATCH_RESULT,
        total_predictions=380,
        total_matches=380,
        accuracy=0.52,
        brier_score=0.245,
        log_loss=0.98,
    )
    assert result.accuracy == 0.52
    assert result.brier_score == 0.245
    assert 0.0 <= result.brier_score <= 1.0


def test_live_match_state_model():
    """Test LiveMatchState model."""
    live_state = LiveMatchState(
        id="live_1",
        match_id="match_1",
        status=MatchStatus.LIVE,
        minute=34,
        home_score=1,
        away_score=0,
        home_possession=58.0,
        away_possession=42.0,
        updated_at=datetime.now(),
    )
    assert live_state.status == MatchStatus.LIVE
    assert live_state.minute == 34
    assert live_state.home_score == 1


def test_feature_snapshot_model():
    """Test FeatureSnapshot model."""
    snapshot = FeatureSnapshot(
        id="snapshot_1",
        match_id="match_1",
        team_id="team_1",
        snapshot_at=datetime.now(),
        features={
            "attack_strength": 1.45,
            "defense_strength": 0.92,
            "form_last_5": 2.4,
        },
        feature_set_version="v1.0",
    )
    assert snapshot.features["attack_strength"] == 1.45
    assert "form_last_5" in snapshot.features


def test_model_type_enum():
    """Test ModelType enum."""
    assert ModelType.POISSON == "poisson"
    assert ModelType.DIXON_COLES == "dixon_coles"
    assert ModelType.ELO == "elo"


def test_standing_model():
    """Test Standing model."""
    standing = Standing(
        id="standing_1",
        competition_id="comp_1",
        season_id="season_1",
        team_id="team_1",
        position=3,
        played=7,
        won=4,
        drawn=2,
        lost=1,
        goals_for=12,
        goals_against=6,
        goal_difference=6,
        points=14,
        form="WWDLW",
    )
    assert standing.position == 3
    assert standing.points == 14
    assert standing.goal_difference == 6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
