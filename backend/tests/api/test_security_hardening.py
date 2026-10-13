"""Security hardening tests.

Covers:
- POST /api/v1/odds/manual-update fails closed when FI_ADMIN_TOKEN is unset
  (it triggers paid The Odds API calls) and enforces the token when set.
- GET /health never echoes raw database exception text.
- The Odds API key is redacted from logged exception messages.

No real network or database access: the odds updater and session factory are
patched with test doubles.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database.session import get_db
from app.routers import odds as odds_router_module


ADMIN_TOKEN_FOR_TESTS = "test-admin-token-not-a-real-secret"


@pytest.fixture
def odds_client(monkeypatch):
    """Minimal app with only the odds router and a stubbed DB dependency."""
    app = FastAPI()
    app.include_router(odds_router_module.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: MagicMock()

    # Track whether the paid update path is ever reached.
    update_all_mock = MagicMock(return_value={"updated": 0, "note": "test double"})
    monkeypatch.setattr(
        "app.services.odds_updater_service.update_all_odds", update_all_mock
    )
    client = TestClient(app)
    client.update_all_mock = update_all_mock
    return client


class TestManualOddsUpdateAuth:
    """Fail-closed admin auth on the manual odds update endpoint."""

    @pytest.mark.parametrize("unset_value", ["", "   ", None])
    def test_rejects_when_admin_token_not_configured(self, odds_client, monkeypatch, unset_value):
        monkeypatch.setattr(odds_router_module.settings, "FI_ADMIN_TOKEN", unset_value)

        response = odds_client.post(
            "/api/v1/odds/manual-update",
            headers={"Authorization": "Bearer anything"},
        )

        assert response.status_code == 503
        assert "FI_ADMIN_TOKEN" in response.json()["detail"]
        odds_client.update_all_mock.assert_not_called()

    def test_rejects_without_header_when_token_unset(self, odds_client, monkeypatch):
        monkeypatch.setattr(odds_router_module.settings, "FI_ADMIN_TOKEN", "")

        response = odds_client.post("/api/v1/odds/manual-update")

        assert response.status_code == 503
        odds_client.update_all_mock.assert_not_called()

    def test_requires_authorization_header(self, odds_client, monkeypatch):
        monkeypatch.setattr(odds_router_module.settings, "FI_ADMIN_TOKEN", ADMIN_TOKEN_FOR_TESTS)

        response = odds_client.post("/api/v1/odds/manual-update")

        assert response.status_code == 401
        odds_client.update_all_mock.assert_not_called()

    def test_rejects_wrong_token(self, odds_client, monkeypatch):
        monkeypatch.setattr(odds_router_module.settings, "FI_ADMIN_TOKEN", ADMIN_TOKEN_FOR_TESTS)

        response = odds_client.post(
            "/api/v1/odds/manual-update",
            headers={"Authorization": "Bearer wrong-token"},
        )

        assert response.status_code == 403
        odds_client.update_all_mock.assert_not_called()

    def test_rejects_non_ascii_token_without_server_error(self, odds_client, monkeypatch):
        monkeypatch.setattr(odds_router_module.settings, "FI_ADMIN_TOKEN", ADMIN_TOKEN_FOR_TESTS)

        response = odds_client.post(
            "/api/v1/odds/manual-update",
            # Raw UTF-8 bytes: the server decodes headers as latin-1, giving a
            # non-ASCII str that would make str-based compare_digest raise.
            headers={"Authorization": "Bearer ğüşİ".encode("utf-8")},
        )

        assert response.status_code == 403
        odds_client.update_all_mock.assert_not_called()

    @pytest.mark.parametrize(
        "header_value",
        [
            f"Bearer {ADMIN_TOKEN_FOR_TESTS}",
            f"bearer {ADMIN_TOKEN_FOR_TESTS}",
            ADMIN_TOKEN_FOR_TESTS,
        ],
    )
    def test_accepts_valid_token(self, odds_client, monkeypatch, header_value):
        monkeypatch.setattr(odds_router_module.settings, "FI_ADMIN_TOKEN", ADMIN_TOKEN_FOR_TESTS)

        response = odds_client.post(
            "/api/v1/odds/manual-update",
            headers={"Authorization": header_value},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        odds_client.update_all_mock.assert_called_once()


class TestHealthDoesNotLeakErrors:
    """/health must not return raw database exception text."""

    def test_db_error_text_not_exposed(self, monkeypatch):
        from app.main import app

        secret_detail = "postgresql://admin:SuperSecretPw@db.internal:5432/fi"

        def broken_session_factory():
            raise RuntimeError(f"could not connect to {secret_detail}")

        monkeypatch.setattr(
            "app.database.session.get_session_factory", broken_session_factory
        )

        response = TestClient(app).get("/health")

        assert response.status_code == 200
        body = response.text
        assert "SuperSecretPw" not in body
        assert secret_detail not in body
        data = response.json()
        assert data["database"] == "connection_failed"
        assert data["status"] == "degraded"
        assert data["database_details"]["connection_verified"] is False


class TestOddsApiKeyRedaction:
    """The Odds API key must never appear in log messages."""

    def test_redacts_query_param_and_literal_key(self):
        from app.providers.odds_api_provider import redact_api_key

        key = "abc123DEVKEYnotreal"
        message = (
            "HTTPSConnectionPool(host='api.the-odds-api.com', port=443): Max retries "
            f"exceeded with url: /v4/sports/soccer_epl/odds?apiKey={key}&regions=eu"
        )

        redacted = redact_api_key(message, key)

        assert key not in redacted
        assert "apiKey=***REDACTED***&regions=eu" in redacted
        assert redact_api_key(f"plain {key} text", key) == "plain ***REDACTED*** text"

    def test_request_exception_log_is_redacted(self, monkeypatch, caplog):
        import logging

        import requests

        from app.providers import odds_api_provider as provider_module

        key = "abc123DEVKEYnotreal"
        provider = provider_module.TheOddsAPIProvider()
        provider.api_key = key
        provider.enabled = True

        def failing_get(url, params=None, timeout=None):
            raise requests.exceptions.ConnectionError(
                f"Max retries exceeded with url: /v4/sports?apiKey={params['apiKey']}"
            )

        monkeypatch.setattr(provider_module.requests, "get", failing_get)

        with caplog.at_level(logging.ERROR, logger=provider_module.__name__):
            assert provider.get_available_sports() is None
            assert provider.check_quota() == (False, None)

        assert caplog.records, "expected error logs from failed requests"
        assert key not in caplog.text
        assert "***REDACTED***" in caplog.text
