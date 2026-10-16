"""Tests for the runtime match model (app.prediction.match_model) and its runtime features
(app.features.match_model_features), and for the wiring in app.features.match_features.

EVERY fixture in this file is SYNTHETIC TEST DATA (names start with "TEST" / "synthetic", FotMob-like
ids are in the 9xxxxx range, values are made up for the test). Nothing here is real football data.
"""

from __future__ import annotations

import json
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# =============================================================================================
# Extractor harness (synthetic) - shared by the "byte-identical when disabled" test
# =============================================================================================
SYNTH_KICKOFF = datetime(2026, 10, 14, 19, 0, tzinfo=timezone.utc)   # TEST kickoff
SYNTH_HOME_UUID = "synthetic-home-uuid"
SYNTH_AWAY_UUID = "synthetic-away-uuid"


def _memory_session():
    """Fresh in-memory SQLite session with the app schema (TEST database)."""
    from app.database.models import Base
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


class _SyntheticRatings:
    """TEST FIXTURE standing in for GlobalPoissonRatings (synthetic lambdas, not a fitted model)."""

    def __init__(self, home: float, away: float):
        self.home, self.away = home, away
        self.team_index = {SYNTH_HOME_UUID: 0, SYNTH_AWAY_UUID: 1}

    def predict(self, home_id, away_id, neutral=False):
        from app.prediction.team_ratings import MatchLambdas
        return MatchLambdas(home=self.home, away=self.away, home_matches=31, away_matches=29)


class _NoStandingsProvider:
    """TEST provider: no standings, no matches."""

    def get_standings(self, competition_id, season_id):
        raise NotImplementedError

    def get_matches(self, from_date=None, to_date=None):
        return []


SYNTH_HOME_XI = [str(910001 + i) for i in range(11)]   # synthetic player ids
SYNTH_AWAY_XI = [str(920001 + i) for i in range(11)]


def _synthetic_squad(home_value, away_value, unavailable_home=None, unavailable_away=None,
                     home_xi=None, away_xi=None, lineup_type="predicted"):
    from app.prediction.squad_value import TeamSquadInfo
    return (
        TeamSquadInfo(team_name="TEST Home FC", starter_value=home_value, lineup_type=lineup_type,
                      unavailable=_synthetic_unavailable(unavailable_home), team_id="900001",
                      starter_ids=list(SYNTH_HOME_XI if home_xi is None else home_xi)),
        TeamSquadInfo(team_name="TEST Away FC", starter_value=away_value, lineup_type=lineup_type,
                      unavailable=_synthetic_unavailable(unavailable_away), team_id="900002",
                      starter_ids=list(SYNTH_AWAY_XI if away_xi is None else away_xi)),
    )


def _synthetic_lineup_form():
    from app.prediction.lineup_form import LineupForm
    players = {pid: 6.6 + 0.05 * (k % 7) for k, pid in enumerate(SYNTH_HOME_XI + SYNTH_AWAY_XI)}
    return LineupForm(gamma=0.2157, players=players, usual={"900001": 6.71, "900002": 6.83}, min_known=7)


def _synthetic_goal_layer():
    from app.prediction.goal_model import GoalLayer
    return GoalLayer(m=0.26, a=0.676, b=0.0344, rho=-0.023, nb_dispersion=50.0, trained=True)


SCENARIOS = {
    # name: (ratings (home, away) or None, squad kwargs or None, lineup form on?, competition name, match id)
    "no_squad_info": ((1.62, 1.07), None, True, "Premier League", "fotmob_99000001"),
    "value_and_form_domestic": ((1.62, 1.07), {"home_value": 512_000_000.0, "away_value": 188_000_000.0},
                                True, "Premier League", "fotmob_99000001"),
    "value_cross_league_no_form": ((1.31, 1.44), {"home_value": 61_000_000.0, "away_value": 702_000_000.0},
                                   False, "Champions League", "fotmob_99000002"),
    "one_value_missing_form": ((1.05, 0.97), {"home_value": None, "away_value": 88_000_000.0},
                               True, "Super Lig", "fotmob_99000003"),
    "no_ratings": (None, {"home_value": 512_000_000.0, "away_value": 188_000_000.0}, True, "Premier League",
                   "fotmob_99000004"),
    "non_fotmob_match_id": ((1.40, 1.20), {"home_value": 300_000_000.0, "away_value": 150_000_000.0},
                            True, "LaLiga", "synthetic-db-match-uuid"),
    "unavailable_lists": ((1.50, 1.30), {"home_value": 250_000_000.0, "away_value": 240_000_000.0,
                                         "unavailable_home": [], "unavailable_away": "two_players"},
                          True, "Bundesliga", "fotmob_99000005"),
}


def _synthetic_unavailable(kind):
    from app.prediction.squad_value import UnavailablePlayer
    if kind != "two_players":
        return kind
    return [UnavailablePlayer(name="TEST Player A", reason="injury", expected_return=None, market_value=12_000_000.0),
            UnavailablePlayer(name="TEST Player B", reason="suspension", expected_return=None, market_value=None)]


def run_extractor_scenario(name: str, extra_patches=()) -> dict:
    """Run MatchFeatureExtractor.extract_features on a synthetic scenario; returns a JSON-able
    record of everything the extractor exposes (features dict, squad info, lineup-form shift)."""
    from app.domain.match import Match
    from app.features.match_features import MatchFeatureExtractor

    ratings_hw, squad_kw, form_on, comp_name, match_id = SCENARIOS[name]
    ratings = _SyntheticRatings(*ratings_hw) if ratings_hw else None
    squad = _synthetic_squad(**squad_kw) if squad_kw else None
    session = _memory_session()
    try:
        match = Match(id=match_id, competition_id="synthetic-comp", season_id="2026/2027",
                      home_team_id=SYNTH_HOME_UUID, away_team_id=SYNTH_AWAY_UUID, scheduled_at=SYNTH_KICKOFF)
        match._provider_competition_name = comp_name
        with ExitStack() as stack:
            stack.enter_context(mock.patch("app.prediction.team_ratings.get_ratings_for_match_day",
                                           lambda session, kickoff: ratings))
            stack.enter_context(mock.patch("app.prediction.squad_value.fetch_squad_info",
                                           lambda mid, base_url: squad))
            stack.enter_context(mock.patch("app.prediction.lineup_form.get_lineup_form",
                                           lambda *a, **k: _synthetic_lineup_form() if form_on else None))
            stack.enter_context(mock.patch("app.prediction.goal_model.get_goal_layer",
                                           lambda *a, **k: _synthetic_goal_layer()))
            for target, value in extra_patches:
                stack.enter_context(mock.patch(target, value))
            extractor = MatchFeatureExtractor(provider=_NoStandingsProvider(), db_session=session)
            features = extractor.extract_features(match)
        return {
            "features": json.dumps(features, sort_keys=True, default=repr),
            "squad_info": repr(extractor.squad_info),
            "lineup_form_shift": repr(extractor.lineup_form_shift),
        }
    finally:
        session.close()
