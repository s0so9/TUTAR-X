"""GET /track-record/headline and GET /matches/{id}/headline-record on a scratch database.

Matches and picks are SYNTHETIC TEST FIXTURES (made-up teams and probabilities).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.models import Base, PredictionVersionDB
from app.database.session import get_db
from app.main import app
from app.prediction.headline_picks import PickCandidate
from app.services.headline_tracking.records import MatchFacts, freeze_pick, settle_row, unsettled_rows


def pick(key: str, p: float) -> PickCandidate:
    return PickCandidate(key=key, market_name="Test market", outcome=f"{key} (synthetic)", probability=p, fair_odds=1 / p)


@pytest.fixture
def factory():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    Base.metadata.create_all(bind=engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def client(factory):
    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def add_match(factory, match_id, competition_id, days_ago, picks, results, name="Test League (synthetic)",
              rule_version=None):
    """picks / results: {'banko': (key, p), 'oranli': (key, p)} / {'banko': 'won', ...}
    rule_version: None = the current RULE_VERSION (what freeze_pick stores), else stored as given."""
    kickoff = datetime.now(timezone.utc) - timedelta(days=days_ago)
    match = MatchFacts(
        match_id=match_id, kickoff_at=kickoff, competition_id=competition_id, competition_name=name,
        home_team=f"Home {match_id}", away_team=f"Away {match_id}",
    )
    with factory() as session:
        for kind, (key, p) in picks.items():
            freeze_pick(
                session, kind, pick(key, p), match, frozen_at=kickoff - timedelta(minutes=20),
                model_1x2={"home": 0.5, "draw": 0.3, "away": 0.2},
                lineup_types={"home": "confirmed", "away": "predicted", "source": "test"},
                extra={"rule_version": rule_version} if rule_version else None,
            )
        for row in unsettled_rows(session):
            if row.match_id != match_id:
                continue
            outcome = results.get("banko" if row.stage == "headline_banko" else "oranli")
            if outcome is None:
                continue
            settle_row(
                session, row, outcome=outcome,
                final_score=None if outcome == "void" else {"home": 2, "away": 1, "extra_time": False},
                reason="x" if outcome == "void" else None, result_source="test",
            )


@pytest.fixture
def seeded(factory):
    add_match(factory, "fotmob_1", "42", 2, {"banko": ("HOME_OR_DRAW", 0.81), "oranli": ("OVER_2_5", 0.58)},
              {"banko": "won", "oranli": "lost"}, "Champions League")
    add_match(factory, "fotmob_2", "73", 3, {"banko": ("OVER_1_5", 0.8), "oranli": ("BTTS_YES", 0.55)},
              {"banko": "lost", "oranli": "won"}, "Europa League")
    add_match(factory, "fotmob_3", "42", 10, {"banko": ("HOME_OR_AWAY", 0.75), "oranli": ("DRAW_OR_AWAY", 0.5)},
              {"banko": "won", "oranli": "void"}, "Champions League")
    add_match(factory, "fotmob_4", "42", -0.1, {"banko": ("HOME_WIN", 0.72), "oranli": ("UNDER_3_5", 0.5)},
              {}, "Champions League")  # kicks off in 2.4 h: pending
    add_match(factory, "fotmob_5", "42", 40, {"banko": ("HOME_WIN", 0.72)}, {"banko": "won"}, "Champions League")
    return factory


def test_summary_counts_and_hit_rates(client, seeded):
    body = client.get("/api/v1/track-record/headline", params={"days": 30}).json()
    banko, oranli = body["summary"]["banko"], body["summary"]["oranli"]
    assert {k: banko[k] for k in ("won", "lost", "void", "pending", "settled")} == {
        "won": 2, "lost": 1, "void": 0, "pending": 1, "settled": 3}
    assert banko["hit_rate"] == pytest.approx(2 / 3)
    assert {k: oranli[k] for k in ("won", "lost", "void", "pending", "settled")} == {
        "won": 1, "lost": 1, "void": 1, "pending": 1, "settled": 2}
    assert oranli["hit_rate"] == pytest.approx(0.5)
    assert body["days"] == 30 and body["competition_id"] is None
    assert len(body["picks"]) == 8  # the 40-day-old match is outside the period
    assert "fotmob_5" not in {p["match_id"] for p in body["picks"]}


def test_hit_rate_is_null_while_nothing_is_settled(client, factory):
    add_match(factory, "fotmob_1", "42", -0.1, {"banko": ("HOME_WIN", 0.72)}, {})
    body = client.get("/api/v1/track-record/headline").json()
    assert body["summary"]["banko"]["hit_rate"] is None
    assert body["summary"]["banko"]["pending"] == 1
    assert body["summary"]["oranli"] == {"won": 0, "lost": 0, "void": 0, "pending": 0, "settled": 0, "hit_rate": None}


def test_empty_database(client):
    body = client.get("/api/v1/track-record/headline").json()
    assert body["picks"] == [] and body["by_competition"] == [] and body["by_week"] == []
    assert body["summary"]["banko"]["hit_rate"] is None
    assert body["available_competitions"] == []


def test_period_filter(client, seeded):
    body = client.get("/api/v1/track-record/headline", params={"days": 7}).json()
    assert {p["match_id"] for p in body["picks"]} == {"fotmob_1", "fotmob_2", "fotmob_4"}
    assert body["summary"]["banko"]["won"] == 1 and body["summary"]["banko"]["lost"] == 1
    wide = client.get("/api/v1/track-record/headline", params={"days": 90}).json()
    assert "fotmob_5" in {p["match_id"] for p in wide["picks"]}


def test_competition_filter_keeps_the_options(client, seeded):
    body = client.get("/api/v1/track-record/headline", params={"days": 30, "competition_id": "73"}).json()
    assert {p["match_id"] for p in body["picks"]} == {"fotmob_2"}
    assert body["competition_id"] == "73"
    assert body["summary"]["banko"]["lost"] == 1 and body["summary"]["banko"]["won"] == 0
    assert [c["competition_id"] for c in body["by_competition"]] == ["73"]
    # the filter options do not shrink with the filter
    assert {c["id"] for c in body["available_competitions"]} == {"42", "73"}
    assert {c["id"]: c["name"] for c in body["available_competitions"]}["42"] == "Champions League"


def test_by_competition(client, seeded):
    body = client.get("/api/v1/track-record/headline", params={"days": 30}).json()
    rows = {c["competition_id"]: c for c in body["by_competition"]}
    assert rows["42"]["total"] == 6 and rows["73"]["total"] == 2
    assert rows["42"]["banko"]["won"] == 2 and rows["42"]["oranli"]["void"] == 1
    assert rows["73"]["oranli"]["won"] == 1
    assert body["by_competition"][0]["competition_id"] == "42"  # most picks first


def test_by_week_uses_the_monday_of_the_kickoff(client, seeded):
    body = client.get("/api/v1/track-record/headline", params={"days": 30}).json()
    weeks = body["by_week"]
    assert [w["week_start"] for w in weeks] == sorted((w["week_start"] for w in weeks), reverse=True)
    assert all(datetime.fromisoformat(w["week_start"]).weekday() == 0 for w in weeks)
    assert sum(w["banko"]["won"] + w["banko"]["lost"] + w["banko"]["pending"] + w["banko"]["void"] for w in weeks) == 4


def test_pick_items_carry_the_frozen_values(client, seeded):
    body = client.get("/api/v1/track-record/headline", params={"days": 30}).json()
    banko = next(p for p in body["picks"] if p["match_id"] == "fotmob_1" and p["kind"] == "banko")
    assert banko["stage"] == "headline_banko"
    assert banko["market_key"] == "HOME_OR_DRAW" and banko["label"] == "1X"
    assert banko["selection_text"] == "HOME_OR_DRAW (synthetic)"
    assert banko["probability"] == pytest.approx(0.81) and banko["fair_odds"] == pytest.approx(1 / 0.81)
    assert banko["odds"] is None
    assert banko["lineup_type"] == {"home": "confirmed", "away": "predicted", "source": "test"}
    assert banko["model_1x2"] == {"home": 0.5, "draw": 0.3, "away": 0.2}
    assert banko["result"] == "won" and banko["final_score"]["home"] == 2 and banko["settled_at"]
    assert banko["home_team"] == "Home fotmob_1" and banko["competition_id"] == "42"
    assert banko["minutes_before_kickoff"] == 20.0
    pending = next(p for p in body["picks"] if p["match_id"] == "fotmob_4" and p["kind"] == "banko")
    assert pending["result"] is None and pending["final_score"] is None and pending["settled_at"] is None
    void = next(p for p in body["picks"] if p["match_id"] == "fotmob_3" and p["kind"] == "oranli")
    assert void["result"] == "void" and void["final_score"] is None
    kickoffs = [p["kickoff_at"] for p in body["picks"]]
    assert kickoffs == sorted(kickoffs, reverse=True)


def test_invalid_period_is_rejected(client):
    assert client.get("/api/v1/track-record/headline", params={"days": 0}).status_code == 422
    assert client.get("/api/v1/track-record/headline", params={"days": 5000}).status_code == 422


def test_match_headline_record(client, seeded):
    body = client.get("/api/v1/matches/fotmob_1/headline-record").json()
    assert body["frozen"] is True and body["match_id"] == "fotmob_1"
    assert body["picks"]["banko"]["market_key"] == "HOME_OR_DRAW" and body["picks"]["banko"]["result"] == "won"
    assert body["picks"]["oranli"]["market_key"] == "OVER_2_5" and body["picks"]["oranli"]["result"] == "lost"


def test_match_headline_record_accepts_a_bare_fotmob_id_and_unknown_matches(client, factory):
    add_match(factory, "fotmob_777", "42", 1, {"banko": ("HOME_WIN", 0.72)}, {})
    only_banko = client.get("/api/v1/matches/777/headline-record").json()
    assert only_banko["frozen"] is True
    assert only_banko["picks"]["banko"]["market_key"] == "HOME_WIN" and only_banko["picks"]["oranli"] is None
    unknown = client.get("/api/v1/matches/fotmob_404/headline-record")
    assert unknown.status_code == 200
    assert unknown.json() == {"match_id": "fotmob_404", "frozen": False, "picks": {"banko": None, "oranli": None}}


def test_routes_do_not_shadow_the_existing_match_routes():
    paths = {r.path for r in app.routes}
    assert "/api/v1/matches/{match_id}/headline-record" in paths
    assert "/api/v1/matches/{match_id}/prediction" in paths
    assert "/api/v1/matches/{match_id}" in paths


# --------------------------------------------------------------------------- rule versions and Banko tiers


@pytest.fixture
def versioned(factory):
    """Two headline_v1 matches (stored as such, like the night of 2026-10-14) and six current-rule matches."""
    v1 = "headline_v1"
    add_match(factory, "fotmob_11", "42", 2, {"banko": ("HOME_OR_DRAW", 0.81), "oranli": ("BTTS_YES", 0.5)},
              {"banko": "won", "oranli": "lost"}, "Champions League", rule_version=v1)
    add_match(factory, "fotmob_12", "47", 3, {"banko": ("OVER_1_5", 0.88)}, {"banko": "lost"}, "Premier League",
              rule_version=v1)
    add_match(factory, "fotmob_21", "47", 1, {"banko": ("HOME_OR_DRAW", 0.91), "oranli": ("OVER_2_5", 0.58)},
              {"banko": "won", "oranli": "won"}, "Premier League")
    add_match(factory, "fotmob_22", "47", 2, {"banko": ("DRAW_OR_AWAY", 0.86)}, {"banko": "lost"}, "Premier League")
    add_match(factory, "fotmob_23", "47", 2, {"banko": ("HOME_OR_AWAY", 0.85)}, {"banko": "void"}, "Premier League")
    add_match(factory, "fotmob_24", "87", 4, {"banko": ("OVER_1_5", 0.78), "oranli": ("HOME_WIN", 0.6)},
              {"banko": "won", "oranli": "lost"}, "LaLiga")
    add_match(factory, "fotmob_25", "87", -0.1, {"banko": ("HOME_WIN", 0.9)}, {}, "LaLiga")  # pending
    add_match(factory, "fotmob_26", "87", 45, {"banko": ("HOME_OR_DRAW", 0.87)}, {"banko": "won"}, "LaLiga")
    return factory


def counts(summary):
    return {k: summary[k] for k in ("won", "lost", "void", "pending", "settled")}


def test_default_is_the_current_rule_version(client, versioned):
    body = client.get("/api/v1/track-record/headline", params={"days": 30}).json()
    assert body["rule_version"] == body["current_rule_version"] == "headline_v2"
    assert body["available_rule_versions"] == ["headline_v1", "headline_v2"]
    assert {p["match_id"] for p in body["picks"]} == {"fotmob_21", "fotmob_22", "fotmob_23", "fotmob_24", "fotmob_25"}
    assert {p["rule_version"] for p in body["picks"]} == {"headline_v2"}
    assert counts(body["summary"]["banko"]) == {"won": 2, "lost": 1, "void": 1, "pending": 1, "settled": 3}
    assert body["summary"]["banko"]["hit_rate"] == pytest.approx(2 / 3)
    assert counts(body["summary"]["oranli"]) == {"won": 1, "lost": 1, "void": 0, "pending": 0, "settled": 2}
    # the explicit parameter gives the same answer
    explicit = client.get("/api/v1/track-record/headline", params={"days": 30, "rule_version": "headline_v2"}).json()
    assert explicit["summary"] == body["summary"] and explicit["picks"] == body["picks"]


def test_banko_tiers_follow_the_stored_probability(client, versioned):
    body = client.get("/api/v1/track-record/headline", params={"days": 30}).json()
    tiers = body["banko_tiers"]
    assert counts(tiers["cok_guclu"]) == {"won": 1, "lost": 0, "void": 0, "pending": 1, "settled": 1}  # 0.91, 0.90
    assert tiers["cok_guclu"]["hit_rate"] == 1.0
    assert counts(tiers["banko"]) == {"won": 0, "lost": 1, "void": 1, "pending": 0, "settled": 1}  # 0.86, 0.85 void
    assert tiers["banko"]["hit_rate"] == 0.0
    assert counts(tiers["guclu"]) == {"won": 1, "lost": 0, "void": 0, "pending": 0, "settled": 1}  # 0.78
    tier_of = {(p["match_id"], p["kind"]): p["tier"] for p in body["picks"]}
    assert tier_of[("fotmob_21", "banko")] == "cok_guclu"
    assert tier_of[("fotmob_23", "banko")] == "banko"  # exactly 0.85
    assert tier_of[("fotmob_25", "banko")] == "cok_guclu"  # exactly 0.90
    assert tier_of[("fotmob_24", "banko")] == "guclu"
    assert tier_of[("fotmob_21", "oranli")] is None
    # the tiers add up to the Banko summary (every stored probability is inside 0.70-0.95)
    for key in ("won", "lost", "void", "pending"):
        assert sum(t[key] for t in tiers.values()) == body["summary"]["banko"][key]


def test_banko_strong_counts_only_the_bankos_of_at_least_085(client, versioned):
    body = client.get("/api/v1/track-record/headline", params={"days": 30}).json()
    # 21 won (0.91), 22 lost (0.86), 23 void (0.85), 25 pending (0.90); not the guclu 0.78 that won
    strong = body["summary"]["banko_strong"]
    assert counts(strong) == {"won": 1, "lost": 1, "void": 1, "pending": 1, "settled": 2}
    assert strong["hit_rate"] == pytest.approx(0.5)
    assert body["summary"]["banko"]["hit_rate"] == pytest.approx(2 / 3)  # the slot picks, guclu included
    tiers = body["banko_tiers"]
    for key in ("won", "lost", "void", "pending"):
        assert strong[key] == tiers["banko"][key] + tiers["cok_guclu"][key]
    # the same split per competition and per week
    rows = {c["competition_id"]: c for c in body["by_competition"]}
    assert counts(rows["47"]["banko_strong"]) == {"won": 1, "lost": 1, "void": 1, "pending": 0, "settled": 2}
    assert counts(rows["87"]["banko_strong"]) == {"won": 0, "lost": 0, "void": 0, "pending": 1, "settled": 0}
    assert rows["87"]["banko_strong"]["hit_rate"] is None and rows["87"]["banko"]["hit_rate"] == 1.0
    for key in ("won", "lost", "void", "pending"):
        assert sum(w["banko_strong"][key] for w in body["by_week"]) == strong[key]


def test_banko_strong_of_the_old_rule(client, versioned):
    # headline_v1 like the night of 2026-10-14: the slot picks went 1 of 2, the one Banko of >= 0.85 lost
    body = client.get("/api/v1/track-record/headline", params={"days": 30, "rule_version": "headline_v1"}).json()
    assert counts(body["summary"]["banko"]) == {"won": 1, "lost": 1, "void": 0, "pending": 0, "settled": 2}
    assert counts(body["summary"]["banko_strong"]) == {"won": 0, "lost": 1, "void": 0, "pending": 0, "settled": 1}
    assert body["summary"]["banko_strong"]["hit_rate"] == 0.0


def test_banko_progress_counts_every_strong_banko_of_the_version(client, versioned):
    body = client.get("/api/v1/track-record/headline", params={"days": 7, "competition_id": "47"}).json()
    progress = body["banko_progress"]
    # all time and every competition: 21 won, 22 lost, 23 void, 25 pending, 26 won (45 days ago, LaLiga);
    # not the güçlü 0.78 and not the headline_v1 0.88
    assert counts(progress) == {"won": 2, "lost": 1, "void": 1, "pending": 1, "settled": 3}
    assert progress["hit_rate"] == pytest.approx(2 / 3)
    assert progress["target"] == 300 and progress["min_probability"] == 0.85
    assert progress["rule_version"] == "headline_v2"


def test_the_old_rule_stays_viewable(client, versioned):
    body = client.get("/api/v1/track-record/headline", params={"days": 30, "rule_version": "headline_v1"}).json()
    assert body["rule_version"] == "headline_v1" and body["current_rule_version"] == "headline_v2"
    assert {p["match_id"] for p in body["picks"]} == {"fotmob_11", "fotmob_12"}
    assert counts(body["summary"]["banko"]) == {"won": 1, "lost": 1, "void": 0, "pending": 0, "settled": 2}
    assert counts(body["banko_tiers"]["guclu"])["won"] == 1  # 0.81
    assert counts(body["banko_tiers"]["banko"])["lost"] == 1  # 0.88
    assert counts(body["summary"]["oranli"]) == {"won": 0, "lost": 1, "void": 0, "pending": 0, "settled": 1}
    assert counts(body["banko_progress"]) == {"won": 0, "lost": 1, "void": 0, "pending": 0, "settled": 1}
    assert {c["id"] for c in body["available_competitions"]} == {"42", "47"}


def test_all_versions_together(client, versioned):
    body = client.get("/api/v1/track-record/headline", params={"days": 30, "rule_version": "all"}).json()
    assert body["rule_version"] == "all"
    assert len([p for p in body["picks"] if p["kind"] == "banko"]) == 7
    assert counts(body["banko_progress"]) == {"won": 2, "lost": 2, "void": 1, "pending": 1, "settled": 4}


def test_rule_version_parameter_is_validated(client, versioned):
    assert client.get("/api/v1/track-record/headline", params={"rule_version": ""}).status_code == 422
    assert client.get("/api/v1/track-record/headline", params={"rule_version": "a b"}).status_code == 422
    assert client.get("/api/v1/track-record/headline", params={"rule_version": "x" * 65}).status_code == 422
    unknown = client.get("/api/v1/track-record/headline", params={"rule_version": "headline_v9"})
    assert unknown.status_code == 200
    body = unknown.json()
    assert body["picks"] == [] and body["summary"]["banko"]["hit_rate"] is None
    assert body["banko_tiers"]["banko"]["hit_rate"] is None and body["banko_progress"]["settled"] == 0


def test_headline_v1_records_are_never_rewritten(client, versioned):
    def v1_rows():
        with versioned() as session:
            rows = session.execute(
                select(PredictionVersionDB).where(PredictionVersionDB.match_id.in_(["fotmob_11", "fotmob_12"]))
            ).scalars().all()
            return sorted((r.id, r.stage, r.actual_result, json.dumps(r.prediction_data, sort_keys=True)) for r in rows)

    before = v1_rows()
    for version in ("headline_v1", "headline_v2", "all"):
        client.get("/api/v1/track-record/headline", params={"days": 30, "rule_version": version})
    assert v1_rows() == before
    assert all('"rule_version": "headline_v1"' in row[3] for row in before)
    record = client.get("/api/v1/matches/fotmob_11/headline-record").json()
    assert record["picks"]["banko"]["rule_version"] == "headline_v1"
    assert record["picks"]["banko"]["tier"] == "guclu"  # derived on read
    assert record["picks"]["oranli"]["tier"] is None


def test_build_track_record_defaults_to_the_current_rule(versioned):
    from app.prediction.headline_picks import RULE_VERSION
    from app.services.headline_tracking.report import build_track_record

    with versioned() as session:
        default = build_track_record(session, days=30)
        blank = build_track_record(session, days=30, rule_version="  ")
    assert default["rule_version"] == blank["rule_version"] == RULE_VERSION
    assert default["summary"] == blank["summary"]
