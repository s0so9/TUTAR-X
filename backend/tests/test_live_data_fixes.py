"""Tests for live-data fixes: FotMob clock parsing, live id normalisation and
the stale-status refresh of GET /api/v1/matches/{match_id}.

All FotMob payloads below are hand-written fixtures shaped like FotMob's
responses (test data, not real match data). No network access.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.domain.enums import MatchOutcome, MatchStatus
from app.domain.match import Match
from app.providers.cache import ProviderCache
from app.providers.fotmob import FotMobFootballProvider, _parse_live_clock
from app.providers.models import ProviderLiveMatch, ProviderMatch

LRM = "‎"
KICKOFF = datetime(2026, 10, 13, 16, 45, tzinfo=timezone.utc)


def _provider() -> FotMobFootballProvider:
    return FotMobFootballProvider(base_url="https://fotmob.test", cache=None)


def _list_item(short=None, started=True, finished=False, reason=None, **extra):
    """FotMob day-list match item (TEST FIXTURE)."""
    status = {
        "utcTime": "2026-10-13T16:45:00.000Z",
        "started": started,
        "finished": finished,
        "cancelled": False,
    }
    if short is not None:
        status["liveTime"] = {"short": short, "long": "", "addedTime": 0}
    if reason is not None:
        status["reason"] = reason
    item = {
        "id": 900001,
        "leagueId": 943230,
        "home": {"id": 101, "score": 1, "name": "Test Home", "longName": "Test Home"},
        "away": {"id": 202, "score": 0, "name": "Test Away", "longName": "Test Away"},
        "status": status,
    }
    item.update(extra)
    return item


def _details(short=None, started=True, finished=False, reason=None):
    """FotMob matchDetails payload: status only under header.status (TEST FIXTURE)."""
    status = {"utcTime": "2026-10-13T16:45:00.000Z", "started": started, "finished": finished, "cancelled": False}
    if short is not None:
        status["liveTime"] = {"short": short, "long": "", "addedTime": 0}
    if reason is not None:
        status["reason"] = reason
    return {
        "general": {
            "matchId": "900001",
            "leagueId": 943230,
            "leagueName": "Test League",
            "matchTimeUTCDate": "2026-10-13T16:45:00.000Z",
            "homeTeam": {"name": "Test Home", "id": 101},
            "awayTeam": {"name": "Test Away", "id": 202},
        },
        "header": {
            "teams": [{"name": "Test Home", "id": 101, "score": 2}, {"name": "Test Away", "id": 202, "score": 1}],
            "status": status,
        },
    }


# --- liveTime parsing ----------------------------------------------------

@pytest.mark.parametrize(
    "short, expected",
    [
        (f"23{LRM}’{LRM}", (23, None, False)),
        ("45+2’", (45, 2, False)),
        (f"90{LRM}+{LRM}5{LRM}’", (90, 5, False)),
        ("105+1'", (105, 1, False)),
        ("HT", (None, None, True)),
        ("Pen", (None, None, False)),
        ("", (None, None, False)),
    ],
)
def test_parse_live_clock(short, expected):
    assert _parse_live_clock({"liveTime": {"short": short}}) == expected


def test_parse_live_clock_missing_is_unknown():
    assert _parse_live_clock({}) == (None, None, False)
    assert _parse_live_clock({"liveTime": None}) == (None, None, False)
    assert _parse_live_clock(None) == (None, None, False)


def test_list_item_live_minute_from_live_time():
    m = _provider()._normalize_match(_list_item(f"23{LRM}’{LRM}"))
    assert m.status == MatchStatus.LIVE
    assert m.minute == 23
    assert m.added_time is None
    assert (m.home_score, m.away_score) == (1, 0)


def test_list_item_stoppage_time():
    m = _provider()._normalize_match(_list_item("45+2’"))
    assert (m.minute, m.added_time) == (45, 2)


def test_list_item_half_time():
    m = _provider()._normalize_match(_list_item("HT"))
    assert m.status == MatchStatus.HALF_TIME
    assert m.minute is None
    assert m.is_live is True


def test_explicit_minute_field_still_wins():
    m = _provider()._normalize_match(_list_item("71’", minute=70))
    assert m.minute == 70


def test_scheduled_and_finished_have_no_minute():
    p = _provider()
    scheduled = p._normalize_match(_list_item(None, started=False))
    assert scheduled.status == MatchStatus.SCHEDULED and scheduled.minute is None
    finished = p._normalize_match(
        _list_item(None, finished=True, reason={"short": "FT", "shortKey": "fulltime_short"})
    )
    assert finished.status == MatchStatus.FINISHED and finished.minute is None
    assert finished.outcome == MatchOutcome.HOME_WIN


def test_match_details_status_read_from_header():
    p = _provider()
    live = p._normalize_match(_details(f"67{LRM}’{LRM}"))
    assert live.status == MatchStatus.LIVE
    assert live.minute == 67
    assert (live.home_score, live.away_score) == (2, 1)
    finished = p._normalize_match(
        _details(None, finished=True, reason={"short": "FT", "shortKey": "fulltime_short"})
    )
    assert finished.status == MatchStatus.FINISHED
    assert finished.outcome == MatchOutcome.HOME_WIN
    scheduled = p._normalize_match(_details(None, started=False))
    assert scheduled.status == MatchStatus.SCHEDULED


@pytest.mark.asyncio
async def test_espn_live_path_parses_live_time():
    """FotMob.get_live_matches (ESPN cross-reference) reads liveTime too."""
    p = _provider()
    espn = {"events": [{"name": "Test Away at Test Home", "status": {"type": {"state": "in"}}}]}
    p._client.get = AsyncMock(return_value=httpx.Response(200, json=espn))
    p._request = AsyncMock(return_value={"leagues": [{"id": 943230, "primaryId": 42, "matches": [_list_item("45+3’")]}]})
    matches = await p.get_live_matches()
    assert len(matches) == 1
    assert (matches[0].minute, matches[0].added_time) == (45, 3)
    assert matches[0].status == MatchStatus.LIVE

    p._request = AsyncMock(return_value={"leagues": [{"id": 943230, "primaryId": 42, "matches": [_list_item("HT")]}]})
    matches = await p.get_live_matches()
    assert matches[0].status == MatchStatus.HALF_TIME
    assert matches[0].minute is None


# --- live endpoint: id normalisation, league filter, shared cache --------

def test_normalize_live_match_id():
    from app.api.v1.endpoints.live_matches import _normalize_live_match_id

    assert _normalize_live_match_id("6106414", "fotmob") == "fotmob_6106414"
    assert _normalize_live_match_id("fotmob_6106414", "fotmob") == "fotmob_6106414"
    assert _normalize_live_match_id(6106414, "fotmob") == "fotmob_6106414"
    assert _normalize_live_match_id("abc", "unknown_provider") == "abc"
    assert _normalize_live_match_id("abc", None) == "abc"


def _live(match_id, competition_id, minute=12):
    now = datetime.now(timezone.utc)
    return ProviderLiveMatch(
        provider="fotmob", source_id=match_id, fetched_at=now, match_id=match_id,
        status=MatchStatus.LIVE, minute=minute, home_score=1, away_score=0,
        home_team_id="101", away_team_id="202", home_team_name="Test Home",
        away_team_name="Test Away", competition_id=competition_id, last_updated=now,
    )


def _day(source_id, competition_id, status=MatchStatus.LIVE, minute=12):
    return ProviderMatch(
        provider="fotmob", source_id=source_id, fetched_at=datetime.now(timezone.utc),
        competition_id=competition_id, home_team_id="101", home_team_name="Test Home",
        away_team_id="202", away_team_name="Test Away", scheduled_at=KICKOFF,
        status=status, minute=minute, home_score=1, away_score=0,
    )


@pytest.fixture
def shared_cache():
    from app.main import app_state

    previous = app_state.provider_cache
    app_state.provider_cache = ProviderCache()
    yield app_state.provider_cache
    app_state.provider_cache = previous


@pytest.mark.asyncio
async def test_live_endpoint_prefixes_ids_and_filters_by_parent_league(shared_cache):
    from app.api.v1.endpoints import live_matches

    live = [_live("6106414", "943230"), _live("5795468", "47")]
    day = [_day("6106414", "42"), _day("5795468", "47")]
    with patch.object(live_matches.ProviderManager, "get_live_matches",
                      AsyncMock(return_value=(live, {"selected_provider": "fotmob"}))), \
         patch.object(live_matches.FotMobFootballProvider, "get_matches_by_date",
                      AsyncMock(return_value=day)), \
         patch.object(live_matches.ProviderHealthService, "check_all",
                      AsyncMock(return_value={})) as check_all:
        unfiltered = await live_matches.get_live_matches(league_id=None, include_stats=False)
        filtered = await live_matches.get_live_matches(league_id="42", include_stats=False)

    assert [m.match_id for m in unfiltered.matches] == ["fotmob_6106414", "fotmob_5795468"]
    assert [m.match_id for m in filtered.matches] == ["fotmob_6106414"]
    assert filtered.provider_used == "fotmob"
    assert filtered.matches[0].minute == 12
    # Provider health is probed once and then served from the shared cache.
    assert check_all.await_count == 1


@pytest.mark.asyncio
async def test_live_endpoint_daily_list_fallback_ids(shared_cache):
    from app.api.v1.endpoints import live_matches

    day = [_day("6106414", "42", minute=None), _day("6106424", "42", status=MatchStatus.HALF_TIME)]
    day[0] = day[0].model_copy(update={"minute": 31, "added_time": None})
    with patch.object(live_matches.ProviderManager, "get_live_matches",
                      AsyncMock(return_value=([], {"selected_provider": None}))), \
         patch.object(live_matches.FotMobFootballProvider, "get_matches_by_date",
                      AsyncMock(return_value=day)), \
         patch.object(live_matches.ProviderHealthService, "check_all",
                      AsyncMock(return_value={})):
        resp = await live_matches.get_live_matches(league_id="42", include_stats=False)

    assert resp.provider_used == "fotmob_daily_list"
    assert [(m.match_id, m.status, m.minute) for m in resp.matches] == [
        ("fotmob_6106414", "LIVE", 31),
        ("fotmob_6106424", "HALF_TIME", 12),
    ]


def test_live_endpoint_uses_shared_cache(shared_cache):
    from app.api.v1.endpoints.live_matches import _shared_provider_cache

    assert _shared_provider_cache() is shared_cache


# --- GET /matches/{id}: stale status refresh ------------------------------

@pytest.fixture(autouse=True)
def _clear_refresh_memo():
    from app.api.v1.endpoints import matches

    matches._live_refresh_memo.clear()
    yield
    matches._live_refresh_memo.clear()


def _cached_match(status=MatchStatus.SCHEDULED, kickoff=KICKOFF, match_id="fotmob_900001"):
    return Match(
        id=match_id, competition_id="42", season_id="test_season",
        home_team_id="home-uuid", away_team_id="away-uuid", scheduled_at=kickoff,
        status=status, home_score=0, away_score=0,
    )


def _fresh(status=MatchStatus.LIVE, home=1, away=0, minute=23, added=None, outcome=None):
    return SimpleNamespace(
        source_id="900001", status=status, home_score=home, away_score=away,
        minute=minute, added_time=added, outcome=outcome,
        fetched_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_refresh_updates_stale_scheduled_match(shared_cache):
    from app.api.v1.endpoints.matches import _refresh_stale_live_status

    fetch = AsyncMock(return_value=_fresh(added=2, minute=45))
    match = await _refresh_stale_live_status(
        "fotmob_900001", _cached_match(), fetch=fetch, now=KICKOFF + timedelta(minutes=50)
    )
    fetch.assert_awaited_once_with("900001")
    assert match.status == MatchStatus.LIVE
    assert (match.home_score, match.away_score, match.minute, match.added_time) == (1, 0, 45, 2)
    assert match.home_team_id == "home-uuid"  # untouched fields are preserved
    # The fresh state is shared with other readers of the provider cache.
    assert shared_cache.get("fotmob:match:900001") is fetch.return_value


@pytest.mark.asyncio
async def test_refresh_picks_up_full_time():
    from app.api.v1.endpoints.matches import _refresh_stale_live_status

    fresh = _fresh(status=MatchStatus.FINISHED, home=2, away=1, minute=None, outcome=MatchOutcome.HOME_WIN)
    match = await _refresh_stale_live_status(
        "fotmob_900001", _cached_match(MatchStatus.LIVE), fetch=AsyncMock(return_value=fresh),
        now=KICKOFF + timedelta(minutes=115),
    )
    assert match.status == MatchStatus.FINISHED
    assert (match.home_score, match.away_score, match.minute) == (2, 1, None)
    assert match.outcome == MatchOutcome.HOME_WIN


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "match_id, status, now",
    [
        ("fotmob_900001", MatchStatus.SCHEDULED, KICKOFF - timedelta(minutes=5)),   # not kicked off
        ("fotmob_900001", MatchStatus.LIVE, KICKOFF + timedelta(hours=4, minutes=1)),  # outside window
        ("fotmob_900001", MatchStatus.FINISHED, KICKOFF + timedelta(minutes=30)),  # final already
        ("ryzellx_900001", MatchStatus.SCHEDULED, KICKOFF + timedelta(minutes=30)),  # other provider
    ],
)
async def test_refresh_skipped_outside_conditions(match_id, status, now):
    from app.api.v1.endpoints.matches import _refresh_stale_live_status

    fetch = AsyncMock(return_value=_fresh())
    match = await _refresh_stale_live_status(match_id, _cached_match(status, match_id=match_id), fetch=fetch, now=now)
    fetch.assert_not_awaited()
    assert match.status == status


@pytest.mark.asyncio
async def test_refresh_fails_soft_and_keeps_cached_data():
    from app.api.v1.endpoints.matches import _refresh_stale_live_status

    fetch = AsyncMock(side_effect=RuntimeError("network down"))
    match = await _refresh_stale_live_status(
        "fotmob_900001", _cached_match(), fetch=fetch, now=KICKOFF + timedelta(minutes=10)
    )
    assert match.status == MatchStatus.SCHEDULED
    assert (match.home_score, match.away_score, match.minute) == (0, 0, None)


@pytest.mark.asyncio
async def test_refresh_is_memoised_between_polls():
    from app.api.v1.endpoints.matches import _refresh_stale_live_status

    fetch = AsyncMock(return_value=_fresh())
    now = KICKOFF + timedelta(minutes=10)
    first = await _refresh_stale_live_status("fotmob_900001", _cached_match(), fetch=fetch, now=now)
    second = await _refresh_stale_live_status("fotmob_900001", _cached_match(), fetch=fetch, now=now)
    assert fetch.await_count == 1
    assert first.status == second.status == MatchStatus.LIVE
    assert second.minute == 23


@pytest.mark.asyncio
async def test_get_match_endpoint_applies_refresh():
    """The endpoint wires the refresh in before building the response."""
    from app.api.v1.endpoints import matches

    started = datetime.now(timezone.utc) - timedelta(minutes=20)
    provider = MagicMock()
    provider.get_match.return_value = _cached_match(kickoff=started)
    provider.get_team.return_value = None
    provider.get_team_match_statistics.return_value = []
    provider.is_development_data.return_value = False
    fresh = _provider()._normalize_match(_details(f"20{LRM}’{LRM}"))

    with patch.object(matches, "_fetch_fresh_fotmob_match", AsyncMock(return_value=fresh)):
        resp = await matches.get_match("fotmob_900001", provider=provider)

    assert resp.match.status == MatchStatus.LIVE
    assert (resp.match.home_score, resp.match.away_score, resp.match.minute) == (2, 1, 20)


@pytest.mark.asyncio
async def test_provider_health_served_stale_while_refreshing():
    """An expired health result is returned at once; one probe refreshes it."""
    import asyncio
    from app.api.v1.endpoints import live_matches

    cache = ProviderCache()
    stale = {"fotmob": {"availability_code": "AVAILABLE", "last_check_utc": "2026-10-13T16:00:00"}}
    cache.set(live_matches._PROVIDER_HEALTH_LAST_KNOWN_KEY, stale, ttl_seconds=600)

    release = asyncio.Event()

    async def slow_check_all():
        await release.wait()
        return {}

    service = MagicMock()
    service.check_all = AsyncMock(side_effect=slow_check_all)

    first = await live_matches._cached_provider_health(service, cache)
    second = await live_matches._cached_provider_health(service, cache)
    assert first is stale and second is stale  # did not wait for the probe

    release.set()
    await live_matches._provider_health_refresh
    assert service.check_all.await_count == 1  # one background probe only
    assert cache.get(live_matches._PROVIDER_HEALTH_CACHE_KEY) == {}
