"""Team-news endpoints against a scratch in-memory DB (SYNTHETIC data, no network)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.models import Base
from app.database.session import get_db
from app.main import app
from app.services.team_news.service import apply_match_payload, apply_team_payload
from app.services.team_news.store import TeamNewsStore
from tests.test_team_news_fixtures import (
    SYN_AWAY_TEAM,
    SYN_HOME_TEAM,
    syn_player_id,
    synthetic_match_payload,
    synthetic_team_payload,
)
from tests.test_team_news_services import seed_base

UTC = timezone.utc


@pytest.fixture()
def api():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    now = datetime.now(UTC).replace(microsecond=0)
    kickoff = now + timedelta(days=2)
    with factory() as s:
        seed_base(s)
        store = TeamNewsStore(s)
        apply_team_payload(store, synthetic_team_payload(SYN_HOME_TEAM, injured={2: ("30", "Late October 2026")}), now)
        apply_match_payload(
            store,
            synthetic_match_payload(
                6800001,
                kickoff=kickoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
                unavailable={"home": [(2, "injury", "Late October 2026")], "away": []},
            ),
            now,
        )
        s.commit()

    def override():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    try:
        yield TestClient(app), engine
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def test_team_news_endpoint_shape(api):
    client, _ = api
    r = client.get("/api/v1/matches/fotmob_6800001/team-news")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_development_data"] is False
    assert body["match"]["provider_match_id"] == "6800001"
    home = body["home"]
    assert home["team"]["provider_id"] == str(SYN_HOME_TEAM)
    assert home["lineup"]["lineup_type"] == "predicted" and len(home["lineup"]["starters"]) == 11
    starter = home["lineup"]["starters"][0]
    # no finished matches in this scratch DB: explicit nulls + reason, never 0
    assert starter["form"]["apps"] is None and starter["form"]["missing_reason"] == "no_finished_matches_before_kickoff"
    assert home["last5"]["played"] == 0 and home["last5"]["wins"] is None
    assert home["last5"]["missing_reason"] == "no_finished_matches_before_kickoff"
    [absent] = home["absentees"]
    assert absent["player"]["provider_id"] == str(syn_player_id(SYN_HOME_TEAM, 2))
    assert absent["status"] == "injured" and absent["status_label"] == "Sakat"
    assert absent["share"]["goals_share"] is None and absent["share"]["missing_reason"]
    assert body["away"]["absentees"] == [] and body["away"]["absentees_missing_reason"] is None  # list sent, empty
    assert {s["source"] for s in body["sources"]} >= {"fotmob_match_lineup", "fotmob_team_squad"}
    # bare FotMob id works too
    assert client.get("/api/v1/matches/6800001/team-news").status_code == 200


def test_team_news_unknown_match_404(api):
    client, _ = api
    r = client.get("/api/v1/matches/fotmob_999999999/team-news")
    assert r.status_code == 404
    assert r.json()["detail"]["missing_reason"] == "match_not_tracked"


def test_team_squad_endpoint(api):
    client, _ = api
    r = client.get(f"/api/v1/teams/{SYN_HOME_TEAM}/squad")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["season"] == "2026/2027" and len(body["players"]) == 14
    injured = [p for p in body["players"] if p["availability_status"] == "unavailable"]
    assert [p["provider_id"] for p in injured] == [str(syn_player_id(SYN_HOME_TEAM, 2))]
    assert body["players"][0]["market_value_as_of"] is None  # squad sends no valuation date
    away = client.get(f"/api/v1/teams/fotmob_{SYN_AWAY_TEAM}/squad").json()
    assert away["players"] == [] and away["missing_reason"] == "squad_not_observed"
    assert client.get("/api/v1/teams/31337/squad").status_code == 404


def test_endpoints_return_503_before_migration(api):
    client, engine = api
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE lineup_snapshots"))
    r = client.get("/api/v1/matches/fotmob_6800001/team-news")
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "team_news_not_migrated"
