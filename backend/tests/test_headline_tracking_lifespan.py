"""The FastAPI lifespan starts the headline tracker (on by default) and stops it with the app.

No network: the tracker's tick is replaced by a counter, the database is an in-memory scratch one.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.config import settings
from app.database.models import Base
from app.services.headline_tracking.tracker import HeadlineTracker


@pytest.fixture
def scratch_factory(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    monkeypatch.setattr(main_module, "get_session_factory", lambda: factory)
    yield factory
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def counted_ticks(monkeypatch):
    ticks = []

    async def fake_tick(self, now=None):
        ticks.append(now)
        return {}

    monkeypatch.setattr(HeadlineTracker, "tick", fake_tick)
    return ticks


def wait_for(predicate, seconds=5.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_tracking_is_on_by_default():
    assert settings.headline_tracking_enabled is True


def test_lifespan_runs_the_tracker_when_enabled(scratch_factory, counted_ticks, monkeypatch):
    monkeypatch.setattr(settings, "headline_tracking_enabled", True)
    with TestClient(main_module.app):
        assert wait_for(lambda: len(counted_ticks) >= 1)


def test_lifespan_does_not_start_it_when_disabled(scratch_factory, counted_ticks, monkeypatch):
    monkeypatch.setattr(settings, "headline_tracking_enabled", False)
    with TestClient(main_module.app):
        time.sleep(0.3)
    assert counted_ticks == []


def test_a_crashing_tick_does_not_take_the_app_down(scratch_factory, monkeypatch):
    calls = []

    async def exploding_tick(self, now=None):
        calls.append(1)
        raise RuntimeError("tick exploded")

    monkeypatch.setattr(HeadlineTracker, "tick", exploding_tick)
    monkeypatch.setattr(settings, "headline_tracking_enabled", True)
    monkeypatch.setattr(settings, "headline_tick_seconds", 0.05)
    with TestClient(main_module.app) as client:
        assert wait_for(lambda: len(calls) >= 3)  # kept ticking after failures
        assert client.get("/health").status_code == 200
