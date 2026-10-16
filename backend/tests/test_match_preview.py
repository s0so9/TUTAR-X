"""Pre-match analysis ("Maç analizi"): history windows, rest days, rotation, highlight
templates, and the endpoint end to end.

EVERYTHING BELOW IS SYNTHETIC TEST DATA (made-up teams "Test Ev" / "Test Dep", made-up
results, a scratch in-memory database, a fake live centre and a fake FotMob client). It
is not football data and is never shown to users.
"""

from __future__ import annotations

import asyncio
import gzip
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database.models import Competition, Match, ProviderSource, Team
from app.database.session import get_db
from app.domain.enums import MatchStatus
from app.services.live_center.schemas import (
    LineupPlayer,
    Lineups,
    LiveCenterResponse,
    ScorePair,
    Stats,
    TeamInfo,
    TeamLineup,
    Teams,
    UnavailablePlayer,
)
from app.services.live_center.service import LiveCenterError
from app.services.match_preview import service as preview_service_module
from app.services.match_preview.highlights import MAX_HIGHLIGHTS, build_highlights, form_statement
from app.services.match_preview.history import (
    FixturesPayloadError,
    build_rest,
    build_window,
    dedupe_matches,
    is_friendly,
    parse_team_fixtures,
    previous_competitive_match,
)
from app.services.match_preview.rotation import compute_rotation, rotation_problem
from app.services.match_preview.schemas import (
    Absentee,
    AbsenteesInfo,
    LineupInfo,
    PlayerRef,
    PreviewMatch,
    PreviewSide,
    RestInfo,
    RotationInfo,
)
from app.services.match_preview.service import MatchPreviewService
from app.services.match_preview.turkish import count_accusative, decimal, join_names
from app.services.team_news.fotmob_client import FetchResult, FotMobUnavailableError

KICKOFF = datetime(2026, 10, 15, 19, 0, tzinfo=timezone.utc)


# ============================================================================ pure helpers


def test_turkish_helpers():
    assert [count_accusative(n) for n in range(1, 6)] == ["1'ini", "2'sini", "3'ünü", "4'ünü", "5'ini"]
    with pytest.raises(ValueError):
        count_accusative(9)
    assert decimal(5.84) == "5,8" and decimal(11.0, 2) == "11,00"
    assert join_names(["A"]) == "A"
    assert join_names(["A", "B"]) == "A ve B"
    assert join_names(["A", "B", "C"]) == "A, B ve C"
    assert join_names([]) == ""


def pm(days_ago, venue, gf, ga, xg=None, comp="Test League (synthetic)", friendly=False, opp="Rakip", mid=None, hours=0, source="database"):
    """A synthetic played match ``days_ago`` days before KICKOFF."""
    date = KICKOFF - timedelta(days=days_ago, hours=hours)
    letter = "G" if gf > ga else ("M" if gf < ga else "B")
    return PreviewMatch(
        match_id=mid or str(1000000 + int(days_ago * 100) + (7 if venue == "away" else 0)),
        date=date,
        competition=comp,
        is_friendly=friendly,
        venue=venue,
        opponent=opp,
        opponent_id=f"opp-{opp}",
        goals_for=gf,
        goals_against=ga,
        result=letter,
        xg_for=None if xg is None else xg[0],
        xg_against=None if xg is None else xg[1],
        source=source,
    )


def test_window_results_goals_and_xg_exclude_friendlies():
    history = [
        pm(4, "home", 0, 2, xg=(0.8, 1.9)),
        pm(6, "away", 1, 3, xg=(1.0, 2.0)),
        pm(8, "home", 1, 2),  # no xG
        pm(9, "home", 5, 0, friendly=True, comp="Club Friendlies"),  # not part of the window
        pm(11, "away", 2, 2, xg=(1.1, 1.4)),
        pm(14, "home", 3, 1, xg=(2.2, 0.5)),
        pm(18, "home", 4, 0),  # 6th competitive match: outside the window
    ]
    w = build_window(history, scope="last5")
    assert w.played == 5
    assert w.results == "MMMBG"  # most recent first
    assert (w.wins, w.draws, w.losses) == (1, 1, 3)
    assert (w.goals_for, w.goals_against) == (0 + 1 + 1 + 2 + 3, 2 + 3 + 2 + 2 + 1)
    assert [m.is_friendly for m in w.matches] == [False] * 5
    # xG only over the matches that have it, with their count
    assert w.xg_matches == 4
    assert w.xg_for == pytest.approx(0.8 + 1.0 + 1.1 + 2.2)
    assert w.xg_against == pytest.approx(1.9 + 2.0 + 1.4 + 0.5)
    assert w.xg_missing_reason == "xG yalnızca 4/5 maçta var."
    assert w.missing_reason is None


def test_venue_window_only_home_matches():
    history = [pm(4, "home", 0, 2), pm(6, "away", 1, 3), pm(8, "home", 1, 2), pm(11, "away", 2, 2), pm(14, "home", 3, 1)]
    w = build_window(history, scope="last5_venue", venue="home")
    assert w.played == 3 and w.results == "MMG"
    assert (w.goals_for, w.goals_against) == (4, 5)
    assert w.missing_reason == "Son 5 yerine 3 maç bulundu."


def test_window_without_matches_is_null_with_reason():
    w = build_window([pm(3, "home", 1, 0, friendly=True, comp="Club Friendlies")], scope="last5")
    assert w.played == 0
    assert w.results is None and w.wins is None and w.goals_for is None and w.xg_for is None
    assert w.missing_reason == "Bu takım için kayıtlı maç bulunamadı."
    away = build_window([], scope="last5_venue", venue="away")
    assert away.missing_reason == "Bu takım için deplasmanda kayıtlı maç bulunamadı."


def test_window_without_any_xg_says_so_instead_of_zero():
    w = build_window([pm(d, "home", 1, 0) for d in (3, 6, 9, 12, 15)], scope="last5")
    assert w.xg_matches == 0 and w.xg_for is None and w.xg_against is None
    assert w.xg_missing_reason == "Bu maçlar için xG verisi yok."


def test_is_friendly_by_name_or_competition_id():
    assert is_friendly("Club Friendlies") and is_friendly("Friendlies U21") and is_friendly(None, "489")
    assert not is_friendly("Europa League") and not is_friendly(None)


def test_rest_days_and_fixture_load():
    # previous match 4 calendar days earlier (UTC dates), 3 matches in the 14 days, a friendly counts
    history = [pm(4, "home", 1, 0), pm(8, "away", 0, 0), pm(12, "home", 2, 1, friendly=True, comp="Club Friendlies"), pm(20, "home", 1, 1)]
    rest = build_rest(history, KICKOFF)
    assert rest.rest_days == 4
    assert rest.matches_last_14_days == 3
    assert rest.previous_match.match_id == history[0].match_id
    assert rest.missing_reason is None


def test_rest_days_use_calendar_dates_not_24h_blocks():
    previous = KICKOFF.replace(hour=22, minute=30) - timedelta(days=3)  # Monday 22:30 -> Thursday 19:00 = 3 calendar days
    m = pm(3, "home", 1, 0)
    m = m.model_copy(update={"date": previous})
    assert build_rest([m], KICKOFF).rest_days == 3


def test_rest_without_history_is_null():
    rest = build_rest([], KICKOFF)
    assert rest.rest_days is None and rest.matches_last_14_days is None and rest.previous_match is None
    assert rest.missing_reason == "Önceki maç kaydı bulunamadı."


def test_previous_competitive_match_skips_friendlies():
    history = [pm(2, "home", 1, 0, friendly=True, comp="Club Friendlies"), pm(5, "away", 0, 1)]
    assert previous_competitive_match(history, KICKOFF).match_id == history[1].match_id
    assert previous_competitive_match([], KICKOFF) is None


def test_dedupe_keeps_row_with_xg_and_short_id():
    twin_a = pm(5, "home", 1, 2, opp="Same", mid="1000011002")
    twin_b = pm(5, "home", 1, 2, opp="Same", mid="5403663", xg=(1.0, 1.2))
    other = pm(9, "home", 0, 0, opp="Other")
    out = dedupe_matches([twin_a, other, twin_b])
    assert [m.match_id for m in out] == ["5403663", other.match_id]
    # a different score on the same day is not a duplicate
    assert len(dedupe_matches([pm(5, "home", 1, 2, opp="Same"), pm(5, "home", 0, 0, opp="Same", mid="1")])) == 2


# ---- FotMob team page

def _fx(match_id, when, home, away, hs, as_, league="Test League (synthetic)", league_id=1, finished=True, cancelled=False):
    return {
        "id": match_id,
        "home": {"id": home[0], "name": home[1], "score": hs},
        "away": {"id": away[0], "name": away[1], "score": as_},
        "tournament": {"name": league, "leagueId": league_id},
        "status": {"utcTime": when.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "finished": finished, "cancelled": cancelled, "started": finished},
    }


def _team_page(fixtures):
    return {"fixtures": {"allFixtures": {"fixtures": fixtures}}}


def test_parse_team_fixtures_gap_fill():
    team = (9001, "Test Ev")
    newest_local = KICKOFF - timedelta(days=8)
    page = _team_page(
        [
            _fx(11, KICKOFF - timedelta(days=2), team, (9100, "Gap Away"), 2, 1),  # new, home win
            _fx(12, KICKOFF - timedelta(days=5), (9101, "Gap Home"), team, 3, 3),  # new, away draw
            _fx(13, KICKOFF - timedelta(days=9), team, (9102, "Old"), 0, 0),  # older than the newest local match
            _fx(14, KICKOFF - timedelta(days=6), team, (9103, "Known"), 1, 0),  # already in the database
            _fx(15, KICKOFF - timedelta(days=1), team, (9104, "Cancelled"), 0, 0, cancelled=True),
            _fx(16, KICKOFF + timedelta(days=3), team, (9105, "Future"), None, None, finished=False),
            _fx(17, KICKOFF + timedelta(hours=-0), team, (9106, "Same time"), 1, 1),  # not before kick-off
            _fx(18, KICKOFF - timedelta(days=3), (9200, "Not Mine"), (9201, "Other"), 1, 0),  # team is not in it
            _fx(19, KICKOFF - timedelta(days=4), team, (9107, "Friendly"), 4, 0, league="Club Friendlies", league_id=489),
        ]
    )
    got = parse_team_fixtures(page, "9001", before=KICKOFF, after=newest_local, known_match_ids={"14"})
    assert [(m.match_id, m.venue, m.goals_for, m.goals_against, m.result) for m in got] == [
        ("11", "home", 2, 1, "G"),
        ("12", "away", 3, 3, "B"),
        ("19", "home", 4, 0, "G"),
    ]
    assert all(m.source == "fotmob_team_fixtures" and m.xg_for is None for m in got)
    assert got[2].is_friendly and not got[0].is_friendly
    assert got[0].opponent == "Gap Away" and got[1].opponent == "Gap Home"


def test_parse_team_fixtures_rejects_unknown_payload():
    for bad in (None, {}, {"fixtures": {}}, {"fixtures": {"allFixtures": {"fixtures": "x"}}}):
        with pytest.raises(FixturesPayloadError):
            parse_team_fixtures(bad, "9001", before=KICKOFF, after=None, known_match_ids=set())


# ---- rotation

def _xi(prefix, n=11):
    return [PlayerRef(id=f"{prefix}{i}", name=f"{prefix.upper()} Player {i}") for i in range(n)]


def test_compute_rotation_counts_new_starters_and_lists_both_directions():
    previous = _xi("p")
    today = previous[:6] + _xi("n", 5)  # 5 new starters
    assert rotation_problem(today, previous) is None
    changes, came_in, dropped_out = compute_rotation(today, previous)
    assert changes == 5
    assert [p.id for p in came_in] == ["n0", "n1", "n2", "n3", "n4"]
    assert [p.id for p in dropped_out] == ["p6", "p7", "p8", "p9", "p10"]
    # identical XI: zero changes, empty lists
    assert compute_rotation(previous, previous) == (0, [], [])
    # an order change is not a change
    assert compute_rotation(list(reversed(previous)), previous)[0] == 0


def test_compute_rotation_falls_back_to_names_without_ids():
    previous = [PlayerRef(id=None, name=f"Anon {i}") for i in range(11)]
    today = [PlayerRef(id=None, name=f"anon {i}") for i in range(10)] + [PlayerRef(id=None, name="Newcomer")]
    assert compute_rotation(today, previous)[0] == 1


def test_rotation_problem_reports_incomplete_data():
    assert "ilk 11 eksik (9 oyuncu)" in rotation_problem(_xi("n", 9), _xi("p"))
    assert "Önceki maçın ilk 11'i eksik (10 oyuncu)" in rotation_problem(_xi("n"), _xi("p", 10))
    assert rotation_problem([PlayerRef()] * 11, _xi("p")) == "Oyuncu kimlikleri eksik, karşılaştırma yapılamadı."


# ============================================================================ highlight templates


def _side(name, history, venue, *, rest=None, absent=None, lineup_type=None, changes=None, verified=True, absent_available=True, matches_14d=None):
    rest_info = RestInfo(rest_days=rest, matches_last_14_days=matches_14d) if (rest is not None or matches_14d is not None) else RestInfo(missing_reason="yok")
    rotation = RotationInfo(changes=changes)
    return PreviewSide(
        team_id=name,
        team_name=name,
        last5=build_window(history, scope="last5"),
        venue_last5=build_window(history, scope="last5_venue", venue=venue),
        rest=rest_info,
        absentees=AbsenteesInfo(available=absent_available, players=absent or []),
        lineup=LineupInfo(lineup_type=lineup_type, starters_count=11 if lineup_type else 0, rotation=rotation),
        history_verified=verified,
    )


def _venue_run(results, venue):
    """Matches of one venue from (gf, ga) pairs, most recent first, spread over weeks."""
    return [pm(7 * (i + 1), venue, gf, ga) for i, (gf, ga) in enumerate(results)]


def _texts(highlights):
    return {h.kind: h.text for h in highlights}


@pytest.mark.parametrize(
    "results,expected",
    [
        # 5 wins -> "kazandı"; goals for-against of the five
        ([(3, 1), (2, 0), (4, 2), (5, 3), (2, 1)], "Test Ev evde son 5 maçı kazandı (16–7)."),
        # 4 wins of 5
        ([(3, 1), (2, 0), (4, 2), (0, 1), (2, 1)], "Test Ev evde son 5 maçın 4'ünü kazandı (11–5)."),
        # 3 losses of 5
        ([(1, 2), (0, 3), (2, 2), (1, 2), (5, 2)], "Test Ev evde son 5 maçın 3'ünü kaybetti (9–11)."),
        # all lost
        ([(0, 1), (0, 2), (1, 2), (0, 3), (1, 4)], "Test Ev evde son 5 maçı kaybetti (2–12)."),
        # no win at all (draws and one loss)
        ([(1, 1), (0, 0), (2, 2), (0, 1), (1, 1)], "Test Ev evde son 5 maçta hiç kazanamadı (4–5)."),
        # unbeaten: 3 wins and 2 draws
        ([(1, 0), (2, 2), (3, 1), (0, 0), (2, 1)], "Test Ev evde son 5 maçta yenilmedi (8–4)."),
    ],
)
def test_form_templates_fire_with_exact_sentence(results, expected):
    side = _side("Test Ev", _venue_run(results, "home"), "home")
    statement = form_statement("Test Ev", side.venue_last5, "evde")
    assert statement is not None and statement[2] == expected


@pytest.mark.parametrize(
    "results",
    [
        [(1, 0), (0, 1), (2, 1), (1, 1), (0, 2)],  # 2W 1D 2L: nothing notable
        [(1, 0), (1, 0), (0, 1), (0, 0), (2, 1)],  # 3W 1D 1L: not unbeaten (a loss), 3 wins only
        [(1, 0), (0, 1), (0, 1), (1, 1), (2, 1)],  # 2 losses of 5: below the threshold
    ],
)
def test_form_templates_stay_silent_for_ordinary_runs(results):
    side = _side("Test Ev", _venue_run(results, "home"), "home")
    assert form_statement("Test Ev", side.venue_last5, "evde") is None


def test_form_template_needs_four_matches():
    side = _side("Test Ev", _venue_run([(1, 0), (2, 0), (1, 0)], "home"), "home")
    assert form_statement("Test Ev", side.venue_last5, "evde") is None
    four = _side("Test Ev", _venue_run([(1, 0), (2, 0), (1, 0), (3, 0)], "home"), "home")
    assert form_statement("Test Ev", four.venue_last5, "evde")[2] == "Test Ev evde son 4 maçı kazandı (7–0)."


def test_away_side_uses_away_wording_and_second_statement_only_when_it_contradicts():
    # away: lost 3 of the last 5 away matches, but 4 wins in the last 5 overall (home wins)
    history = _venue_run([(0, 1), (1, 2), (0, 2), (2, 1), (3, 0)], "away")  # days 7..35
    history += [pm(1, "home", 3, 0), pm(2, "home", 2, 1), pm(3, "home", 1, 0), pm(4, "home", 4, 1)]
    history.sort(key=lambda m: m.date, reverse=True)
    away = _side("Test Dep", history, "away")
    assert away.last5.results == "GGGGM"
    texts = [h.text for h in build_highlights(_side("Test Ev", [], "home"), away) if h.side == "away"]
    assert "Test Dep deplasmanda son 5 maçın 3'ünü kaybetti (6–6)." in texts
    assert "Test Dep son 5 maçın 4'ünü kazandı (10–3)." in texts  # the opposite overall story is told too


def test_same_story_is_not_told_twice():
    # strong at home AND strong overall (same polarity): only the venue sentence
    history = [pm(i * 6 + 1, "home", 2, 0) for i in range(5)]
    out = build_highlights(_side("Test Ev", history, "home"), _side("Test Dep", [], "away"))
    form = [h for h in out if h.kind.startswith("form")]
    assert len(form) == 1 and form[0].kind == "form_venue"


@pytest.mark.parametrize(
    "gf,ga,expected_kind,expected_text",
    [
        (7, 1, "goals_against", "Test Ev son 5 maçta sadece 1 gol yedi."),
        (7, 0, "goals_against", "Test Ev son 5 maçta kalesinde gol görmedi."),
        (7, 2, "goals_against", "Test Ev son 5 maçta sadece 2 gol yedi."),
        (6, 9, "goals_against", "Test Ev son 5 maçta 9 gol yedi."),
        (1, 6, "goals_for", "Test Ev son 5 maçta sadece 1 gol attı."),
        (0, 6, "goals_for", "Test Ev son 5 maçta gol atamadı."),
        (12, 7, "goals_for", "Test Ev son 5 maçta 12 gol attı."),
        (6, 6, None, None),  # nothing notable
        (6, 8, None, None),  # just below the 9-goal threshold
        (11, 6, None, None),  # just below the 12-goal threshold
        (3, 3, None, None),
    ],
)
def test_goal_templates(gf, ga, expected_kind, expected_text):
    # split the goals over five matches (the form window is not what is tested here)
    gfs = [gf // 5 + (1 if i < gf % 5 else 0) for i in range(5)]
    gas = [ga // 5 + (1 if i < ga % 5 else 0) for i in range(5)]
    history = [pm(6 * i + 2, "away" if i % 2 else "home", gfs[i], gas[i]) for i in range(5)]
    side = _side("Test Ev", history, "home")
    assert (side.last5.goals_for, side.last5.goals_against) == (gf, ga)
    out = [h for h in build_highlights(side, _side("Test Dep", [], "away")) if h.kind in ("goals_for", "goals_against")]
    if expected_kind is None:
        assert out == []
    else:
        assert [(h.kind, h.text) for h in out] == [(expected_kind, expected_text)]


def test_xg_template_fires_on_a_gap_of_three_goals_and_needs_four_matches_with_xg():
    # 4 matches with xG: 11 goals scored from 7.6 xG (gap 3.4); conceded 2 against 2.2 xGA
    history = [pm(5 + 6 * i, "home", g, 1, xg=(x, 0.55)) for i, (g, x) in enumerate([(3, 1.9), (3, 1.9), (3, 1.9), (2, 1.9)])]
    history.append(pm(40, "home", 0, 1))
    side = _side("Test Ev", history, "home")
    hl = _texts(build_highlights(side, _side("Test Dep", [], "away")))
    assert hl["xg_attack"] == "Test Ev son 4 maçta xG toplamı 7,6 iken 11 gol attı."
    assert "xg_defence" not in hl
    # only 3 matches with xG -> silent
    thin = [pm(5 + 6 * i, "home", 3, 1, xg=(1.0, 0.5)) for i in range(3)] + [pm(30, "home", 1, 1), pm(36, "home", 1, 1)]
    assert "xg_attack" not in _texts(build_highlights(_side("Test Ev", thin, "home"), _side("Test Dep", [], "away")))
    # gap below 3 goals -> silent
    close = [pm(5 + 6 * i, "home", 2, 1, xg=(1.8, 0.9)) for i in range(5)]  # 10 goals from 9.0 xG
    assert "xg_attack" not in _texts(build_highlights(_side("Test Ev", close, "home"), _side("Test Dep", [], "away")))


def test_xg_defence_template():
    history = [pm(5 + 6 * i, "home", 1, ga, xg=(1.0, 1.5)) for i, ga in enumerate([1, 1, 1, 0, 0])]  # 3 conceded, 7.5 xGA
    out = _texts(build_highlights(_side("Test Ev", history, "home"), _side("Test Dep", [], "away")))
    assert out["xg_defence"] == "Test Ev son 5 maçta rakiplerin xG toplamı 7,5 iken 3 gol yedi."
    # a stronger goals sentence ("kalesinde gol görmedi") replaces the xG one: one goal story per team
    clean = [pm(5 + 6 * i, "home", 1, 0, xg=(1.0, 1.5)) for i in range(5)]
    out = _texts(build_highlights(_side("Test Ev", clean, "home"), _side("Test Dep", [], "away")))
    assert out["goals_against"] == "Test Ev son 5 maçta kalesinde gol görmedi." and "xg_defence" not in out


@pytest.mark.parametrize(
    "home_rest,away_rest,expected",
    [
        (3, 4, "Test Ev 3 gün dinlendi, Test Dep 4 gün."),
        (4, 3, "Test Ev 4 gün dinlendi, Test Dep 3 gün."),
        (3, 3, "Test Ev ve Test Dep 3 gün dinlendi."),
        (7, 4, "Test Ev 7 gün dinlendi, Test Dep 4 gün."),  # gap of 3 days
        (2, 6, "Test Ev 2 gün dinlendi, Test Dep 6 gün."),
        (4, None, None),
        (3, None, "Test Ev 3 gün dinlendi."),
        (5, 4, None),
        (5, 6, None),
        (None, None, None),
    ],
)
def test_rest_template_thresholds(home_rest, away_rest, expected):
    out = _texts(build_highlights(_side("Test Ev", [], "home", rest=home_rest), _side("Test Dep", [], "away", rest=away_rest)))
    assert out.get("rest") == expected


def test_congestion_template():
    out = _texts(build_highlights(_side("Test Ev", [], "home", rest=4, matches_14d=4), _side("Test Dep", [], "away", rest=4, matches_14d=3)))
    assert out["congestion"] == "Test Ev son 14 günde 4 maç oynadı."
    assert "Test Dep son 14 günde" not in " ".join(out.values())


def _absentee(name, code="injury", started=None):
    return Absentee(id=name, name=name, reason_code=code, started_previous_match=started)


def test_absentee_templates():
    three = [_absentee("A Oyuncu"), _absentee("B Oyuncu"), _absentee("C Oyuncu", "suspension")]
    out = _texts(build_highlights(_side("Test Ev", [], "home", absent=three), _side("Test Dep", [], "away", absent=[])))
    assert out["absentees"] == "Test Ev için eksikler: C Oyuncu (cezalı), A Oyuncu ve B Oyuncu."  # suspension named first
    six = [_absentee(f"P{i}", started=(i < 2)) for i in range(6)]
    out6 = _texts(build_highlights(_side("Test Ev", [], "home", absent=six), _side("Test Dep", [], "away")))
    assert out6["absentees"] == "Test Ev için 6 oyuncu eksik: P0, P1, P2 ve 3 oyuncu daha."
    # doubtful players are not "yok": their own, weaker sentence
    doubtful = _texts(build_highlights(_side("Test Ev", [], "home", absent=[_absentee("X Oyuncu", "doubtful")]), _side("Test Dep", [], "away")))
    assert "absentees" not in doubtful and doubtful["doubtful"] == "Test Ev için şüpheli: X Oyuncu."
    # no availability data from the source -> no sentence (and no "yok" claim)
    none = build_highlights(_side("Test Ev", [], "home", absent_available=False), _side("Test Dep", [], "away"))
    assert none == []
    # starters of the previous match raise the importance
    plain = [h for h in build_highlights(_side("Test Ev", [], "home", absent=[_absentee("A")]), _side("Test Dep", [], "away"))][0]
    key = [h for h in build_highlights(_side("Test Ev", [], "home", absent=[_absentee("A", started=True)]), _side("Test Dep", [], "away"))][0]
    assert key.importance > plain.importance


@pytest.mark.parametrize(
    "lineup_type,changes,expected",
    [
        ("confirmed", 5, "Test Ev geçen maça göre 5 değişiklikle sahada."),
        ("confirmed", 4, "Test Ev geçen maça göre 4 değişiklikle sahada."),
        ("confirmed", 3, None),
        ("confirmed", 0, None),
        ("predicted", 6, "Test Ev tahmini ilk 11'de geçen maça göre 6 değişiklik var."),
        ("predicted", 2, None),
        ("last_starting11", 7, None),  # FotMob's "last XI" is not today's line-up
        (None, 7, None),
    ],
)
def test_rotation_template(lineup_type, changes, expected):
    out = _texts(build_highlights(_side("Test Ev", [], "home", lineup_type=lineup_type, changes=changes), _side("Test Dep", [], "away")))
    assert out.get("rotation") == expected


def test_unverified_history_gets_no_history_sentences_but_keeps_absentees_and_rotation():
    history = _venue_run([(3, 0), (2, 0), (1, 0), (2, 0), (4, 0)], "home")
    side = _side("Test Ev", history, "home", rest=2, matches_14d=5, absent=[_absentee("A Oyuncu")], lineup_type="confirmed", changes=5, verified=False)
    kinds = {h.kind for h in build_highlights(side, _side("Test Dep", [], "away"))}
    assert kinds == {"absentees", "rotation"}  # no form / goals / rest / congestion sentence for the unverified side


def test_highlights_are_ordered_by_importance_and_capped():
    hist_home = _venue_run([(3, 0), (2, 0), (4, 1), (5, 0), (2, 0)], "home")
    hist_away = _venue_run([(0, 3), (1, 4), (0, 2), (0, 1), (1, 2)], "away")
    home = _side("Test Ev", hist_home, "home", rest=2, matches_14d=5, absent=[_absentee(f"P{i}", started=True) for i in range(5)], lineup_type="confirmed", changes=6)
    away = _side("Test Dep", hist_away, "away", rest=3, absent=[_absentee("Z Oyuncu")], lineup_type="confirmed", changes=4)
    out = build_highlights(home, away)
    assert len(out) <= MAX_HIGHLIGHTS == 6
    importances = [h.importance for h in out]
    assert importances == sorted(importances, reverse=True)
    assert len({h.id for h in out}) == len(out)
    assert max(sum(1 for h in out if h.side == s) for s in ("home", "away")) <= 4
    for h in out:  # every sentence carries its numbers and states no advice
        assert h.text.endswith(".") and h.facts
        assert not any(word in h.text.lower() for word in ("bahis", "oyna ", "kupon", "öner", "tavsiye", "değer"))


def test_nothing_notable_gives_no_highlights():
    ordinary = [pm(7 * (i + 1), "home" if i % 2 else "away", gf, ga) for i, (gf, ga) in enumerate([(1, 0), (1, 1), (0, 1), (2, 2), (1, 0)])]
    out = build_highlights(_side("Test Ev", ordinary, "home", rest=5, absent=[]), _side("Test Dep", ordinary, "away", rest=5, absent=[]))
    assert out == []


# ============================================================================ service + endpoint


@pytest.fixture()
def scratch_db(db_session):
    """db_session of conftest (in-memory SQLite) with a provider source and one competition."""
    source = ProviderSource(name="fotmob", is_active=True)
    db_session.add(source)
    db_session.flush()
    league = Competition(provider_source_id=source.id, provider_id="9999", name="Test League (synthetic)")
    friendlies = Competition(provider_source_id=source.id, provider_id="489", name="Club Friendlies")
    db_session.add_all([league, friendlies])
    db_session.flush()
    db_session.info.update(source=source, league=league, friendlies=friendlies, teams={})
    return db_session


def _team(db, provider_id, name):
    teams = db.info["teams"]
    if provider_id not in teams:
        team = Team(provider_source_id=db.info["source"].id, provider_id=provider_id, name=name)
        db.add(team)
        db.flush()
        teams[provider_id] = team
    return teams[provider_id]


def _add_match(db, match_id, when, home, away, hs, as_, hxg=None, axg=None, friendly=False, status=MatchStatus.FINISHED):
    h = _team(db, *home)
    a = _team(db, *away)
    db.add(
        Match(
            provider_source_id=db.info["source"].id,
            provider_id=str(match_id),
            competition_id=(db.info["friendlies"] if friendly else db.info["league"]).id,
            home_team_id=h.id,
            away_team_id=a.id,
            scheduled_at=when.replace(tzinfo=None),
            status=status,
            home_score=hs,
            away_score=as_,
            home_xg=hxg,
            away_xg=axg,
        )
    )
    db.flush()


HOME = ("9001", "Test Ev")
AWAY = ("9002", "Test Dep")
OPP = lambda n: (f"91{n:02d}", f"Rakip {n}")  # noqa: E731


def _fill_history(db, *, newest_day_home=4, newest_day_away=5, horizon_days_ago=0.5):
    """Home: lost 3 of the last 5 (0-2 H, 1-3 A, 1-2 H, 2-2 A, 3-1 H) + a friendly + older matches.
    Away: 4 wins in a row then a draw. A third-party match sets the database horizon."""
    k = KICKOFF
    d = lambda days: k - timedelta(days=days)  # noqa: E731
    _add_match(db, 5001, d(newest_day_home), HOME, OPP(1), 0, 2, 0.8, 1.9)
    _add_match(db, 5002, d(newest_day_home + 4), OPP(2), HOME, 3, 1, 2.0, 1.0)
    _add_match(db, 5003, d(newest_day_home + 7), HOME, OPP(3), 1, 2, 1.2, 1.1)
    _add_match(db, 5004, d(newest_day_home + 11), OPP(4), HOME, 2, 2, 1.0, 1.0)
    _add_match(db, 5005, d(newest_day_home + 13), HOME, OPP(5), 3, 1, 2.2, 0.5)
    _add_match(db, 5006, d(newest_day_home + 15), HOME, OPP(6), 6, 0, friendly=True)
    _add_match(db, 5007, d(newest_day_home + 20), HOME, OPP(7), 1, 0)
    for i, (gf, ga) in enumerate([(2, 0), (1, 0), (3, 1), (2, 1), (1, 1)]):
        _add_match(db, 6001 + i, d(newest_day_away + 7 * i), AWAY if i % 2 == 0 else OPP(20 + i), OPP(10 + i) if i % 2 == 0 else AWAY, gf if i % 2 == 0 else ga, ga if i % 2 == 0 else gf, 1.5, 0.7)
    # a third-party match defines the database horizon
    _add_match(db, 7001, k - timedelta(days=horizon_days_ago), OPP(30), OPP(31), 1, 0)
    db.commit()


def _lineup(prefix, n=11, lineup_type="confirmed", unavailable=(), formation="4-4-2"):
    return TeamLineup(
        formation=formation,
        lineup_type=lineup_type if n else None,
        starters=[LineupPlayer(id=f"{prefix}{i}", name=f"{prefix.upper()} Oyuncu {i}") for i in range(n)],
        unavailable=list(unavailable),
    )


def _out(name, code="injury", reason="Sakatlık", ret="Late October 2026", pid=None):
    return UnavailablePlayer(id=pid or name, name=name, reason=reason, reason_code=code, expected_return=ret)


def _centre(match_id, home_lineup, away_lineup, *, kickoff=KICKOFF, status="SCHEDULED", home=HOME, away=AWAY):
    return LiveCenterResponse(
        match_id=match_id,
        provider_match_id=match_id.replace("fotmob_", ""),
        fetched_at=KICKOFF - timedelta(hours=3),
        cache_ttl_seconds=300,
        status=status,
        kickoff=kickoff,
        competition="Test League (synthetic)",
        score=ScorePair(),
        teams=Teams(home=TeamInfo(id=home[0], name=home[1]), away=TeamInfo(id=away[0], name=away[1])),
        lineups=Lineups(home=home_lineup, away=away_lineup),
        stats=Stats(),
    )


class FakeCentre:
    """Stands in for the live-centre service: pre-built responses by route id."""

    def __init__(self, responses):
        self.responses = responses
        self.calls: list[str] = []

    async def get(self, match_id, db=None):
        self.calls.append(match_id)
        r = self.responses.get(match_id)
        if r is None:
            raise LiveCenterError("match_not_found_at_source", 404)
        if isinstance(r, Exception):
            raise r
        return r


class FakeFotMob:
    """Stands in for TeamNewsFotMobClient (no network): team pages by team id."""

    def __init__(self, pages=None, errors=None):
        self.pages = pages or {}
        self.errors = errors or {}
        self.calls: list[str] = []

    async def team(self, team_id, ttl_seconds=600.0):
        self.calls.append(str(team_id))
        if str(team_id) in self.errors:
            raise self.errors[str(team_id)]
        return FetchResult(data=self.pages[str(team_id)], raw=b"", fetched_at=KICKOFF)


def _previous_centre(match_id, team, other, team_lineup, finished=True, team_home=True):
    home, away = (team, other) if team_home else (other, team)
    home_lineup, away_lineup = (team_lineup, _lineup("zz")) if team_home else (_lineup("zz"), team_lineup)
    return _centre(match_id, home_lineup, away_lineup, kickoff=KICKOFF - timedelta(days=5), status="FINISHED" if finished else "SCHEDULED", home=home, away=away)


@pytest.fixture()
def api(monkeypatch, scratch_db, tmp_path):
    """-> (make, db): make(centre_responses, fotmob) installs a fresh service and returns a TestClient."""
    from app.main import app

    def make(responses, fotmob=None, now=KICKOFF - timedelta(hours=6), raw_dir=None):
        service = MatchPreviewService(
            live_center=FakeCentre(responses),
            fotmob_client=fotmob or FakeFotMob(),
            raw_details_dir=raw_dir or tmp_path / "raw",
            now=lambda: now,
        )
        monkeypatch.setattr(preview_service_module, "_service", service)
        app.dependency_overrides[get_db] = lambda: scratch_db
        return TestClient(app), service

    yield make
    app.dependency_overrides.pop(get_db, None)


def test_endpoint_fresh_database_builds_windows_rest_absentees_and_rotation(api, scratch_db):
    _fill_history(scratch_db)
    prev_home = _previous_centre("fotmob_5001", HOME, OPP(1), _lineup("h"))  # previous XI h0..h10
    prev_away = _previous_centre("fotmob_6001", AWAY, OPP(10), _lineup("a"))
    home_starters = _lineup("h").starters[:6] + _lineup("new", 5).starters  # 5 changes
    today_home = TeamLineup(formation="4-3-3", lineup_type="confirmed", starters=home_starters,
                            unavailable=[_out("Kilit Oyuncu", pid="h3"), _out("Cezalı Oyuncu", "suspension", "Cezalı", None), _out("Şüpheli Oyuncu", "doubtful", "Şüpheli")])
    today_away = _lineup("a", 11, "predicted")
    responses = {
        "fotmob_4242": _centre("fotmob_4242", today_home, today_away),
        "fotmob_5001": prev_home,
        "fotmob_6001": prev_away,
    }
    client, service = api(responses)
    r = client.get("/api/v1/matches/fotmob_4242/preview")
    assert r.status_code == 200, r.text
    body = r.json()
    home, away = body["home"], body["away"]
    # database was fresh -> FotMob team pages were never asked
    assert service._fotmob_client.calls == []
    assert home["history_verified"] and away["history_verified"]
    # last 5 of the home team: friendlies out, most recent first
    assert home["last5"]["results"] == "MMMBG"
    assert (home["last5"]["goals_for"], home["last5"]["goals_against"]) == (0 + 1 + 1 + 2 + 3, 2 + 3 + 2 + 2 + 1)
    assert home["last5"]["xg_matches"] == 5 and home["last5"]["xg_for"] == pytest.approx(0.8 + 1.0 + 1.2 + 1.0 + 2.2)
    assert [m["opponent"] for m in home["last5"]["matches"]] == ["Rakip 1", "Rakip 2", "Rakip 3", "Rakip 4", "Rakip 5"]
    assert home["last5"]["matches"][0]["date"].startswith("2026-10-11")
    # home venue window: home matches only
    assert [m["venue"] for m in home["venue_last5"]["matches"]] == ["home"] * 4  # 4 non-friendly home matches in the data
    assert home["venue_last5"]["results"] == "MMGG"
    assert home["venue_last5"]["missing_reason"] == "Son 5 yerine 4 maç bulundu."
    # rest: previous match 4 calendar days earlier; 3 matches (+ friendly) in the 14 days
    assert home["rest"]["rest_days"] == 4
    assert home["rest"]["matches_last_14_days"] == 3
    assert away["rest"]["rest_days"] == 5
    # absentees as FotMob sends them, plus the "started the previous match" flag
    names = {p["name"]: p for p in home["absentees"]["players"]}
    assert names["Kilit Oyuncu"]["started_previous_match"] is True
    assert names["Cezalı Oyuncu"]["started_previous_match"] is False
    assert names["Kilit Oyuncu"]["expected_return"] == "Late October 2026"
    # rotation: 5 of today's starters were not in the previous XI
    rot = home["lineup"]["rotation"]
    assert home["lineup"]["lineup_type"] == "confirmed" and home["lineup"]["formation"] == "4-3-3"
    assert rot["changes"] == 5 and rot["previous_xi_source"] == "fotmob_match_details"
    assert [p["id"] for p in rot["came_in"]] == [f"new{i}" for i in range(5)]
    assert [p["id"] for p in rot["dropped_out"]] == [f"h{i}" for i in range(6, 11)]
    assert rot["previous_match"]["opponent"] == "Rakip 1"
    # identical away XI -> zero changes (predicted line-up is flagged as such)
    assert away["lineup"]["lineup_type"] == "predicted" and away["lineup"]["rotation"]["changes"] == 0
    # highlights are template sentences with numbers
    texts = [h["text"] for h in body["highlights"]]
    assert "Test Ev geçen maça göre 5 değişiklikle sahada." in texts
    assert any("Test Ev için eksikler:" in t and "Kilit Oyuncu" in t and "Cezalı Oyuncu (cezalı)" in t for t in texts)
    assert any(t.startswith("Test Ev son 5 maçın 4'ünü kaybetti") or t.startswith("Test Ev son 5 maçın 3'ünü kaybetti") for t in texts)
    assert len(texts) <= 6
    assert body["database_latest_match_at"].startswith("2026-10-15T07:00")  # kickoff - 0.5 days
    assert any("yerel veritabanı" in s for s in body["sources"])


def test_endpoint_stale_database_is_filled_from_fotmob_team_page_with_provenance(api, scratch_db):
    # the database ends 3 days before today; the home team played 2 days ago, which only FotMob knows
    _fill_history(scratch_db, horizon_days_ago=3)
    page_home = _team_page([_fx(8101, KICKOFF - timedelta(days=2), HOME, OPP(40), 0, 3)])
    page_away = _team_page([])
    fotmob = FakeFotMob(pages={"9001": page_home, "9002": page_away})
    responses = {"fotmob_4242": _centre("fotmob_4242", _lineup("h", 0), _lineup("a", 0))}
    client, _ = api(responses, fotmob)
    body = client.get("/api/v1/matches/fotmob_4242/preview").json()
    assert sorted(fotmob.calls) == ["9001", "9002"]
    home = body["home"]
    newest = home["last5"]["matches"][0]
    assert newest["source"] == "fotmob_team_fixtures" and newest["xg_for"] is None
    assert newest["opponent"] == "Rakip 40" and (newest["goals_for"], newest["goals_against"]) == (0, 3)
    assert home["last5"]["results"] == "MMMMB"
    assert home["rest"]["rest_days"] == 2
    assert home["last5"]["xg_matches"] == 4  # the filled match has no xG: counted, not guessed
    assert any("FotMob takım sayfasından eklendi" in n for n in home["data_notes"])
    assert any("Yerel veritabanı en son" in n for n in home["data_notes"])
    assert body["away"]["data_notes"] == []  # nothing newer for the away team
    assert any("FotMob takım sayfası" in s for s in body["sources"])
    assert home["history_verified"] is True


def test_endpoint_stale_database_and_fotmob_down_flags_history_instead_of_guessing(api, scratch_db):
    _fill_history(scratch_db, horizon_days_ago=3)
    fotmob = FakeFotMob(errors={"9001": FotMobUnavailableError("down"), "9002": FotMobUnavailableError("down")})
    responses = {"fotmob_4242": _centre("fotmob_4242", _lineup("h", 0, unavailable=[_out("Tek Oyuncu")]), _lineup("a", 0))}
    client, _ = api(responses, fotmob)
    body = client.get("/api/v1/matches/fotmob_4242/preview").json()
    home = body["home"]
    assert home["history_verified"] is False
    assert home["rest"]["rest_days"] is None
    assert "doğrulanamadı" in home["rest"]["missing_reason"] and "eksik olabilir" in home["rest"]["missing_reason"]
    assert home["last5"]["missing_reason"] == home["rest"]["missing_reason"]
    assert home["last5"]["results"] is not None  # the matches we do have are still shown
    kinds = {h["kind"] for h in body["highlights"]}
    assert kinds <= {"absentees", "doubtful", "rotation"}  # no form / goals / rest sentence from a possibly stale history
    assert any("Tek Oyuncu" in h["text"] for h in body["highlights"])


def test_endpoint_fresh_database_with_fotmob_down_stays_verified(api, scratch_db):
    """A team with no recent local match would be checked; a fully current database needs no check."""
    _fill_history(scratch_db, horizon_days_ago=0.2)
    fotmob = FakeFotMob(errors={"9001": FotMobUnavailableError("down"), "9002": FotMobUnavailableError("down")})
    client, _ = api({"fotmob_4242": _centre("fotmob_4242", _lineup("h", 0), _lineup("a", 0))}, fotmob)
    body = client.get("/api/v1/matches/fotmob_4242/preview").json()
    # home has 5+ competitive matches, newest 4 days ago, database current -> no FotMob call at all
    assert fotmob.calls == [] and body["home"]["history_verified"] is True and body["away"]["history_verified"] is True


def test_endpoint_team_without_history_has_null_values_and_reasons(api, scratch_db):
    scratch_db.flush()
    _fill_history(scratch_db)
    unknown = ("9777", "Test Bilinmeyen")
    centre = _centre("fotmob_4242", _lineup("h", 0), _lineup("u", 0), away=unknown)
    fotmob = FakeFotMob(pages={"9777": _team_page([])})
    client, _ = api({"fotmob_4242": centre}, fotmob)
    away = client.get("/api/v1/matches/fotmob_4242/preview").json()["away"]
    assert away["last5"]["played"] == 0 and away["last5"]["results"] is None and away["last5"]["goals_for"] is None
    assert away["last5"]["missing_reason"] == "Bu takım için kayıtlı maç bulunamadı."
    assert away["venue_last5"]["missing_reason"] == "Bu takım için deplasmanda kayıtlı maç bulunamadı."
    assert away["last5"]["xg_for"] is None and away["last5"]["xg_matches"] == 0
    assert away["rest"]["rest_days"] is None and away["rest"]["missing_reason"] == "Önceki maç kaydı bulunamadı."
    assert away["history_verified"] is True  # FotMob confirmed there is nothing


def test_endpoint_missing_lineup_and_availability_are_explicit(api, scratch_db):
    _fill_history(scratch_db)
    empty = TeamLineup()  # FotMob sent nothing for the team
    last11 = _lineup("a", 11, "last_starting11")
    client, _ = api({"fotmob_4242": _centre("fotmob_4242", empty, last11)})
    body = client.get("/api/v1/matches/fotmob_4242/preview").json()
    home, away = body["home"], body["away"]
    assert home["absentees"]["available"] is False and home["absentees"]["players"] == []
    assert "göndermedi" in home["absentees"]["missing_reason"]
    assert home["lineup"]["lineup_type"] is None and home["lineup"]["starters_count"] == 0
    assert home["lineup"]["missing_reason"] == "Kadro henüz açıklanmadı."
    assert home["lineup"]["rotation"]["changes"] is None
    # FotMob's "last starting XI" is not today's line-up: no rotation figure, and it says why
    assert away["lineup"]["lineup_type"] == "last_starting11"
    assert away["lineup"]["rotation"]["changes"] is None
    assert "değişiklik sayısı hesaplanamadı" in away["lineup"]["rotation"]["missing_reason"]
    assert away["absentees"]["available"] is True and away["absentees"]["players"] == []  # a line-up came, nobody is listed


def test_endpoint_rotation_reads_the_local_raw_archive_before_asking_fotmob(api, scratch_db, tmp_path):
    _fill_history(scratch_db)
    raw = tmp_path / "raw"
    raw.mkdir()
    # synthetic FotMob matchDetails body of the home team's previous match (id 5001), finished
    def starters(prefix):
        return [{"id": f"{prefix}{i}", "name": f"{prefix.upper()} Oyuncu {i}", "positionId": 1 if i == 0 else 40, "shirtNumber": i + 1} for i in range(11)]

    body = {
        "general": {"matchId": "5001", "matchTimeUTCDate": (KICKOFF - timedelta(days=4)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "homeTeam": {"id": 9001, "name": "Test Ev"}, "awayTeam": {"id": 9101, "name": "Rakip 1"}, "started": True, "finished": True},
        "header": {"teams": [{"id": 9001, "name": "Test Ev", "score": 0}, {"id": 9101, "name": "Rakip 1", "score": 2}],
                   "status": {"utcTime": "x", "started": True, "finished": True, "cancelled": False}},
        "content": {"lineup": {"lineupType": "standard", "homeTeam": {"formation": "4-4-2", "starters": starters("h"), "subs": []},
                               "awayTeam": {"formation": "4-4-2", "starters": starters("r"), "subs": []}}},
    }
    with gzip.open(raw / "5001.json.gz", "wt", encoding="utf-8") as fh:
        json.dump(body, fh)
    today = TeamLineup(formation="4-4-2", lineup_type="confirmed", starters=_lineup("h").starters[:9] + _lineup("n", 2).starters)
    client, service = api({"fotmob_4242": _centre("fotmob_4242", today, _lineup("a", 0))}, raw_dir=raw)
    home = client.get("/api/v1/matches/fotmob_4242/preview").json()["home"]
    assert home["lineup"]["rotation"]["changes"] == 2
    assert home["lineup"]["rotation"]["previous_xi_source"] == "local_raw_cache"
    assert service._live_center.calls == ["fotmob_4242"]  # the previous match never went to the live centre


def test_endpoint_rotation_missing_reasons(api, scratch_db):
    _fill_history(scratch_db)
    today = TeamLineup(formation="4-4-2", lineup_type="confirmed", starters=_lineup("h").starters)
    # previous match unavailable at FotMob -> reason, no number
    client, _ = api({"fotmob_4242": _centre("fotmob_4242", today, _lineup("a", 0))})
    rot = client.get("/api/v1/matches/fotmob_4242/preview").json()["home"]["lineup"]["rotation"]
    assert rot["changes"] is None
    assert rot["missing_reason"].startswith("Önceki maçın ilk 11'i alınamadı")
    # previous match not finished -> reason
    unfinished = _previous_centre("fotmob_5001", HOME, OPP(1), _lineup("h"), finished=False)
    client, _ = api({"fotmob_4242": _centre("fotmob_4242", today, _lineup("a", 0)), "fotmob_5001": unfinished})
    rot = client.get("/api/v1/matches/fotmob_4242/preview").json()["home"]["lineup"]["rotation"]
    assert rot["changes"] is None and "bitmemiş" in rot["missing_reason"]
    # incomplete previous XI -> reason names the count
    short_prev = _previous_centre("fotmob_5001", HOME, OPP(1), _lineup("h", 9))
    client, _ = api({"fotmob_4242": _centre("fotmob_4242", today, _lineup("a", 0)), "fotmob_5001": short_prev})
    rot = client.get("/api/v1/matches/fotmob_4242/preview").json()["home"]["lineup"]["rotation"]
    assert rot["changes"] is None and "ilk 11'i eksik (9 oyuncu)" in rot["missing_reason"]


def test_endpoint_maps_errors_and_missing_teams(api, scratch_db):
    client, _ = api({"fotmob_1": LiveCenterError("source_unavailable", 503), "fotmob_2": LiveCenterError("unknown_match_id", 404)})
    r = client.get("/api/v1/matches/fotmob_1/preview")
    assert r.status_code == 503 and r.json()["detail"]["error"] == "source_unavailable"
    r = client.get("/api/v1/matches/fotmob_2/preview")
    assert r.status_code == 404 and r.json()["detail"]["error"] == "unknown_match_id"
    nameless = _centre("fotmob_3", _lineup("h", 0), _lineup("a", 0), home=("", "x"))
    client, _ = api({"fotmob_3": nameless})
    r = client.get("/api/v1/matches/fotmob_3/preview")
    assert r.status_code == 503 and r.json()["detail"]["error"] == "teams_unknown"


def test_preview_is_cached_and_concurrent_callers_share_one_build(scratch_db):
    _fill_history(scratch_db)
    centre = FakeCentre({"fotmob_4242": _centre("fotmob_4242", _lineup("h", 0), _lineup("a", 0))})
    clock = [100.0]
    service = MatchPreviewService(live_center=centre, fotmob_client=FakeFotMob(), now=lambda: KICKOFF - timedelta(hours=6),
                                  clock=lambda: clock[0], cache_seconds=300)

    async def run():
        return await asyncio.gather(*(service.get("fotmob_4242", scratch_db) for _ in range(4)))

    results = asyncio.run(run())
    assert centre.calls.count("fotmob_4242") == 1 and all(r is results[0] for r in results)
    asyncio.run(service.get("fotmob_4242", scratch_db))
    assert centre.calls.count("fotmob_4242") == 1  # served from the cache
    clock[0] += 301
    asyncio.run(service.get("fotmob_4242", scratch_db))
    assert centre.calls.count("fotmob_4242") == 2  # expired -> rebuilt


def test_response_never_contains_a_zero_for_unknown_numbers(api, scratch_db):
    """Missing xG / rest must be null, never 0."""
    _fill_history(scratch_db)
    # a team whose matches have no xG at all
    for i, day in enumerate((3, 8, 12, 17, 22)):
        _add_match(scratch_db, 8200 + i, KICKOFF - timedelta(days=day), ("9003", "Test Xg"), OPP(50 + i), 1, 0)
    scratch_db.commit()
    centre = _centre("fotmob_4242", _lineup("h", 0), _lineup("x", 0), away=("9003", "Test Xg"))
    client, _ = api({"fotmob_4242": centre})
    away = client.get("/api/v1/matches/fotmob_4242/preview").json()["away"]
    assert away["last5"]["xg_for"] is None and away["last5"]["xg_against"] is None
    assert away["last5"]["xg_matches"] == 0 and away["last5"]["xg_missing_reason"] == "Bu maçlar için xG verisi yok."
    assert away["rest"]["rest_days"] == 3
