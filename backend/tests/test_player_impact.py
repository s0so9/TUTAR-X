"""Tests for player_impact module - DETERMINISTIC, DATA-DRIVEN ONLY."""

import pytest
from app.prediction.player_impact import (
    PlayerImpactEngine,
    PlayerImpactData,
    PlayerImpactResult,
    TeamLineupImpact,
)
from app.prediction.interfaces import ModelPrediction, ModelAvailability


class TestPlayerImpactData:
    """Tests for PlayerImpactData."""
    
    def test_player_has_sufficient_data(self):
        """Test sufficient data check."""
        player = PlayerImpactData(
            player_id="p1",
            player_name="Test Player",
            position="FW",
            matches_played=10,
            minutes_played=900,
            avg_xg_contribution=0.3
        )
        
        assert player.has_sufficient_data
    
    def test_player_insufficient_matches(self):
        """Test insufficient matches."""
        player = PlayerImpactData(
            player_id="p1",
            player_name="Test Player",
            position="FW",
            matches_played=3,  # < 5
            minutes_played=270,
            avg_xg_contribution=0.3
        )
        
        assert not player.has_sufficient_data
    
    def test_player_insufficient_minutes(self):
        """Test insufficient minutes."""
        player = PlayerImpactData(
            player_id="p1",
            player_name="Test Player",
            position="FW",
            matches_played=5,
            minutes_played=200,  # < 450
            avg_xg_contribution=0.3
        )
        
        assert not player.has_sufficient_data


class TestPlayerImpactEngine:
    """Tests for PlayerImpactEngine - NEVER FABRICATES DATA."""
    
    def test_engine_with_no_absent_players(self):
        """Test engine with no absent players."""
        engine = PlayerImpactEngine()
        
        prediction = ModelPrediction(
            model_id="test",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.9
        )
        
        result = engine.calculate_impact(prediction, [], [])
        
        assert isinstance(result, PlayerImpactResult)
        assert result.adjusted_home_xg == 1.5
        assert result.adjusted_away_xg == 1.2
    
    def test_engine_with_key_forward_absent(self):
        """Test impact of absent key forward."""
        engine = PlayerImpactEngine()
        
        prediction = ModelPrediction(
            model_id="test",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.9
        )
        
        # Key striker absent (0.4 xG per game)
        absent_striker = PlayerImpactData(
            player_id="p1",
            player_name="Star Striker",
            position="FW",
            matches_played=20,
            minutes_played=1800,
            avg_xg_contribution=0.4,
            avg_xa_contribution=0.15
        )
        
        result = engine.calculate_impact(prediction, [absent_striker], [])
        
        assert isinstance(result, PlayerImpactResult)
        # Home xG should decrease (striker absent)
        assert result.adjusted_home_xg < prediction.home_score_mean
        assert result.overall_confidence > 0.5  # Have data
    
    def test_engine_returns_unavailable_with_insufficient_data(self):
        """Test that engine returns ModelAvailability when data insufficient."""
        engine = PlayerImpactEngine()
        
        prediction = ModelPrediction(
            model_id="test",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.9
        )
        
        # Player with insufficient data
        unknown_player = PlayerImpactData(
            player_id="p_unknown",
            player_name="Unknown Player",
            position="FW",
            matches_played=2,  # Insufficient
            minutes_played=180,
            avg_xg_contribution=None
        )
        
        result = engine.calculate_impact(prediction, [unknown_player], [])
        
        # Should return unavailable (cannot assess impact reliably)
        assert isinstance(result, ModelAvailability)
        assert result.available is False
        assert "insufficient" in result.reason
    
    def test_engine_handles_partial_data(self):
        """Test engine with partial data (some players known, some not)."""
        engine = PlayerImpactEngine()
        
        prediction = ModelPrediction(
            model_id="test",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.9
        )
        
        known_player = PlayerImpactData(
            player_id="p1",
            player_name="Known Player",
            position="FW",
            matches_played=20,
            minutes_played=1800,
            avg_xg_contribution=0.3
        )
        
        unknown_player1 = PlayerImpactData(
            player_id="p2",
            player_name="Unknown Player 1",
            position="MF",
            matches_played=2,
            minutes_played=100,
            avg_xg_contribution=None
        )
        
        unknown_player2 = PlayerImpactData(
            player_id="p3",
            player_name="Unknown Player 2",
            position="DF",
            matches_played=1,
            minutes_played=90,
            avg_xg_contribution=None
        )
        
        # Now we have 1/3 players with data = 33% < 50%
        result = engine.calculate_impact(prediction, [known_player, unknown_player1, unknown_player2], [])
        
        if isinstance(result, PlayerImpactResult):
            # Confidence reduced due to partial data
            assert result.overall_confidence < 0.9
            assert result.home_team_impact.data_sufficiency == "partial"
    
    def test_engine_calculates_probability_adjustments(self):
        """Test that probability adjustments are calculated."""
        engine = PlayerImpactEngine()
        
        prediction = ModelPrediction(
            model_id="test",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.9
        )
        
        absent_forward = PlayerImpactData(
            player_id="p1",
            player_name="Forward",
            position="FW",
            matches_played=15,
            minutes_played=1350,
            avg_xg_contribution=0.35
        )
        
        result = engine.calculate_impact(prediction, [absent_forward], [])
        
        if isinstance(result, PlayerImpactResult):
            assert "home_win" in result.prob_adjustments
            assert "draw" in result.prob_adjustments
            assert "away_win" in result.prob_adjustments
            
            # Absent home forward should reduce home win probability
            assert result.prob_adjustments["home_win"] < 0
    
    def test_engine_never_fabricates_player_ratings(self):
        """Test that engine NEVER fabricates missing player data."""
        engine = PlayerImpactEngine()
        
        prediction = ModelPrediction(
            model_id="test",
            home_score_mean=1.5,
            away_score_mean=1.2,
            home_win_prob=0.45,
            draw_prob=0.30,
            away_win_prob=0.25,
            confidence_score=0.8,
            data_quality_score=0.9
        )
        
        # Player with NO historical data
        player_no_data = PlayerImpactData(
            player_id="p_new",
            player_name="New Player",
            position="FW",
            matches_played=0,
            minutes_played=0,
            avg_xg_contribution=None,
            avg_xa_contribution=None,
            avg_defensive_contribution=None
        )
        
        result = engine.calculate_impact(prediction, [player_no_data], [])
        
        # Should return unavailable, NOT fabricate an impact
        assert isinstance(result, ModelAvailability)
    
    def test_engine_ensures_non_negative_xg(self):
        """Test that engine ensures non-negative expected goals."""
        engine = PlayerImpactEngine()
        
        prediction = ModelPrediction(
            model_id="test",
            home_score_mean=0.3,  # Low xG
            away_score_mean=1.2,
            home_win_prob=0.15,
            draw_prob=0.30,
            away_win_prob=0.55,
            confidence_score=0.8,
            data_quality_score=0.9
        )
        
        # Star player absent with large impact
        star_player = PlayerImpactData(
            player_id="p1",
            player_name="Star Player",
            position="FW",
            matches_played=20,
            minutes_played=1800,
            avg_xg_contribution=0.5
        )
        
        result = engine.calculate_impact(prediction, [star_player], [])
        
        if isinstance(result, PlayerImpactResult):
            # xG should not go below 0.1 (minimum)
            assert result.adjusted_home_xg >= 0.1


# =============================================================================
# As-of xG-RAPM ratings runtime (PlayerImpactRatings). Synthetic TEST data only.
# =============================================================================

import csv as _csv
import gzip as _gzip
import json as _json

from app.prediction.player_impact import (
    PlayerImpactRatings,
    PlayerRating,
    replacement_from_rows,
)

_FIELDS = ["cutoff", "player_id", "team_id", "position", "minutes", "minutes_decayed", "xg_minutes",
           "rapm_minutes", "n_apps", "offence", "defence", "prior_offence", "prior_defence", "npxg90", "xa90",
           "xgxa90", "rating", "minutes_share", "market_value", "flags"]


def _row(cutoff, pid, pos, off, dfn, minutes=2000.0, flags=""):
    return {"cutoff": cutoff, "player_id": str(pid), "team_id": "7", "position": pos, "minutes": minutes,
            "minutes_decayed": minutes, "xg_minutes": minutes, "rapm_minutes": minutes, "n_apps": 20,
            "offence": off, "defence": dfn, "prior_offence": off / 2, "prior_defence": dfn / 2, "npxg90": 0.1,
            "xa90": 0.1, "xgxa90": 0.2, "rating": 7.0, "minutes_share": 0.8, "market_value": 1000000,
            "flags": flags}


def _write_ratings(tmp_path, rows, meta=None):
    path = tmp_path / "player_impact_asof.csv.gz"
    with _gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    if meta is not None:
        (tmp_path / "player_impact_meta.json").write_text(_json.dumps(meta), encoding="utf-8")
    return path


def _xi(prefix=1):
    return [f"{prefix}{k:02d}" for k in range(11)]


def _two_cutoff_file(tmp_path, with_meta=True):
    rows = []
    for cutoff, scale in (("2026-09-28", 1.0), ("2026-10-12", 2.0)):
        for k, pid in enumerate(_xi()):
            rows.append(_row(cutoff, pid, "GK" if k == 0 else "MID", 0.01 * k * scale, 0.02 * scale))
        rows.append(_row(cutoff, "199", "FWD", 0.3 * scale, -0.01, minutes=100.0))      # bench forward
    meta = {"per_cutoff": [
        {"cutoff": "2026-09-28", "replacement_level": {"GK": {"offence": -0.2, "defence": -0.05},
                                                       "DEF": {"offence": -0.1, "defence": 0.0},
                                                       "MID": {"offence": -0.03, "defence": -0.01},
                                                       "FWD": {"offence": 0.05, "defence": -0.02},
                                                       "UNK": {"offence": -0.01, "defence": -0.02}}},
        {"cutoff": "2026-10-12", "replacement_level": {"GK": {"offence": -0.25, "defence": -0.06},
                                                       "DEF": {"offence": -0.11, "defence": 0.01},
                                                       "MID": {"offence": -0.04, "defence": -0.02},
                                                       "FWD": {"offence": 0.06, "defence": -0.03},
                                                       "UNK": {"offence": -0.02, "defence": -0.03}}},
    ]}
    return _write_ratings(tmp_path, rows, meta if with_meta else None)


class TestPlayerImpactRatingsLoading:
    def test_latest_cutoff_on_or_before_as_of(self, tmp_path):
        path = _two_cutoff_file(tmp_path)
        assert PlayerImpactRatings.load(path).cutoff == "2026-10-12"
        assert PlayerImpactRatings.load(path, as_of="2026-10-11").cutoff == "2026-09-28"
        assert PlayerImpactRatings.load(path, as_of="2026-10-12T19:00:00+00:00").cutoff == "2026-10-12"
        with pytest.raises(ValueError):
            PlayerImpactRatings.load(path, as_of="2026-09-01")

    def test_values_are_returned_exactly_as_stored(self, tmp_path):
        path = _two_cutoff_file(tmp_path)
        r = PlayerImpactRatings.load(path, as_of="2026-09-30")
        assert r.get("105").offence == 0.05 and r.get(105).defence == 0.02
        assert r.get("999") is None


class TestXIStrength:
    def test_sum_of_rated_players(self, tmp_path):
        r = PlayerImpactRatings.load(_two_cutoff_file(tmp_path), as_of="2026-09-30")
        xi = r.xi_strength(_xi())
        assert xi.offence == pytest.approx(sum(0.01 * k for k in range(11)))
        assert xi.defence == pytest.approx(11 * 0.02)
        assert xi.complete and xi.n_rated == 11 and xi.flags == ()

    def test_unknown_player_gets_flagged_replacement_level(self, tmp_path):
        r = PlayerImpactRatings.load(_two_cutoff_file(tmp_path), as_of="2026-09-30")
        ids = _xi()[:10] + ["555"]
        xi = r.xi_strength(ids, positions={"555": "FWD"})
        assert xi.unknown_player_ids == ("555",) and not xi.complete
        assert "replacement_level_used" in xi.flags
        c = xi.contributions[-1]
        assert c.source == "replacement:FWD" and (c.offence, c.defence) == (0.05, -0.02)
        no_pos = r.xi_strength(ids)
        assert no_pos.contributions[-1].source == "replacement:UNK"

    def test_invalid_lineups(self, tmp_path):
        r = PlayerImpactRatings.load(_two_cutoff_file(tmp_path))
        with pytest.raises(ValueError):
            r.xi_strength([])
        with pytest.raises(ValueError):
            r.xi_strength(["101", "101"])
        assert "xi_size_10" in r.xi_strength(_xi()[:10]).flags

    def test_replacement_from_rows_without_meta(self, tmp_path):
        r = PlayerImpactRatings.load(_two_cutoff_file(tmp_path, with_meta=False), as_of="2026-09-30")
        # only the bench forward has < 450 minutes: the fringe pool is too small per position -> all fringe
        assert r.replacement["FWD"] == pytest.approx((0.3, -0.01))
        assert r.replacement["UNK"] == pytest.approx((0.3, -0.01))
        rows = [PlayerRating(str(k), "1", "DEF", 0.1 * k, 0.0, 0.0, 0.0, 100.0, 100.0) for k in range(6)]
        assert replacement_from_rows(rows)["DEF"][0] == pytest.approx(0.25)


class TestCompareToUsual:
    def test_delta_against_mean_of_recent_lineups(self, tmp_path):
        r = PlayerImpactRatings.load(_two_cutoff_file(tmp_path), as_of="2026-10-12")
        usual = [_xi()] * 5
        today = _xi()[:10] + ["199"]          # the bench forward replaces player 110
        cmp_ = r.compare_to_usual(today, usual)
        assert cmp_.available and cmp_.n_usual_lineups == 5
        assert cmp_.offence_delta == pytest.approx(2 * (0.3 - 0.10))
        assert cmp_.defence_delta == pytest.approx(-0.01 - 2 * 0.02)
        assert cmp_.usual_unknown_share == 0.0

    def test_only_last_n_lineups_count(self, tmp_path):
        r = PlayerImpactRatings.load(_two_cutoff_file(tmp_path), as_of="2026-10-12")
        old = _xi()[:10] + ["199"]
        cmp_ = r.compare_to_usual(_xi(), [old] * 3 + [_xi()] * 3, last_n=3)
        assert cmp_.offence_delta == pytest.approx(0.0)

    def test_insufficient_history_is_explicit(self, tmp_path):
        r = PlayerImpactRatings.load(_two_cutoff_file(tmp_path))
        cmp_ = r.compare_to_usual(_xi(), [_xi(), _xi()])
        assert not cmp_.available and cmp_.offence_delta is None and cmp_.defence_delta is None
        assert cmp_.reason == "usual_xi_needs_3_lineups_has_2"

    def test_unknown_players_in_usual_lineups_are_reported(self, tmp_path):
        r = PlayerImpactRatings.load(_two_cutoff_file(tmp_path), as_of="2026-10-12")
        with_new = _xi()[:10] + ["777"]
        cmp_ = r.compare_to_usual(_xi(), [with_new] * 4)
        assert cmp_.usual_unknown_share == pytest.approx(1 / 11)
        assert "usual_xi_replacement_level_used" in cmp_.flags
