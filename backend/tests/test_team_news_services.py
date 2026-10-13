"""Store, apply_*, async services (mock transport, no network) and the read model.

All payloads are SYNTHETIC (tests/test_team_news_fixtures.py); no real data.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.models import (
    Base,
    Competition,
    LineupSnapshot,
    Match,
    Player,
    PlayerAvailability,
    PlayerMatchStat,
    ProviderSource,
    Team,
    TeamNewsMatch,
    TeamSquadMember,
)
from app.domain.enums import MatchStatus
from app.services.team_news.builder import TeamNewsNotFound, build_team_news, build_team_squad
from app.services.team_news.fotmob_client import (
    FotMobBlockedError,
    FotMobRateLimitedError,
    FotMobUnavailableError,
    TeamNewsFotMobClient,
)
from app.services.team_news.raw_store import RawStore
from app.services.team_news.service import (
    MatchRef,
    TeamNewsService,
    apply_match_payload,
    apply_player_payload,
    apply_team_payload,
    needs_finished_ingest,
)
from app.services.team_news.store import TeamNewsStore, as_utc
from tests.test_team_news_fixtures import (
    SYN_AWAY_TEAM,
    SYN_HOME_TEAM,
    syn_player_id,
    synthetic_injury,
    synthetic_league_payload,
    synthetic_match_payload,
    synthetic_player_payload,
    synthetic_team_payload,
)

UTC = timezone.utc
T0 = datetime(2026, 10, 13, 18, 0, tzinfo=UTC)
HP = lambda n: syn_player_id(SYN_HOME_TEAM, n)  # noqa: E731
AP = lambda n: syn_player_id(SYN_AWAY_TEAM, n)  # noqa: E731


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


def seed_base(session, *, extra_teams=(990003, 990004)):
    src = ProviderSource(name="fotmob", is_active=True)
    session.add(src)
    session.flush()
    comp = Competition(provider_source_id=src.id, provider_id="47", name="Synthetic League")
    session.add(comp)
    teams = {}
    for pid in (SYN_HOME_TEAM, SYN_AWAY_TEAM, *extra_teams):
        t = Team(provider_source_id=src.id, provider_id=str(pid), name=f"Synthetic FC {pid}")
        session.add(t)
        teams[pid] = t
    session.flush()
    return src, comp, teams


def add_match(session, src, comp, teams, provider_id, home, away, when, hs, as_, hxg=None, axg=None):
    m = Match(
        provider_source_id=src.id,
        provider_id=str(provider_id),
        competition_id=comp.id,
        home_team_id=teams[home].id,
        away_team_id=teams[away].id,
        scheduled_at=when,
        status=MatchStatus.FINISHED,
        home_score=hs,
        away_score=as_,
        home_xg=hxg,
        away_xg=axg,
    )
    session.add(m)
    session.flush()
    return m


# =========================================================================== squads / availability


def test_squad_apply_clear_supersede_and_idempotency(session_factory):
    with session_factory() as s:
        seed_base(s)
        store = TeamNewsStore(s)
        c1 = apply_team_payload(
            store, synthetic_team_payload(injured={2: ("45", "Late October 2026"), 7: ("30", "Unknown")}), T0
        )
        s.commit()
        assert c1["members"] == 14 and c1["injured"] == 2 and c1["availability_inserted"] == 2
        assert s.scalar(select(func.count()).select_from(TeamSquadMember)) == 14
        p2 = s.execute(select(Player).where(Player.provider_id == str(HP(2)))).scalar_one()
        assert p2.team_provider_id == str(SYN_HOME_TEAM) and p2.team_id is not None
        assert p2.market_value_eur == 2_000_000 and p2.market_value_as_of is None
        assert p2.market_value_source == "fotmob_team_squad"

        # same observation again -> idempotent
        c_again = apply_team_payload(
            TeamNewsStore(s), synthetic_team_payload(injured={2: ("45", "Late October 2026"), 7: ("30", "Unknown")}), T0
        )
        s.commit()
        assert c_again["availability_inserted"] == 0 and c_again["availability_confirmed"] == 2
        assert s.scalar(select(func.count()).select_from(PlayerAvailability)) == 2

        # 6 h later: player 7 recovered, player 2 has a new expected return
        t1 = T0 + timedelta(hours=6)
        c2 = apply_team_payload(TeamNewsStore(s), synthetic_team_payload(injured={2: ("45", "Early November 2026")}), t1)
        s.commit()
        assert c2["availability_cleared"] == 1 and c2["availability_superseded"] == 1
        assert c2["availability_inserted"] == 1
        rows = s.execute(select(PlayerAvailability).order_by(PlayerAvailability.first_observed_at)).scalars().all()
        assert len(rows) == 3  # history kept, nothing deleted
        by = {(r.player_provider_id, r.expected_return): r for r in rows}
        assert by[(str(HP(7)), "Unknown")].cleared_reason == "not_listed"
        assert as_utc(by[(str(HP(7)), "Unknown")].cleared_at) == t1
        assert by[(str(HP(2)), "Late October 2026")].cleared_reason == "superseded"
        assert by[(str(HP(2)), "Early November 2026")].cleared_at is None

        # an older observation arriving late is ignored
        c_old = apply_team_payload(TeamNewsStore(s), synthetic_team_payload(injured={}), T0 + timedelta(hours=1))
        s.commit()
        assert c_old["availability_stale"] == 1
        assert s.scalar(select(func.count()).select_from(PlayerAvailability).where(PlayerAvailability.cleared_at.is_(None))) == 1
        member = s.execute(select(TeamSquadMember).where(TeamSquadMember.player_provider_id == str(HP(1)))).scalar_one()
        assert as_utc(member.first_seen_at) == T0 and as_utc(member.last_seen_at) == t1


def test_player_profile_merge_and_injury_lifecycle(session_factory):
    with session_factory() as s:
        seed_base(s)
        apply_team_payload(TeamNewsStore(s), synthetic_team_payload(), T0)
        s.commit()
        pid = HP(3)
        t1 = T0 + timedelta(hours=1)
        c = apply_player_payload(TeamNewsStore(s), synthetic_player_payload(pid, injury=synthetic_injury()), t1)
        s.commit()
        assert c["availability_inserted"] == 1
        p = s.execute(select(Player).where(Player.provider_id == str(pid))).scalar_one()
        assert (p.primary_position, p.preferred_foot, p.contract_end, p.height_cm) == ("Center Back", "left", "2030-06-30", 190)
        assert p.market_value_eur == 6_000_000 and as_utc(p.market_value_as_of) == datetime(2026, 10, 1, tzinfo=UTC)
        assert p.market_value_source == "fotmob_player_profile" and p.profile_source == "fotmob_player_profile"
        assert p.shirt_number == 4  # profile (newer) overrides the squad shirt 3
        # an older lineup observation only fills NULL fields
        older = apply_match_payload(TeamNewsStore(s), synthetic_match_payload(6200001, kickoff="2026-10-01T19:00:00Z", status="scheduled"), T0 - timedelta(days=12))
        s.commit()
        p = s.execute(select(Player).where(Player.provider_id == str(pid))).scalar_one()
        assert p.shirt_number == 4 and p.profile_source == "fotmob_player_profile"
        # injury gone in a later profile -> cleared, never deleted
        t2 = t1 + timedelta(days=1)
        c2 = apply_player_payload(TeamNewsStore(s), synthetic_player_payload(pid, injury=None), t2)
        s.commit()
        assert c2["availability_cleared"] == 1
        r = s.execute(select(PlayerAvailability).where(PlayerAvailability.source == "fotmob_player_profile")).scalar_one()
        assert r.reason == "Synthetic knock" and r.injury_id == "45" and as_utc(r.cleared_at) == t2
        # keys absent -> the profile cannot confirm/clear anything
        payload = synthetic_player_payload(pid, include_injury_key=False)
        payload.pop("internationalDuty")
        c3 = apply_player_payload(TeamNewsStore(s), payload, t2 + timedelta(hours=1))
        assert not any(k.startswith("availability_") for k in c3)
        assert older["status"] == "scheduled"
        # a newer squad observation updates fields but keeps the best-ranked source bookkeeping
        apply_team_payload(TeamNewsStore(s), synthetic_team_payload(), t2 + timedelta(hours=2))
        s.commit()
        p = s.execute(select(Player).where(Player.provider_id == str(pid))).scalar_one()
        assert p.shirt_number == 3  # squad (newest) value
        assert p.profile_source == "fotmob_player_profile" and as_utc(p.profile_observed_at) == t2 + timedelta(hours=1)


# =========================================================================== matches


def test_prematch_snapshots_and_match_unavailable(session_factory):
    with session_factory() as s:
        seed_base(s)
        mid = 6300001
        base = dict(kickoff="2026-10-14T19:00:00.000Z", unavailable={"home": [(2, "injury", "Late October 2026")], "away": None})
        c1 = apply_match_payload(TeamNewsStore(s), synthetic_match_payload(mid, **base), T0)
        s.commit()
        assert c1["snapshots_created"] == 2 and c1["home_unavailable_inserted"] == 1
        assert "away_unavailable_inserted" not in c1  # away list not sent
        reg = s.execute(select(TeamNewsMatch)).scalar_one()
        assert reg.home_team_provider_id == str(SYN_HOME_TEAM) and as_utc(reg.home_unavailable_observed_at) == T0
        assert reg.away_unavailable_observed_at is None and reg.source_status == "scheduled"

        # identical content 15 min later -> no new snapshot, last_observed_at moves
        t1 = T0 + timedelta(minutes=15)
        c2 = apply_match_payload(TeamNewsStore(s), synthetic_match_payload(mid, **base), t1)
        s.commit()
        assert c2["snapshots_created"] == 0
        snaps = s.execute(select(LineupSnapshot).where(LineupSnapshot.side == "home")).scalars().all()
        assert len(snaps) == 1 and as_utc(snaps[0].last_observed_at) == t1 and as_utc(snaps[0].observed_at) == T0

        # confirmed XI (different starter, lineupType standard, bench) + empty home list
        t2 = T0 + timedelta(minutes=30)
        starters = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 13]
        c3 = apply_match_payload(
            TeamNewsStore(s),
            synthetic_match_payload(mid, kickoff=base["kickoff"], lineup_type="standard", home_starters=starters,
                                    with_bench=True, unavailable={"home": [], "away": []}),
            t2,
        )
        s.commit()
        assert c3["snapshots_created"] == 2 and c3["home_unavailable_cleared"] == 1
        latest = s.execute(
            select(LineupSnapshot).where(LineupSnapshot.side == "home").order_by(LineupSnapshot.observed_at.desc())
        ).scalars().first()
        assert latest.lineup_type == "standard" and latest.starter_ids[-1] == HP(13) and latest.bench is not None
        assert latest.timestamp_basis == "observed"


def test_finished_match_stats_upsert_rules(session_factory):
    with session_factory() as s:
        src, comp, teams = seed_base(s)
        add_match(s, src, comp, teams, 6400001, SYN_HOME_TEAM, SYN_AWAY_TEAM, datetime(2026, 10, 4, 15, tzinfo=UTC), 2, 1, 1.9, 0.7)
        payload = synthetic_match_payload(
            6400001, kickoff="2026-10-04T15:00:00.000Z", status="finished", lineup_type="standard",
            home_score=2, away_score=1, with_bench=True,
            unavailable={"home": [(14, "injury", "Unknown")], "away": []},
            stats={HP(9): {"minutes": 90, "rating": 7.5, "goals": 2, "xg": 1.2, "shotmap": 3}},
        )
        fetched = datetime(2026, 10, 4, 18, tzinfo=UTC)
        c = apply_match_payload(TeamNewsStore(s), payload, fetched)
        s.commit()
        assert c["stats_inserted"] == 28
        row = s.execute(select(PlayerMatchStat).where(PlayerMatchStat.player_provider_id == str(HP(9)))).scalar_one()
        assert (row.goals, row.xg, row.minutes, row.rating) == (2, 1.2, 90, 7.5)
        assert row.match_id is not None and row.team_id is not None and as_utc(row.fetched_at) == fetched
        # match-time list stamped at kickoff
        a = s.execute(select(PlayerAvailability)).scalar_one()
        assert a.timestamp_basis == "match_kickoff" and as_utc(a.first_observed_at) == datetime(2026, 10, 4, 15, tzinfo=UTC)
        assert a.match_id is not None
        # re-apply same fetch -> updates, no duplicates
        c2 = apply_match_payload(TeamNewsStore(s), payload, fetched)
        s.commit()
        assert c2["stats_inserted"] == 0 and c2["stats_updated"] == 28
        # older fetch never overwrites newer rows
        c3 = apply_match_payload(TeamNewsStore(s), payload, fetched - timedelta(hours=1))
        s.commit()
        assert c3["stats_skipped_older"] == 28
        assert s.scalar(select(func.count()).select_from(PlayerMatchStat)) == 28
        reg = s.execute(select(TeamNewsMatch)).scalar_one()
        assert as_utc(reg.stats_ingested_at) == fetched


def test_needs_finished_ingest():
    ko = datetime(2026, 10, 12, 19, tzinfo=UTC)
    ref = MatchRef(provider_match_id="1", kickoff_at=ko, status="finished")
    now = ko + timedelta(hours=3)
    assert needs_finished_ingest(ref, None, now) is True
    assert needs_finished_ingest(ref, {"stats_ingested_at": ko + timedelta(hours=2, minutes=50)}, now) is False
    assert needs_finished_ingest(ref, {"stats_ingested_at": ko + timedelta(hours=2)}, now) is True
    assert needs_finished_ingest(ref, {"stats_ingested_at": ko + timedelta(hours=7)}, ko + timedelta(hours=9)) is False


# =========================================================================== async service (mock transport)


class FakeFotMob:
    """httpx.MockTransport handler serving SYNTHETIC payloads; records requests."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.url.path, tuple(sorted(request.url.params.items()))))
        for (path, params), resp in self.routes.items():
            if path == request.url.path and all(request.url.params.get(k) == v for k, v in params):
                return resp() if callable(resp) else httpx.Response(200, json=resp)
        return httpx.Response(404, json={"error": "not found"})


def R(path: str, **params: str):
    """Route key of FakeFotMob: (path, ((param, value), ...))."""
    return (path, tuple(sorted(params.items())))


def make_client(routes):
    fake = FakeFotMob(routes)
    client = TeamNewsFotMobClient(
        base_url="https://fotmob.test", min_interval_seconds=0, transport=httpx.MockTransport(fake), test_mode=True
    )
    return client, fake


def test_service_refresh_ingest_squads_and_cycle(session_factory, tmp_path):
    with session_factory() as s:
        src, comp, teams = seed_base(s)
        s.commit()
    now = datetime.now(UTC).replace(microsecond=0)
    ko = (now + timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    done_ko = (now - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    routes = {
        R("/api/data/leagues", id="47"): synthetic_league_payload(
            47,
            [
                {"id": 7101, "home": SYN_HOME_TEAM, "away": SYN_AWAY_TEAM, "utcTime": ko},
                {"id": 7102, "home": SYN_AWAY_TEAM, "away": SYN_HOME_TEAM, "utcTime": done_ko, "finished": True},
            ],
        ),
        R("/api/data/matchDetails", matchId="7101"): synthetic_match_payload(
            7101, kickoff=ko, unavailable={"home": [(2, "injury", "Unknown")], "away": []}
        ),
        R("/api/data/matchDetails", matchId="7102"): synthetic_match_payload(
            7102, home=SYN_AWAY_TEAM, away=SYN_HOME_TEAM, kickoff=done_ko, status="finished",
            lineup_type="standard", home_score=0, away_score=1,
            stats={HP(10): {"minutes": 90, "rating": 7.0, "goals": 1, "xg": 0.6, "shotmap": 2}},
        ),
        R("/api/data/teams", id=str(SYN_HOME_TEAM)): synthetic_team_payload(SYN_HOME_TEAM, injured={2: ("30", "Unknown")}),
        R("/api/data/teams", id=str(SYN_AWAY_TEAM)): synthetic_team_payload(SYN_AWAY_TEAM),
    }
    client, fake = make_client(routes)
    raw = RawStore(tmp_path / "raw")
    service = TeamNewsService(session_factory, client, raw)

    async def run():
        summary = await service.run_cycle(now, hours_ahead=72, lookback_hours=24, competitions=[47], squads="window")
        again = await service.run_cycle(
            now, hours_ahead=72, lookback_hours=24, competitions=[47], squads="none",
            match_due=lambda ref, last: last is None,
        )
        await client.aclose()
        return summary, again

    summary, again = asyncio.run(run())
    assert summary["discovered"] == 2 and summary["upcoming"] == 1 and summary["finished"] == 1
    assert summary["squads"]["ok"] == 2 and summary["squads"]["injured"] == 1
    assert again["upcoming"] == 0 and again["finished"] == 0  # due-check and settle rule
    with session_factory() as s:
        assert s.scalar(select(func.count()).select_from(LineupSnapshot)) == 4
        assert s.scalar(select(func.count()).select_from(PlayerMatchStat).where(PlayerMatchStat.provider_match_id == "7102")) == 22
        assert s.scalar(select(func.count()).select_from(TeamSquadMember)) == 28
        regs = {r.provider_match_id: r for r in s.execute(select(TeamNewsMatch)).scalars()}
        assert set(regs) == {"7101", "7102"} and regs["7102"].stats_ingested_at is not None
    assert raw.saved >= 4 and (tmp_path / "raw" / "match_details" / "_manifest.jsonl").exists()


def test_client_blocked_and_rate_limited():
    routes = {
        R("/api/data/teams", id="1"): lambda: httpx.Response(403, text="Forbidden"),
        R("/api/data/teams", id="2"): lambda: httpx.Response(429, headers={"Retry-After": "5"}),
        R("/api/data/teams", id="3"): lambda: httpx.Response(
            200, text="<html>captcha challenge</html>", headers={"content-type": "text/html"}
        ),
        R("/api/data/teams", id="4"): lambda: httpx.Response(
            502, text="<html>Bad Gateway</html>", headers={"content-type": "text/html"}
        ),
    }

    async def run():
        c1, fake = make_client(routes)
        with pytest.raises(FotMobRateLimitedError):
            await c1.team("2")
        with pytest.raises(FotMobBlockedError):
            await c1.team("1")
        assert c1.blocked is True
        n = len(fake.calls)
        with pytest.raises(FotMobBlockedError):
            await c1.team("2")  # refuses further requests once blocked
        assert len(fake.calls) == n
        await c1.aclose()
        c2, _ = make_client(routes)
        with pytest.raises(FotMobUnavailableError):
            await c2.team("4")  # plain 5xx error page: not a block
        assert c2.blocked is False
        with pytest.raises(FotMobBlockedError):
            await c2.team("3")  # HTML challenge page
        await c2.aclose()

    asyncio.run(run())


def test_service_propagates_block(session_factory):
    with session_factory() as s:
        seed_base(s)
        s.commit()
    client, _ = make_client({R("/api/data/matchDetails", matchId="1"): lambda: httpx.Response(403)})
    service = TeamNewsService(session_factory, client)

    async def run():
        with pytest.raises(FotMobBlockedError):
            await service.refresh_match_team_news("fotmob_1")
        await client.aclose()

    asyncio.run(run())


# =========================================================================== read model


def _seed_history(s):
    """5 finished SYNTHETIC matches per team before a 2026-10-20 kickoff + player stats."""
    src, comp, teams = seed_base(s)
    store = TeamNewsStore(s)
    base_day = datetime(2026, 9, 20, 15, tzinfo=UTC)
    for i in range(5):
        when = base_day + timedelta(days=5 * i)
        mid = 6500000 + i
        hs, as_ = (2, 0) if i % 2 == 0 else (1, 1)
        add_match(s, src, comp, teams, mid, SYN_HOME_TEAM, 990003, when, hs, as_, 1.5, 0.5 if i != 4 else None)
        stats = {
            HP(9): {"minutes": 90, "rating": 7.0 + i / 10, "goals": 1 if i % 2 == 0 else 0, "xg": 0.5, "shotmap": 2},
            HP(4): {"minutes": 90, "rating": 6.5, "goals": 0, "shotmap": 0},  # no shot -> zero rule
            HP(2): {"minutes": 90, "rating": 6.8, "goals": 1 if i == 0 else 0, "xg": 0.3, "shotmap": 1},
        }
        apply_match_payload(
            store,
            synthetic_match_payload(
                mid, home=SYN_HOME_TEAM, away=990003, kickoff=when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                status="finished", lineup_type="standard", home_score=hs, away_score=as_, stats=stats,
                home_starters=list(range(1, 12)) if i < 3 else [1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            ),
            when + timedelta(hours=3),
        )
        if i < 2:  # only 2 of the away team's matches have player data
            add_match(s, src, comp, teams, 6600000 + i, 990004, SYN_AWAY_TEAM, when, 0, 3, None, None)
    s.commit()
    return src, comp, teams


def test_build_team_news_upcoming_match(session_factory):
    with session_factory() as s:
        _seed_history(s)
        store = TeamNewsStore(s)
        apply_team_payload(store, synthetic_team_payload(SYN_HOME_TEAM, injured={2: ("30", "Late October 2026")}), T0)
        mid = 6700001
        apply_match_payload(
            store,
            synthetic_match_payload(
                mid, kickoff="2026-10-20T19:00:00.000Z",
                home_starters=[1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                unavailable={"home": [(2, "injury", "Late October 2026")]},
            ),
            T0,
        )
        s.commit()
        news = build_team_news(s, f"fotmob_{mid}", now=T0 + timedelta(minutes=5))

    assert news.match.provider_match_id == str(mid) and news.match.match_id is None
    assert news.match.as_of == T0 + timedelta(minutes=5)
    home, away = news.home, news.away
    assert home.team.provider_id == str(SYN_HOME_TEAM) and home.team.team_id is not None
    assert home.lineup is not None and home.lineup.lineup_type == "predicted"
    assert home.lineup.lineup_status == "predicted" and home.lineup.based_on_match_id is None
    assert home.lineup.lineup_type_label == "Tahmini ilk 11 (FotMob)"
    striker = next(p for p in home.lineup.starters if p.provider_id == str(HP(9)))
    f = striker.form
    assert (f.window_matches, f.matches_with_data, f.apps, f.starts, f.minutes) == (5, 5, 5, 5, 450)
    assert f.goals == 3 and f.xg == 2.5 and f.coverage.xg_apps == 5 and f.missing_reason is None
    assert f.avg_rating == 7.2
    defender = next(p for p in home.lineup.starters if p.provider_id == str(HP(4)))
    assert defender.form.xg == 0.0 and defender.form.coverage.xg_zero_rule_apps == 5
    sub12 = next(p for p in home.lineup.starters if p.provider_id == str(HP(12)))
    assert sub12.form.apps == 2 and sub12.form.coverage.minutes_apps == 0 and sub12.form.minutes is None

    [absent] = home.absentees
    assert absent.player.provider_id == str(HP(2)) and absent.status == "injured"
    assert absent.primary_source == "fotmob_match_lineup"
    assert {r.source for r in absent.reports} == {"fotmob_match_lineup", "fotmob_team_squad"}
    assert absent.form.apps == 3 and absent.form.goals == 1
    sh = absent.share
    assert sh.matches_used == 5 and sh.team_goals == 8 and sh.player_goals == 1 and sh.goals_share == 0.125
    assert sh.team_minutes == 450 and sh.player_minutes == 270 and sh.minutes_share == 0.6
    assert sh.team_xg == 7.5 and sh.player_xg == 0.9 and sh.xg_share == 0.12  # own xG known in all 5
    assert home.last5.played == 5 and (home.last5.wins, home.last5.draws, home.last5.losses) == (3, 2, 0)
    assert home.last5.goals_for == 8 and home.last5.xg_matches == 4
    assert home.freshness.lineup_observed_at == T0 and home.freshness.squad_observed_at == T0

    assert away.lineup is not None and away.absentees == []
    assert away.absentees_missing_reason == "availability_not_observed"  # away list never sent, no squad
    assert away.last5.played == 2 and away.last5.xg_for is None and away.last5.xg_matches == 0
    sk = {x.source for x in news.sources}
    assert {"fotmob_match_lineup", "fotmob_team_squad", "fotmob_match_details", "local_matches"} <= sk


def test_build_team_news_point_in_time_for_finished_and_not_found(session_factory):
    with session_factory() as s:
        _seed_history(s)
        # squad injury observed today must not leak into a historical match view
        apply_team_payload(TeamNewsStore(s), synthetic_team_payload(SYN_HOME_TEAM, injured={9: ("30", "Unknown")}), T0)
        s.commit()
        news = build_team_news(s, "6500004", now=T0)
        assert news.match.match_id is not None and news.match.status == "finished"
        assert news.match.as_of == datetime(2026, 10, 10, 15, tzinfo=UTC)
        assert news.home.absentees == []
        assert news.home.lineup is not None and news.home.lineup.timestamp_basis == "match_kickoff"
        assert news.home.last5.played == 4  # strictly before kickoff
        with pytest.raises(TeamNewsNotFound):
            build_team_news(s, "fotmob_123456789", now=T0)
        with pytest.raises(TeamNewsNotFound):
            build_team_news(s, "not-a-known-uuid", now=T0)


def test_build_team_squad(session_factory):
    with session_factory() as s:
        seed_base(s)
        apply_team_payload(TeamNewsStore(s), synthetic_team_payload(injured={5: ("30", "Unknown")}), T0)
        apply_team_payload(TeamNewsStore(s), synthetic_team_payload(n_players=13, injured={5: ("30", "Unknown")}), T0 + timedelta(hours=6))
        s.commit()
        squad = build_team_squad(s, str(SYN_HOME_TEAM))
        assert squad.season == "2026/2027" and squad.squad_observed_at == T0 + timedelta(hours=6)
        assert len(squad.players) == 13  # player 14 left the latest squad
        p5 = next(p for p in squad.players if p.provider_id == str(HP(5)))
        assert p5.availability_status == "unavailable" and p5.availability[0].status == "injured"
        assert next(p for p in squad.players if p.provider_id == str(HP(1))).availability_status == "no_report"
        full = build_team_squad(s, f"fotmob_{SYN_HOME_TEAM}", include_former=True)
        assert len(full.players) == 14 and sum(not p.in_latest_squad for p in full.players) == 1
        empty = build_team_squad(s, str(SYN_AWAY_TEAM))
        assert empty.players == [] and empty.missing_reason == "squad_not_observed"
        with pytest.raises(TeamNewsNotFound):
            build_team_squad(s, "424242")


# =========================================================================== refresh loop (scheduler)


class _LoopCfg:
    team_news_competitions = "47"
    team_news_hours_ahead = 72.0
    team_news_finished_lookback_hours = 24.0
    team_news_squad_refresh_hours = 6.0
    team_news_match_refresh_minutes = 15.0
    team_news_near_kickoff_hours = 2.0
    team_news_near_kickoff_refresh_minutes = 5.0
    team_news_finished_refresh_minutes = 30.0


def test_refresh_loop_cadence(session_factory):
    from app.services.team_news.scheduler import TeamNewsRefreshLoop

    with session_factory() as s:
        seed_base(s)
        s.commit()
    now = datetime.now(UTC).replace(microsecond=0)
    far_ko = (now + timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    near_ko = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    routes = {
        R("/api/data/leagues", id="47"): synthetic_league_payload(
            47,
            [
                {"id": 7201, "home": SYN_HOME_TEAM, "away": SYN_AWAY_TEAM, "utcTime": far_ko},
                {"id": 7202, "home": SYN_AWAY_TEAM, "away": SYN_HOME_TEAM, "utcTime": near_ko},
            ],
        ),
        R("/api/data/matchDetails", matchId="7201"): synthetic_match_payload(7201, kickoff=far_ko),
        R("/api/data/matchDetails", matchId="7202"): synthetic_match_payload(
            7202, home=SYN_AWAY_TEAM, away=SYN_HOME_TEAM, kickoff=near_ko
        ),
        R("/api/data/teams", id=str(SYN_HOME_TEAM)): synthetic_team_payload(SYN_HOME_TEAM),
        R("/api/data/teams", id=str(SYN_AWAY_TEAM)): synthetic_team_payload(SYN_AWAY_TEAM),
    }
    client, fake = make_client(routes)
    loop = TeamNewsRefreshLoop(session_factory, cfg=_LoopCfg, client=client, raw_store=RawStore(None))

    async def run():
        s1 = await loop.tick(now)
        s2 = await loop.tick(now + timedelta(minutes=1))
        s3 = await loop.tick(now + timedelta(minutes=6))
        s4 = await loop.tick(now + timedelta(minutes=16))
        await client.aclose()
        return s1, s2, s3, s4

    s1, s2, s3, s4 = asyncio.run(run())
    assert s1["upcoming"] == 2 and s1["squads"]["ok"] == 2  # first tick: everything + squads
    assert s2["upcoming"] == 0 and "squads" not in s2  # nothing due after 1 minute
    assert s3["upcoming"] == 1  # only the match within 2 h of kickoff (5-minute cadence)
    assert s4["upcoming"] == 2  # both due after 15 minutes
    assert sum(1 for path, _ in fake.calls if path == "/api/data/leagues") == 1  # fixtures cached (1 h)


def test_start_and_stop_refresher(session_factory, monkeypatch):
    from app.services.team_news import scheduler

    with session_factory() as s:
        seed_base(s)
        s.commit()
    client, fake = make_client({R("/api/data/leagues", id="47"): synthetic_league_payload(47, [])})
    monkeypatch.setattr(scheduler, "TeamNewsFotMobClient", lambda: client)
    monkeypatch.setattr(scheduler, "default_raw_store", lambda: RawStore(None))
    monkeypatch.setattr("app.config.settings.team_news_competitions", "47")

    async def run():
        handle = scheduler.start_team_news_refresher(session_factory)
        assert handle is not None
        await asyncio.sleep(0.2)
        await scheduler.stop_team_news_refresher(handle, timeout=5)
        return handle

    handle = asyncio.run(run())
    assert handle.task.done() and handle.loop.ticks >= 1
    assert any(path == "/api/data/leagues" for path, _ in fake.calls)


def test_refresher_not_started_without_tables():
    from app.services.team_news import scheduler

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine)

    async def run():
        return scheduler.start_team_news_refresher(factory)

    assert asyncio.run(run()) is None
    engine.dispose()


def test_last_starting11_snapshot_is_labelled_placeholder(session_factory):
    with session_factory() as s:
        seed_base(s)
        apply_match_payload(
            TeamNewsStore(s),
            synthetic_match_payload(6700002, kickoff="2026-10-25T19:00:00.000Z", lineup_type="lastStarting11", last_match=6699999),
            T0,
        )
        s.commit()
        news = build_team_news(s, "6700002", now=T0)
    assert news.home.lineup.lineup_status == "last_match_xi"
    assert news.home.lineup.based_on_match_id == "6699999"
    assert "tahmin değil" in news.home.lineup.lineup_type_label


def test_shared_limiter_permission_error_is_retried():
    from types import SimpleNamespace

    from app.services.team_news.fotmob_client import _acquire_shared

    calls = {"n": 0}

    async def flaky_acquire():
        calls["n"] += 1
        if calls["n"] < 3:  # Windows lock-dir race in fotmob_rate._Lock
            raise PermissionError("[WinError 5] Access is denied")

    asyncio.run(_acquire_shared(SimpleNamespace(acquire_async=flaky_acquire)))
    assert calls["n"] == 3


def test_cycle_continues_after_a_bad_match(session_factory):
    with session_factory() as s:
        seed_base(s)
        s.commit()
    now = datetime.now(UTC).replace(microsecond=0)
    ko1 = (now + timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ko2 = (now + timedelta(hours=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    routes = {
        R("/api/data/leagues", id="47"): synthetic_league_payload(
            47,
            [
                {"id": 7301, "home": SYN_HOME_TEAM, "away": SYN_AWAY_TEAM, "utcTime": ko1},
                {"id": 7302, "home": SYN_AWAY_TEAM, "away": SYN_HOME_TEAM, "utcTime": ko2},
            ],
        ),
        R("/api/data/matchDetails", matchId="7301"): [],  # unusable body (not an object)
        R("/api/data/matchDetails", matchId="7302"): synthetic_match_payload(7302, home=SYN_AWAY_TEAM, away=SYN_HOME_TEAM, kickoff=ko2),
    }
    client, _ = make_client(routes)
    service = TeamNewsService(session_factory, client)

    async def run():
        out = await service.run_cycle(now, competitions=[47], squads="none")
        await client.aclose()
        return out

    summary = asyncio.run(run())
    assert summary["errors"] == 1 and summary["upcoming"] == 1
