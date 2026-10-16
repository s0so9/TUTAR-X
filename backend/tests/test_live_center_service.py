"""Live match centre service + endpoint.

The FotMob bodies below are SYNTHETIC TEST FIXTURES shaped like matchDetails
responses (structure from real responses, values made up). They are not
football data and are never shown to users.
"""

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.services.live_center import service as svc
from app.services.live_center.service import LiveCenterError, LiveCenterService, provider_id_from_match_id
from app.services.team_news.fotmob_client import FetchResult, FotMobBlockedError, FotMobNotFoundError


def _body(match_id="4242", started=True, finished=False, home_score=1, away_score=0, minute="23'"):
    return {
        "general": {
            "matchId": match_id,
            "leagueName": "Test League (synthetic)",
            "matchTimeUTCDate": "2026-10-14T19:00:00.000Z",
            "homeTeam": {"id": 10, "name": "Synthetic Home"},
            "awayTeam": {"id": 20, "name": "Synthetic Away"},
            "started": started,
            "finished": finished,
        },
        "header": {
            "teams": [
                {"id": 10, "name": "Synthetic Home", "score": home_score},
                {"id": 20, "name": "Synthetic Away", "score": away_score},
            ],
            "status": {
                "utcTime": "2026-10-14T19:00:00.000Z",
                "started": started,
                "finished": finished,
                "cancelled": False,
                "liveTime": {"short": minute, "long": minute},
            },
        },
        "content": {},
    }


class FakeClient:
    """Stands in for TeamNewsFotMobClient (no network)."""

    def __init__(self, body=None, exc=None, delay=0.0):
        self.body = body
        self.exc = exc
        self.delay = delay
        self.calls = 0

    async def match_details(self, match_id, ttl_seconds=60.0):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc is not None:
            raise self.exc
        return FetchResult(data=self.body, raw=b"", fetched_at=datetime(2026, 10, 14, 19, 23, tzinfo=timezone.utc))


def test_provider_id_forms():
    assert provider_id_from_match_id("fotmob_6106254") == "6106254"
    assert provider_id_from_match_id("6106254") == "6106254"
    with pytest.raises(LiveCenterError) as err:
        provider_id_from_match_id("not-a-match")
    assert err.value.code == "unknown_match_id" and err.value.status_code == 404


def test_parses_live_body_and_caches():
    client = FakeClient(body=_body())
    now = [1000.0]
    service = LiveCenterService(client=client, clock=lambda: now[0])

    async def run():
        first = await service.get("fotmob_4242")
        second = await service.get("fotmob_4242")
        return first, second

    first, second = asyncio.run(run())
    assert first is second
    assert client.calls == 1
    assert first.match_id == "fotmob_4242"
    assert first.score.home == 1 and first.score.away == 0
    assert first.teams.home.name == "Synthetic Home"
    # nothing invented: sections the body does not carry are listed as missing
    assert first.stats.all == []
    assert {m.section for m in first.missing} >= {"stats", "shotmap", "momentum"}

    now[0] += first.cache_ttl_seconds + 1
    asyncio.run(service.get("fotmob_4242"))
    assert client.calls == 2


def test_concurrent_callers_share_one_fetch():
    client = FakeClient(body=_body(), delay=0.05)
    service = LiveCenterService(client=client)

    async def run():
        return await asyncio.gather(*(service.get("fotmob_4242") for _ in range(5)))

    results = asyncio.run(run())
    assert client.calls == 1
    assert all(r is results[0] for r in results)


@pytest.mark.parametrize(
    "exc,code,status",
    [
        (FotMobBlockedError("403"), "source_blocked", 503),
        (FotMobNotFoundError("404"), "match_not_found_at_source", 404),
    ],
)
def test_source_errors_are_mapped(exc, code, status):
    service = LiveCenterService(client=FakeClient(exc=exc))
    with pytest.raises(LiveCenterError) as err:
        asyncio.run(service.get("fotmob_4242"))
    assert err.value.code == code and err.value.status_code == status


def test_body_for_another_match_is_rejected():
    service = LiveCenterService(client=FakeClient(body=_body(match_id="999")))
    with pytest.raises(LiveCenterError) as err:
        asyncio.run(service.get("fotmob_4242"))
    assert err.value.code == "source_payload_invalid"


def test_endpoint_returns_contract_and_error_codes(monkeypatch):
    from app.main import app

    monkeypatch.setattr(svc, "_service", LiveCenterService(client=FakeClient(body=_body())))
    client = TestClient(app)
    ok = client.get("/api/v1/matches/fotmob_4242/live-center")
    assert ok.status_code == 200
    data = ok.json()
    assert data["match_id"] == "fotmob_4242" and data["provider"] == "fotmob"
    assert data["score"] == {"home": 1, "away": 0}
    assert isinstance(data["missing"], list)

    monkeypatch.setattr(svc, "_service", LiveCenterService(client=FakeClient(exc=FotMobBlockedError("403"))))
    blocked = client.get("/api/v1/matches/fotmob_4242/live-center")
    assert blocked.status_code == 503
    assert blocked.json()["detail"]["error"] == "source_blocked"

    unknown = client.get("/api/v1/matches/xyz/live-center")
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["error"] == "unknown_match_id"


def test_event_descriptions_are_turkish_and_not_duplicated():
    from app.services.live_center.parsers import parse_events

    content = {
        "matchFacts": {
            "events": {
                "events": [
                    {"type": "Goal", "time": 10, "isHome": True, "player": {"id": 1, "name": "Synthetic A"},
                     "goalDescription": "Header", "newScore": [1, 0]},
                    {"type": "Card", "time": 20, "isHome": False, "player": {"id": 2, "name": "Synthetic B"},
                     "card": "Yellow", "cardReason": {"defaultText": "Dissent"}},
                    {"type": "Goal", "time": 30, "isHome": True, "player": {"id": 1, "name": "Synthetic A"},
                     "goalDescriptionKey": "penalty", "goalDescription": "Penalty", "newScore": [2, 0]},
                    {"type": "Card", "time": 40, "isHome": False, "player": {"id": 3, "name": "Synthetic C"},
                     "card": "Yellow", "cardReason": {"defaultText": "Some new reason"}},
                ]
            }
        }
    }
    events = parse_events(content)
    by_minute = {e.minute: e for e in events}
    assert by_minute[10].detail == "Kafa vuruşu"
    assert by_minute[20].detail == "İtiraz"
    assert by_minute[30].type == "penalty_goal" and by_minute[30].detail is None
    assert by_minute[40].detail == "Some new reason"  # unknown text kept as sent
