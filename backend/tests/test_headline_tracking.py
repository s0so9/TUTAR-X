"""Headline pick tracking: freezing, settlement, the tracker tick, the backfill and the loop.

Matches, teams and predictions below are SYNTHETIC TEST FIXTURES (made-up probabilities, never
football data). The backfill test reads the real hand-tracked record of 2026-10-14 from docs/.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.models import Base, PredictionVersionDB
from app.prediction.headline_picks import PickCandidate
from app.prediction.prediction_version import PredictionStage, PredictionVersionManager
from app.services.headline_tracking import backfill as backfill_module
from app.services.headline_tracking.records import (
    HEADLINE_STAGES,
    SOURCE_LIVE,
    SOURCE_MANUAL_2026_10_14,
    STAGE_BY_KIND,
    MatchFacts,
    existing_stages,
    freeze_pick,
    settle_row,
    unsettled_rows,
)
from app.services.headline_tracking.results import (
    REASON_CANCELLED,
    REASON_EXTRA_TIME,
    ChainedResultFetcher,
    DbResultFetcher,
    LiveCenterResultFetcher,
    MatchResult,
    settle_outcome,
)
from app.services.headline_tracking.sources import (
    ScheduledMatch,
    lineup_types_from_squad_info,
    normalise_lineup_type,
    to_scheduled_match,
)
from app.services.headline_tracking.tracker import (
    HeadlineTracker,
    start_headline_tracker,
    stop_headline_tracker,
)
from app.services.prediction_persistence import PredictionPersistenceService

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = json.loads(
    (REPO_ROOT / "frontend" / "src" / "utils" / "__tests__" / "headlinePicks.fixtures.json").read_text(encoding="utf-8")
)
# response case 0: banko HOME_OR_DRAW (1X), oranli OVER_2_5 (see the parity test)
PREDICTION = copy.deepcopy(FIXTURES["response_cases"][0]["prediction"])
PREDICTION["squad_info"] = {
    "source": "fotmob",
    "home": {"team_name": "Home FC", "lineup_type": "standard"},
    "away": {"team_name": "Away FC", "lineup_type": "standard"},
}
NOW = datetime(2026, 10, 15, 16, 0, tzinfo=timezone.utc)

CFG = SimpleNamespace(
    headline_tracking_enabled=True,
    headline_freeze_minutes_before=20,
    headline_tick_seconds=0.01,
    headline_schedule_refresh_seconds=300,
    headline_settle_first_check_minutes=95,
    headline_settle_check_seconds=120,
    headline_settle_give_up_hours=12,
)


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    yield factory
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def scheduled(match_id="fotmob_1", minutes=15, competition="42", status="SCHEDULED", now=NOW) -> ScheduledMatch:
    return ScheduledMatch(
        match_id=match_id,
        competition_id=competition,
        competition_name="Test Competition (synthetic)",
        kickoff_at=now + timedelta(minutes=minutes),
        status=status,
        home_team="Home FC",
        away_team="Away FC",
    )


class Mocks:
    """Injected sources of the tracker: no network, call counters."""

    def __init__(self, fixtures: List[ScheduledMatch], prediction: Optional[Dict[str, Any]] = None):
        self.fixtures = fixtures
        self.prediction = prediction if prediction is not None else copy.deepcopy(PREDICTION)
        self.schedule_calls = 0
        self.predict_calls: List[str] = []
        self.result_calls: List[str] = []
        self.lineup_calls: List[str] = []
        self.results: Dict[str, Optional[MatchResult]] = {}
        self.predict_error: Optional[Exception] = None
        self.lineup: Optional[dict] = None

    async def schedule(self, now):
        self.schedule_calls += 1
        return self.fixtures

    async def predictor(self, match_id):
        self.predict_calls.append(match_id)
        if self.predict_error:
            raise self.predict_error
        return copy.deepcopy(self.prediction)

    async def result_fetcher(self, match_id):
        self.result_calls.append(match_id)
        return self.results.get(match_id)

    async def lineup_lookup(self, match_id):
        self.lineup_calls.append(match_id)
        return self.lineup


def make_tracker(session_factory, mocks: Mocks, featured=("42", "73")) -> HeadlineTracker:
    return HeadlineTracker(
        session_factory,
        cfg=CFG,
        schedule=mocks.schedule,
        predictor=mocks.predictor,
        results=mocks.result_fetcher,
        lineup_lookup=mocks.lineup_lookup,
        featured=set(featured),
    )


def run(coro):
    return asyncio.run(coro)


def rows(session_factory, stage: Optional[str] = None) -> List[PredictionVersionDB]:
    with session_factory() as session:
        stmt = select(PredictionVersionDB).where(PredictionVersionDB.stage.in_(HEADLINE_STAGES))
        if stage:
            stmt = stmt.where(PredictionVersionDB.stage == stage)
        return list(session.execute(stmt.order_by(PredictionVersionDB.stage)).scalars().all())


# --------------------------------------------------------------------------- records


def candidate(key="HOME_OR_DRAW", p=0.81, odds=None) -> PickCandidate:
    return PickCandidate(
        key=key, market_name="Çifte Şans", outcome="1X (Home FC veya beraberlik)", probability=p,
        fair_odds=1 / p, odds=odds, odds_source="Test Book" if odds else None,
    )


def facts(match_id="fotmob_1") -> MatchFacts:
    return MatchFacts(
        match_id=match_id, kickoff_at=NOW + timedelta(minutes=20), competition_id="42",
        competition_name="Test Competition (synthetic)", home_team="Home FC", away_team="Away FC",
    )


def freeze(session, kind="banko", pick=None, match=None, **kw):
    return freeze_pick(
        session, kind, pick or candidate(), match or facts(), frozen_at=NOW,
        model_1x2={"home": 0.59, "draw": 0.22, "away": 0.19},
        lineup_types={"home": "confirmed", "away": "confirmed", "source": "test"}, **kw,
    )


def test_freeze_fills_the_columns_and_the_json(session_factory):
    with session_factory() as session:
        row_id = freeze(session, pick=candidate(odds=1.55))
    (row,) = rows(session_factory, "headline_banko")
    assert row.id == row_id
    assert row.match_id == "fotmob_1"
    assert row.selected_market == "HOME_OR_DRAW"
    assert row.selection_text == "1X (Home FC veya beraberlik)"
    assert row.selection_probability == pytest.approx(0.81)
    assert row.selection_fair_odds == pytest.approx(1 / 0.81)
    assert row.selection_odds == 1.55
    assert row.actual_result is None and row.settled_at is None
    data = row.prediction_data
    assert data["rule_version"] == "headline_v2"
    assert data["banko_tier"] == "guclu"  # 0.81: informational copy of the tier
    assert data["kind"] == "banko" and data["source"] == SOURCE_LIVE
    assert data["frozen_at"] == "2026-10-15T16:00:00Z"
    assert data["kickoff_at"] == "2026-10-15T16:20:00Z"
    assert data["minutes_before_kickoff"] == 20.0
    assert data["model_1x2"] == {"home": 0.59, "draw": 0.22, "away": 0.19}
    assert data["lineup_type"] == {"home": "confirmed", "away": "confirmed", "source": "test"}
    assert data["home_team"] == "Home FC" and data["competition_id"] == "42"
    json.dumps(data)  # JSON-serialisable


def test_the_oranli_record_carries_no_tier(session_factory):
    with session_factory() as session:
        freeze(session, kind="oranli", pick=candidate(key="OVER_2_5", p=0.58))
    (row,) = rows(session_factory, "headline_oranli")
    assert row.prediction_data["rule_version"] == "headline_v2"
    assert "banko_tier" not in row.prediction_data


def test_odds_stay_null_without_a_bookmaker_price(session_factory):
    with session_factory() as session:
        freeze(session)
    (row,) = rows(session_factory)
    assert row.selection_odds is None
    assert row.prediction_data["odds_source"] is None


def test_freezing_twice_never_overwrites(session_factory):
    with session_factory() as session:
        first = freeze(session)
        second = freeze(session, pick=candidate("OVER_1_5", 0.9))  # a different pick, same match and stage
    assert first is not None and second is None
    (row,) = rows(session_factory)
    assert row.selected_market == "HOME_OR_DRAW" and row.selection_probability == pytest.approx(0.81)


def test_each_kind_has_its_own_stage(session_factory):
    with session_factory() as session:
        assert freeze(session, "banko") is not None
        assert freeze(session, "oranli", pick=candidate("OVER_2_5", 0.58)) is not None
        assert existing_stages(session, "fotmob_1") == set(HEADLINE_STAGES)
        assert existing_stages(session, "fotmob_2") == set()
    assert {r.stage for r in rows(session_factory)} == {"headline_banko", "headline_oranli"}


def test_headline_stages_do_not_break_the_version_manager(session_factory):
    """prediction_versions rows of unknown stages used to make get_versions() raise."""
    with session_factory() as session:
        freeze(session)
        manager = PredictionVersionManager(persistence_service=PredictionPersistenceService(session))
        versions = manager.get_versions("fotmob_1")
        assert [v.stage for v in versions] == [PredictionStage.HEADLINE_BANKO]
        assert versions[0].selected_market == "HOME_OR_DRAW"
        assert PredictionStage("headline_oranli") is PredictionStage.HEADLINE_ORANLI


def test_a_concurrent_duplicate_is_dropped_oldest_survives(session_factory):
    with session_factory() as session:
        freeze(session)
        # a second writer (another process) inserts the same (match, stage) behind our back
        duplicate = PredictionVersionDB(
            id="dup", match_id="fotmob_1", stage="headline_banko", prediction_data={"x": 1},
            confidence_score=0.0, selected_market="OVER_1_5",
            created_at=datetime.utcnow() + timedelta(seconds=5), updated_at=datetime.utcnow(),
        )
        session.add(duplicate)
        session.commit()
        from app.services.headline_tracking.records import _drop_concurrent_duplicates

        _drop_concurrent_duplicates(session, "fotmob_1", "headline_banko")
    (row,) = rows(session_factory)
    assert row.id != "dup" and row.selected_market == "HOME_OR_DRAW"


def test_settle_row_sets_result_score_and_is_final(session_factory):
    with session_factory() as session:
        freeze(session)
        (row,) = unsettled_rows(session)
        ok = settle_row(
            session, row, outcome="won", final_score={"home": 2, "away": 1}, reason=None, result_source="test",
            now=NOW + timedelta(hours=2),
        )
        assert ok is True
        assert settle_row(session, row, outcome="lost", final_score=None, reason=None, result_source="x") is False
        assert unsettled_rows(session) == []
    (row,) = rows(session_factory)
    assert row.actual_result == "won"
    assert row.settled_at is not None
    assert row.prediction_data["final_score"] == {"home": 2, "away": 1}
    assert row.prediction_data["settlement"]["result_source"] == "test"
    assert row.prediction_data["frozen_at"] == "2026-10-15T16:00:00Z"  # the frozen part is untouched
    assert row.selected_market == "HOME_OR_DRAW" and row.selection_probability == pytest.approx(0.81)


def test_settle_row_rejects_unknown_results(session_factory):
    with session_factory() as session:
        freeze(session)
        (row,) = unsettled_rows(session)
        with pytest.raises(ValueError):
            settle_row(session, row, outcome="WIN", final_score=None, reason=None, result_source=None)


# --------------------------------------------------------------------------- settlement rules


def test_settle_outcome():
    finished = MatchResult("FINISHED", 2, 1, source="t")
    assert settle_outcome("HOME_OR_DRAW", finished) == ("won", None)
    assert settle_outcome("DRAW_OR_AWAY", finished) == ("lost", None)
    assert settle_outcome("OVER_2_5", finished) == ("won", None)
    assert settle_outcome("BTTS_NO", finished) == ("lost", None)
    for status in ("CANCELLED", "ABANDONED", "POSTPONED"):
        assert settle_outcome("HOME_WIN", MatchResult(status)) == ("void", REASON_CANCELLED)
    assert settle_outcome("OVER_2_5", MatchResult("FINISHED", 2, 2, went_to_extra_time=True)) == ("void", REASON_EXTRA_TIME)
    for not_final in (MatchResult("LIVE", 1, 0), MatchResult("HALF_TIME", 0, 0), MatchResult("FINISHED", None, None)):
        assert not_final.is_final is False
        assert settle_outcome("HOME_WIN", not_final) == (None, None)


def test_lineup_type_normalisation():
    assert normalise_lineup_type("standard") == "confirmed"
    assert normalise_lineup_type("Confirmed") == "confirmed"
    assert normalise_lineup_type("predicted") == "predicted"
    assert normalise_lineup_type("lastStarting11") == "last_starting11"
    assert normalise_lineup_type("unavailable") is None
    assert normalise_lineup_type(None) is None
    assert lineup_types_from_squad_info(PREDICTION["squad_info"]) == {
        "home": "confirmed", "away": "confirmed", "source": "prediction.squad_info"
    }
    assert lineup_types_from_squad_info(None) is None
    assert lineup_types_from_squad_info({"home": {"lineup_type": None}, "away": {}}) is None


def test_to_scheduled_match_reads_the_domain_match():
    m = SimpleNamespace(
        id="fotmob_7", competition_id="73", scheduled_at=datetime(2026, 10, 15, 16, 45), status=SimpleNamespace(value="SCHEDULED"),
        _provider_home_team_name="H", _provider_away_team_name="A", _provider_competition_name="Europa League",
    )
    s = to_scheduled_match(m)
    assert s.kickoff_at == datetime(2026, 10, 15, 16, 45, tzinfo=timezone.utc)  # naive = UTC
    assert (s.match_id, s.competition_id, s.status, s.home_team, s.competition_name) == (
        "fotmob_7", "73", "SCHEDULED", "H", "Europa League"
    )
    assert to_scheduled_match(SimpleNamespace(id="x", scheduled_at=None)) is None


# --------------------------------------------------------------------------- tracker: freeze


def test_tick_freezes_only_matches_inside_the_window(session_factory):
    mocks = Mocks([
        scheduled("fotmob_in", minutes=15),          # inside the 20-minute window -> frozen
        scheduled("fotmob_edge", minutes=20),        # exactly 20 minutes -> frozen
        scheduled("fotmob_far", minutes=25),         # later (still within the 30-minute look-ahead)
        scheduled("fotmob_started", minutes=-1),     # already kicked off: never frozen afterwards
        scheduled("fotmob_other", minutes=10, competition="999"),   # not a featured competition
        scheduled("fotmob_live", minutes=10, status="LIVE"),        # not SCHEDULED
        scheduled("fotmob_post", minutes=10, status="POSTPONED"),
    ])
    tracker = make_tracker(session_factory, mocks)
    summary = run(tracker.tick(NOW))
    assert sorted(mocks.predict_calls) == ["fotmob_edge", "fotmob_in"]
    assert summary["upcoming_30m"] == 3  # in, edge, far
    frozen = {(r.match_id, r.stage) for r in rows(session_factory)}
    assert frozen == {
        ("fotmob_in", "headline_banko"), ("fotmob_in", "headline_oranli"),
        ("fotmob_edge", "headline_banko"), ("fotmob_edge", "headline_oranli"),
    }
    # the far match enters the window later
    run(tracker.tick(NOW + timedelta(minutes=6)))
    assert "fotmob_far" in mocks.predict_calls


def test_frozen_values_come_from_the_rule_and_the_prediction(session_factory):
    mocks = Mocks([scheduled("fotmob_1", minutes=18)])
    run(make_tracker(session_factory, mocks).tick(NOW))
    banko, oranli = rows(session_factory, "headline_banko")[0], rows(session_factory, "headline_oranli")[0]
    assert (banko.selected_market, oranli.selected_market) == ("HOME_OR_DRAW", "OVER_2_5")
    assert banko.selection_text == "1X (Home FC veya beraberlik)"
    assert oranli.selection_text == "Üst 2.5"
    assert banko.selection_probability == pytest.approx(0.81)
    assert oranli.selection_fair_odds == pytest.approx(1 / 0.58)
    assert banko.selection_odds is None
    data = banko.prediction_data
    assert data["model_1x2"] == {"home": 0.59, "draw": 0.22, "away": 0.19}
    assert data["lineup_type"] == {"home": "confirmed", "away": "confirmed", "source": "prediction.squad_info"}
    assert data["minutes_before_kickoff"] == 18.0
    assert data["frozen_at"] == "2026-10-15T16:00:00Z"
    assert mocks.lineup_calls == []  # squad_info already had both sides


def test_lineup_lookup_is_the_fallback_and_unknown_stays_unknown(session_factory):
    prediction = copy.deepcopy(PREDICTION)
    prediction["squad_info"] = None
    mocks = Mocks([scheduled("fotmob_1", minutes=15), scheduled("fotmob_2", minutes=15)], prediction)
    mocks.lineup = {"home": "predicted", "away": "predicted", "source": "live_center"}
    run(make_tracker(session_factory, mocks).tick(NOW))
    assert mocks.lineup_calls == ["fotmob_1", "fotmob_2"]
    assert rows(session_factory, "headline_banko")[0].prediction_data["lineup_type"]["home"] == "predicted"

    other = Mocks([scheduled("fotmob_3", minutes=15)], prediction)  # no line-up anywhere
    other.lineup = None
    run(make_tracker(session_factory, other).tick(NOW))
    banko3 = [r for r in rows(session_factory, "headline_banko") if r.match_id == "fotmob_3"][0]
    assert banko3.prediction_data["lineup_type"] == {"home": None, "away": None, "source": None}


def test_freezing_is_idempotent_across_ticks_and_restarts(session_factory):
    mocks = Mocks([scheduled("fotmob_1", minutes=15)])
    tracker = make_tracker(session_factory, mocks)
    run(tracker.tick(NOW))
    run(tracker.tick(NOW + timedelta(seconds=60)))
    assert mocks.predict_calls == ["fotmob_1"]  # evaluated once in this process
    before = [(r.id, r.selected_market, r.created_at) for r in rows(session_factory)]

    # a restarted process (fresh tracker, empty memory) finds the records and does not predict or write
    restarted = Mocks([scheduled("fotmob_1", minutes=10)])
    summary = run(make_tracker(session_factory, restarted).tick(NOW + timedelta(minutes=5)))
    assert restarted.predict_calls == []
    assert summary["already_frozen"] == ["fotmob_1"]
    assert [(r.id, r.selected_market, r.created_at) for r in rows(session_factory)] == before


def test_a_missing_stage_stores_nothing_for_that_stage(session_factory, caplog):
    # 1X2 0.40/0.30/0.30 and BTTS yes 0.40 (no market list): nothing is between 70 and 95 %, so no banko;
    # KG Yok (0.60) pays a fair 1.67, so an oranli exists
    prediction = {"home_win_probability": 0.4, "draw_probability": 0.3, "away_win_probability": 0.3,
                  "btts_probability": 0.4, "market_analysis": None}
    mocks = Mocks([scheduled("fotmob_1", minutes=15)], prediction)
    caplog.set_level(logging.INFO)
    run(make_tracker(session_factory, mocks).tick(NOW))
    assert {r.stage for r in rows(session_factory)} == {"headline_oranli"}
    assert [r.selected_market for r in rows(session_factory)] == ["BTTS_NO"]
    assert any("no banko qualifies" in r.message for r in caplog.records)


def test_no_qualifying_pick_at_all_stores_nothing_logs_and_is_not_retried(session_factory, caplog):
    # 0.97 / 0.02 / 0.01 and BTTS 0.97: every probability is above 95 % or below 45 %
    empty = {"home_win_probability": 0.97, "draw_probability": 0.02, "away_win_probability": 0.01,
             "btts_probability": 0.97, "market_analysis": None}
    mocks = Mocks([scheduled("fotmob_2", minutes=15)], empty)
    caplog.set_level(logging.INFO)
    tracker = make_tracker(session_factory, mocks)
    summary = run(tracker.tick(NOW))
    assert summary["no_pick"] == ["fotmob_2"]
    assert rows(session_factory) == []
    assert any("no banko qualifies" in r.message for r in caplog.records)
    assert any("no oranli qualifies" in r.message for r in caplog.records)
    run(tracker.tick(NOW + timedelta(seconds=60)))
    assert mocks.predict_calls == ["fotmob_2"]  # not predicted again every minute


def test_prediction_failure_is_retried_after_two_minutes(session_factory):
    mocks = Mocks([scheduled("fotmob_1", minutes=18)])
    mocks.predict_error = RuntimeError("insufficient data")
    tracker = make_tracker(session_factory, mocks)
    summary = run(tracker.tick(NOW))
    assert summary["prediction_failed"] == ["fotmob_1"] and rows(session_factory) == []
    run(tracker.tick(NOW + timedelta(seconds=60)))
    assert len(mocks.predict_calls) == 1  # still backing off
    mocks.predict_error = None
    run(tracker.tick(NOW + timedelta(seconds=125)))
    assert len(mocks.predict_calls) == 2
    assert len(rows(session_factory)) == 2


def test_a_failed_write_is_retried_and_not_marked_as_evaluated(session_factory, monkeypatch):
    from app.services.headline_tracking import tracker as tracker_module

    real = tracker_module.freeze_pick
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("database is locked")
        return real(*args, **kwargs)

    monkeypatch.setattr(tracker_module, "freeze_pick", flaky)
    mocks = Mocks([scheduled("fotmob_1", minutes=18)])
    tracker = make_tracker(session_factory, mocks)
    summary = run(tracker.tick(NOW))
    assert summary["frozen"] == [] and "database is locked" in summary["errors"][0]
    assert rows(session_factory) == []
    run(tracker.tick(NOW + timedelta(seconds=60)))  # still backing off
    assert len(mocks.predict_calls) == 1
    run(tracker.tick(NOW + timedelta(seconds=125)))
    assert len(rows(session_factory)) == 2


def test_tick_survives_a_failing_schedule(session_factory):
    mocks = Mocks([])

    async def broken(now):
        raise ConnectionError("provider down")

    tracker = make_tracker(session_factory, mocks)
    tracker.schedule = broken
    summary = run(tracker.tick(NOW))
    assert summary["errors"] and "provider down" in summary["errors"][0]


def test_the_schedule_is_re_read_only_every_five_minutes(session_factory):
    mocks = Mocks([scheduled("fotmob_1", minutes=40)])
    tracker = make_tracker(session_factory, mocks)
    for i in range(5):
        run(tracker.tick(NOW + timedelta(seconds=60 * i)))
    assert mocks.schedule_calls == 1
    run(tracker.tick(NOW + timedelta(seconds=301)))
    assert mocks.schedule_calls == 2


# --------------------------------------------------------------------------- tracker: settle


def frozen_match(session_factory, match_id="fotmob_1", kickoff_in=20):
    mocks = Mocks([scheduled(match_id, minutes=kickoff_in)])
    run(make_tracker(session_factory, mocks).tick(NOW))
    return NOW + timedelta(minutes=kickoff_in)


def test_nothing_is_looked_up_before_the_match_can_be_over(session_factory):
    kickoff = frozen_match(session_factory)
    mocks = Mocks([])
    mocks.results["fotmob_1"] = MatchResult("FINISHED", 3, 0, source="t")
    tracker = make_tracker(session_factory, mocks)
    run(tracker.tick(kickoff + timedelta(minutes=94)))
    assert mocks.result_calls == []
    assert all(r.actual_result is None for r in rows(session_factory))
    run(tracker.tick(kickoff + timedelta(minutes=95)))
    assert mocks.result_calls == ["fotmob_1"]


def test_final_result_settles_both_picks_with_the_score(session_factory):
    kickoff = frozen_match(session_factory)  # banko HOME_OR_DRAW, oranli OVER_2_5
    mocks = Mocks([])
    mocks.results["fotmob_1"] = MatchResult("FINISHED", 1, 2, source="live_center")  # 1X lost, over 2.5 won
    summary = run(make_tracker(session_factory, mocks).tick(kickoff + timedelta(minutes=110)))
    assert {(s["kind"], s["result"]) for s in summary["settled"]} == {("banko", "lost"), ("oranli", "won")}
    banko = rows(session_factory, "headline_banko")[0]
    oranli = rows(session_factory, "headline_oranli")[0]
    assert (banko.actual_result, oranli.actual_result) == ("lost", "won")
    assert banko.settled_at is not None
    assert banko.prediction_data["final_score"] == {"home": 1, "away": 2, "extra_time": False}
    assert banko.prediction_data["settlement"]["result_source"] == "live_center"
    assert banko.selected_market == "HOME_OR_DRAW"  # the frozen pick is not touched
    # settled once: later ticks do not look again
    mocks.result_calls.clear()
    run(make_tracker(session_factory, mocks).tick(kickoff + timedelta(minutes=125)))
    assert mocks.result_calls == []


def test_live_match_stays_pending_and_checks_are_spaced(session_factory):
    kickoff = frozen_match(session_factory)
    mocks = Mocks([])
    mocks.results["fotmob_1"] = MatchResult("LIVE", 1, 1, source="live_center")
    tracker = make_tracker(session_factory, mocks)
    run(tracker.tick(kickoff + timedelta(minutes=96)))
    run(tracker.tick(kickoff + timedelta(minutes=97)))  # < 120 s since the last look: skipped
    assert mocks.result_calls == ["fotmob_1"]
    run(tracker.tick(kickoff + timedelta(minutes=98, seconds=5)))
    assert len(mocks.result_calls) == 2
    assert all(r.actual_result is None for r in rows(session_factory))
    mocks.results["fotmob_1"] = MatchResult("FINISHED", 0, 0, source="live_center")
    run(tracker.tick(kickoff + timedelta(minutes=101)))
    banko = rows(session_factory, "headline_banko")[0]
    assert banko.actual_result == "won"  # 0-0: draw or home counts, 1X won
    assert rows(session_factory, "headline_oranli")[0].actual_result == "lost"  # over 2.5 lost


def test_cancelled_match_is_void_without_a_score(session_factory):
    kickoff = frozen_match(session_factory)
    mocks = Mocks([])
    mocks.results["fotmob_1"] = MatchResult("CANCELLED", None, None, source="live_center")
    run(make_tracker(session_factory, mocks).tick(kickoff + timedelta(minutes=100)))
    for r in rows(session_factory):
        assert r.actual_result == "void"
        assert r.prediction_data["final_score"] is None
        assert r.prediction_data["settlement"]["reason"] == REASON_CANCELLED


def test_extra_time_is_void(session_factory):
    kickoff = frozen_match(session_factory)
    mocks = Mocks([])
    mocks.results["fotmob_1"] = MatchResult("FINISHED", 2, 2, went_to_extra_time=True, source="live_center")
    run(make_tracker(session_factory, mocks).tick(kickoff + timedelta(minutes=140)))
    assert {r.actual_result for r in rows(session_factory)} == {"void"}


def test_gives_up_after_twelve_hours_and_logs_once(session_factory, caplog):
    kickoff = frozen_match(session_factory)
    mocks = Mocks([])
    tracker = make_tracker(session_factory, mocks)
    caplog.set_level(logging.WARNING)
    run(tracker.tick(kickoff + timedelta(hours=13)))
    run(tracker.tick(kickoff + timedelta(hours=14)))
    assert mocks.result_calls == []
    assert len([r for r in caplog.records if "no longer checking" in r.message]) == 1


def test_a_failing_result_lookup_does_not_stop_the_tick(session_factory):
    kickoff = frozen_match(session_factory)
    mocks = Mocks([])

    async def boom(match_id):
        raise TimeoutError("fotmob timeout")

    tracker = make_tracker(session_factory, mocks)
    tracker.results = boom
    summary = run(tracker.tick(kickoff + timedelta(minutes=100)))
    assert summary["settled"] == [] and summary["errors"] == []
    assert all(r.actual_result is None for r in rows(session_factory))


def test_records_without_a_kickoff_are_never_looked_up(session_factory):
    with session_factory() as session:
        freeze_pick(
            session, "banko", candidate(), MatchFacts(match_id="fotmob_9", kickoff_at=None),
            frozen_at=NOW, model_1x2=None, lineup_types=None,
        )
    mocks = Mocks([])
    run(make_tracker(session_factory, mocks).tick(NOW + timedelta(days=1)))
    assert mocks.result_calls == []


# --------------------------------------------------------------------------- result fetchers


def test_chained_fetcher_prefers_the_first_final_answer():
    async def not_final(_):
        return MatchResult("LIVE", 1, 0, source="a")

    async def final(_):
        return MatchResult("FINISHED", 2, 0, source="b")

    async def none(_):
        return None

    assert run(ChainedResultFetcher([none, not_final, final])("m")).source == "b"
    assert run(ChainedResultFetcher([none, not_final])("m")).source == "a"
    assert run(ChainedResultFetcher([none])("m")) is None


def test_db_result_fetcher_reads_only_finished_rows(session_factory):
    from app.database.models import Competition, Match, ProviderSource, Team

    with session_factory() as session:
        source = ProviderSource(name="fotmob", is_active=True)
        session.add(source)
        session.flush()
        comp = Competition(provider_source_id=source.id, provider_id="42", name="C")
        home, away = Team(provider_source_id=source.id, provider_id="1", name="H"), Team(provider_source_id=source.id, provider_id="2", name="A")
        session.add_all([comp, home, away])
        session.flush()
        for pid, status, hs, as_ in (("100", "FINISHED", 3, 1), ("101", "LIVE", 1, 0), ("102", "FINISHED", None, None)):
            session.add(Match(
                provider_source_id=source.id, provider_id=pid, competition_id=comp.id, home_team_id=home.id,
                away_team_id=away.id, scheduled_at=NOW, status=status, home_score=hs, away_score=as_,
            ))
        session.commit()
    fetch = DbResultFetcher(session_factory)
    done = run(fetch("fotmob_100"))
    assert (done.status, done.home_goals, done.away_goals, done.source) == ("FINISHED", 3, 1, "matches_table")
    assert run(fetch("fotmob_101")) is None
    assert run(fetch("fotmob_102")) is None
    assert run(fetch("fotmob_999")) is None


def test_live_center_fetcher_maps_status_score_and_extra_time():
    from app.services.live_center.service import LiveCenterError

    def response(status, home, away, status_text=None, penalties=None):
        return SimpleNamespace(
            status=status, status_text=status_text, score=SimpleNamespace(home=home, away=away),
            penalty_score=penalties,
        )

    class Service:
        def __init__(self, resp=None, error=None):
            self.resp, self.error = resp, error

        async def get(self, match_id):
            if self.error:
                raise self.error
            return self.resp

    ok = run(LiveCenterResultFetcher(Service(response("FINISHED", 2, 1, "FT")))("m"))
    assert (ok.status, ok.home_goals, ok.away_goals, ok.went_to_extra_time) == ("FINISHED", 2, 1, False)
    aet = run(LiveCenterResultFetcher(Service(response("FINISHED", 2, 2, "AET")))("m"))
    assert aet.went_to_extra_time is True
    pens = run(LiveCenterResultFetcher(Service(response("FINISHED", 1, 1, "Pen", SimpleNamespace(home=4, away=3))))("m"))
    assert pens.went_to_extra_time is True
    assert run(LiveCenterResultFetcher(Service(error=LiveCenterError("source_unavailable", 503)))("m")) is None


# --------------------------------------------------------------------------- backfill (real record)

# Final scores of the seven matches of 2026-10-14 (docs/live-tests/2026-10-14/results.md)
FINAL_SCORES_2026_10_14 = {
    "fotmob_6106284": (6, 0), "fotmob_6106254": (2, 4), "fotmob_6106315": (1, 0), "fotmob_6106274": (3, 4),
    "fotmob_6106299": (3, 2), "fotmob_6106337": (3, 1), "fotmob_6106396": (0, 3),
}


async def fake_results(match_id):
    score = FINAL_SCORES_2026_10_14.get(match_id)
    return MatchResult("FINISHED", score[0], score[1], source="test_scores") if score else None


PICKS_FILE = REPO_ROOT / "docs" / "live-tests" / "2026-10-14" / "system_picks.json"
LISTING_FILE = REPO_ROOT / "docs" / "live-tests" / "2026-10-14" / "cl_2026-10-14.json"


def test_backfill_imports_the_hand_tracked_night_and_settles_it(session_factory):
    summary = run(backfill_module.backfill_manual_2026_10_14(
        session_factory, fake_results, picks_file=PICKS_FILE, listing_file=LISTING_FILE))
    assert summary["matches"] == 7 and summary["frozen"] == 14 and summary["settled"] == 14
    all_rows = rows(session_factory)
    assert len(all_rows) == 14
    for r in all_rows:
        d = r.prediction_data
        assert d["source"] == SOURCE_MANUAL_2026_10_14 == "manual_record_2026-10-14"
        assert d["rule_version"] == "headline_v1"  # picked with the rule of that night, not the current one
        assert d["frozen_at"] == "2026-10-14T18:58:00Z"  # recorded_at_utc
        assert d["kickoff_at"] == "2026-10-14T19:00:00Z"
        assert d["competition_id"] == "42"
        assert r.selection_odds is None  # no odds were recorded: not invented
        assert r.selection_fair_odds == pytest.approx(1 / r.selection_probability)
        assert d["final_score"]["home"] == FINAL_SCORES_2026_10_14[r.match_id][0]
        assert r.actual_result in ("won", "lost")

    def tally(stage):
        picks = [r for r in all_rows if r.stage == stage]
        return sum(r.actual_result == "won" for r in picks), len(picks)

    assert tally("headline_banko") == (5, 7)   # results.md: Sistem banko 5/7
    assert tally("headline_oranli") == (5, 7)  # results.md: Sistem oranlı 5/7

    villa = [r for r in all_rows if r.match_id == "fotmob_6106284"]
    banko = [r for r in villa if r.stage == "headline_banko"][0]
    assert banko.selected_market == "HOME_OR_DRAW" and banko.selection_probability == pytest.approx(0.81)
    assert banko.prediction_data["home_team"] == "Aston Villa"
    assert banko.prediction_data["model_1x2"] == {"home": 0.59, "draw": 0.22, "away": 0.19}
    assert banko.prediction_data["lineup_type"]["home"] == "confirmed"


def test_backfill_is_idempotent_and_never_overwrites(session_factory):
    run(backfill_module.backfill_manual_2026_10_14(
        session_factory, fake_results, picks_file=PICKS_FILE, listing_file=LISTING_FILE))
    before = [(r.id, r.selected_market, r.actual_result, r.settled_at) for r in rows(session_factory)]
    again = run(backfill_module.backfill_manual_2026_10_14(
        session_factory, fake_results, picks_file=PICKS_FILE, listing_file=LISTING_FILE))
    assert again["frozen"] == 0 and again["already_there"] == 14 and again["settled"] == 0
    assert [(r.id, r.selected_market, r.actual_result, r.settled_at) for r in rows(session_factory)] == before


def test_backfill_without_a_result_leaves_the_pick_pending(session_factory):
    async def nothing(_):
        return None

    summary = run(backfill_module.backfill_manual_2026_10_14(
        session_factory, nothing, picks_file=PICKS_FILE, listing_file=LISTING_FILE))
    assert summary["frozen"] == 14 and summary["settled"] == 0 and len(summary["unsettled"]) == 7
    assert all(r.actual_result is None for r in rows(session_factory))


# --------------------------------------------------------------------------- the loop and the app


def test_loop_keeps_running_when_ticks_fail_and_stops_on_request(session_factory):
    tracker = make_tracker(session_factory, Mocks([]))
    calls: List[int] = []

    async def main():
        stop = asyncio.Event()

        async def flaky_tick(now=None):
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("boom")
            stop.set()
            return {}

        tracker.tick = flaky_tick  # type: ignore[assignment]
        await asyncio.wait_for(tracker.run(stop), timeout=5)

    asyncio.run(main())
    assert len(calls) == 3


def test_start_headline_tracker_needs_the_table_and_stops_cleanly(session_factory):
    async def main():
        handle = start_headline_tracker(session_factory)
        assert handle is not None
        assert handle.tracker.cfg.headline_freeze_minutes_before == 20
        await asyncio.sleep(0)
        await stop_headline_tracker(handle, timeout=2)
        assert handle.task.done()
        await stop_headline_tracker(None)

    asyncio.run(main())

    empty = sessionmaker(bind=create_engine("sqlite:///:memory:", future=True), future=True)

    async def without_table():
        assert start_headline_tracker(empty) is None

    asyncio.run(without_table())


def test_settings_defaults_and_env_switch(monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("HEADLINE_TRACKING_ENABLED", raising=False)
    monkeypatch.delenv("HEADLINE_FREEZE_MINUTES_BEFORE", raising=False)
    default = Settings()
    assert default.headline_tracking_enabled is True
    assert default.headline_freeze_minutes_before == 20
    monkeypatch.setenv("HEADLINE_TRACKING_ENABLED", "false")
    monkeypatch.setenv("HEADLINE_FREEZE_MINUTES_BEFORE", "25")
    switched = Settings()
    assert switched.headline_tracking_enabled is False
    assert switched.headline_freeze_minutes_before == 25


def test_stage_names():
    assert STAGE_BY_KIND == {"banko": "headline_banko", "oranli": "headline_oranli"}
