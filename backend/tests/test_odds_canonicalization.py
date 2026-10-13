"""Tests for AverageMarketOdds -> flat canonical odds conversion and the
manual (user-supplied) odds loader.

All odds values below are TEST FIXTURE values, not real market prices.
"""

import importlib.util
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pytest

from app.database.models import AverageMarketOdds, Match, ProviderSource, Team
from app.domain.enums import MatchStatus
from app.services.odds_service import (
    MANUAL_ODDS_SOURCE,
    ODDS_API_AVERAGE_SOURCE,
    OddsService,
    build_canonical_odds_quotes,
    canonicalize_average_odds,
    line_suffix,
    load_canonical_odds_quotes,
    manual_provider_event_id,
    map_h2h_outcome_names,
    outcome_odds_fields,
)

T0 = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


@dataclass
class FakeRow:
    """Minimal AverageMarketOdds-like row (test fixture)."""

    market_key: str
    outcome_name: str
    average_odds: float
    market_point: Optional[float] = None
    provider_event_id: str = "oddsapi_event_test"
    bookmakers: List[str] = field(default_factory=lambda: ["bookie_a", "bookie_b"])
    bookmaker_count: int = 2
    calculated_at: Optional[datetime] = T0


def _odds_api_rows(home="Arsenal", away="Lille OSC"):
    return [
        FakeRow("h2h", home, 1.22),
        FakeRow("h2h", "Draw", 5.8),
        FakeRow("h2h", away, 12.5),
        FakeRow("totals", "Over", 1.5, 2.5),
        FakeRow("totals", "Under", 2.5, 2.5),
        FakeRow("totals", "Over", 1.1, 1.5),
        FakeRow("totals", "Under", 6.0, 1.5),
        FakeRow("totals", "Over", 2.2, 3.5),
        FakeRow("btts", "Yes", 2.1),
        FakeRow("btts", "No", 1.65),
    ]


class TestCanonicalConversion:
    def test_odds_api_rows_to_flat_canonical_dict(self):
        result = canonicalize_average_odds(_odds_api_rows(), "Arsenal", "Lille")
        assert result == {
            "HOME_WIN": 1.22,
            "DRAW": 5.8,
            "AWAY_WIN": 12.5,
            "OVER_2_5": 1.5,
            "UNDER_2_5": 2.5,
            "OVER_1_5": 1.1,
            "UNDER_1_5": 6.0,
            "OVER_3_5": 2.2,
            "BTTS_YES": 2.1,
            "BTTS_NO": 1.65,
        }

    def test_h2h_tolerates_case_and_diacritics_and_row_order(self):
        rows = [
            FakeRow("h2h", "MANCHESTER UNITED", 3.8),
            FakeRow("h2h", "draw", 3.85),
            FakeRow("h2h", "Atletico Madrid", 1.93),
        ]
        result = canonicalize_average_odds(rows, "Atlético Madrid", "Manchester United")
        assert result == {"HOME_WIN": 1.93, "DRAW": 3.85, "AWAY_WIN": 3.8}

    def test_h2h_turkish_characters(self):
        rows = [
            FakeRow("h2h", "Galatasaray", 8.5),
            FakeRow("h2h", "Draw", 6.5),
            FakeRow("h2h", "Barcelona", 1.27),
        ]
        result = canonicalize_average_odds(rows, "Galatasaray A.Ş.", "FC Barcelona")
        assert result["HOME_WIN"] == 8.5
        assert result["AWAY_WIN"] == 1.27

    def test_h2h_unrelated_teams_are_not_guessed(self):
        mapping = map_h2h_outcome_names(
            ["Paris Saint Germain", "Manchester City", "Draw"],
            "Manchester United",
            "Liverpool",
        )
        assert mapping == {"Draw": "DRAW"}

    def test_h2h_without_team_names_only_maps_draw(self):
        result = canonicalize_average_odds(_odds_api_rows(), None, None)
        assert "HOME_WIN" not in result and "AWAY_WIN" not in result
        assert result["DRAW"] == 5.8

    def test_invalid_and_unknown_rows_are_skipped(self):
        rows = [
            FakeRow("h2h", "Draw", 1.0),           # not a valid decimal price
            FakeRow("totals", "Over", 1.8, None),  # totals without a line
            FakeRow("spreads", "Arsenal", 1.9, -1.5),
            FakeRow("btts", "Maybe", 2.0),
            FakeRow("btts", "Yes", 0.0),
        ]
        assert canonicalize_average_odds(rows, "Arsenal", "Lille") == {}

    def test_empty_rows_give_empty_dict(self):
        assert canonicalize_average_odds([], "Arsenal", "Lille") == {}

    def test_most_recent_row_wins(self):
        rows = [
            FakeRow("btts", "Yes", 2.3, calculated_at=T0 + timedelta(hours=1)),
            FakeRow("btts", "Yes", 2.0, calculated_at=T0),
        ]
        assert canonicalize_average_odds(rows, "A", "B") == {"BTTS_YES": 2.3}

    def test_source_labels(self):
        rows = [
            FakeRow("btts", "Yes", 2.1, provider_event_id=manual_provider_event_id("fotmob_1"),
                    bookmakers=[MANUAL_ODDS_SOURCE], bookmaker_count=1),
            FakeRow("btts", "No", 1.65),
        ]
        quotes = build_canonical_odds_quotes(rows, "A", "B")
        assert quotes["BTTS_YES"].source == MANUAL_ODDS_SOURCE
        assert quotes["BTTS_NO"].source == ODDS_API_AVERAGE_SOURCE

    def test_line_suffix_matches_selector_keys(self):
        # SmartMarketSelector builds f"OVER_{line}".replace(".", "_") with float lines
        for line in (0.5, 1.5, 2.5, 3.5, 3.0):
            assert f"OVER_{line_suffix(line)}" == f"OVER_{line}".replace(".", "_")

    def test_flat_dict_is_consumed_by_odds_service(self):
        flat = canonicalize_average_odds(_odds_api_rows(), "Arsenal", "Lille")
        market_odds = OddsService.get_market_odds(flat, "HOME_WIN")
        assert market_odds.odds == 1.22
        assert OddsService.get_market_odds(flat, "OVER_2_5").odds == 1.5
        assert OddsService.get_market_odds(flat, "HOME_OR_DRAW").odds is None


class TestOutcomeOddsFields:
    def test_missing_quote_keeps_everything_none(self):
        fields = outcome_odds_fields(0.7, None)
        assert set(fields.values()) == {None}

    def test_fields_from_quote(self):
        quote = build_canonical_odds_quotes([FakeRow("totals", "Over", 1.5, 2.5)], "A", "B")["OVER_2_5"]
        fields = outcome_odds_fields(0.70, quote)
        assert fields["real_odds"] == 1.5
        assert fields["implied_probability"] == pytest.approx(1 / 1.5)
        # market_analysis convention: edge = implied - model
        assert fields["market_edge"] == pytest.approx(1 / 1.5 - 0.70)
        assert fields["expected_value"] == pytest.approx(0.70 * 1.5 - 1)
        assert fields["expected_value_percent"] == pytest.approx((0.70 * 1.5 - 1) * 100)
        assert fields["bookmaker"] == ODDS_API_AVERAGE_SOURCE
        assert fields["value_classification"] in {"NO_VALUE", "LOW_VALUE", "VALUE", "STRONG_VALUE"}


def _load_loader_module():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "load_manual_odds.py")
    spec = importlib.util.spec_from_file_location("load_manual_odds_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # required for dataclasses in the module
    spec.loader.exec_module(module)
    return module


def _seed_fixture(db_session):
    """Development/test fixture: one provider, two teams, one scheduled match."""
    provider = ProviderSource(name="fotmob")
    db_session.add(provider)
    db_session.flush()
    home = Team(provider_source_id=provider.id, provider_id="9825", name="Arsenal")
    away = Team(provider_source_id=provider.id, provider_id="8639", name="Lille")
    db_session.add_all([home, away])
    db_session.flush()
    match = Match(
        provider_source_id=provider.id,
        provider_id="5550001",
        home_team_id=home.id,
        away_team_id=away.id,
        scheduled_at=T0,
        status=MatchStatus.SCHEDULED,
    )
    db_session.add(match)
    db_session.commit()
    return home, away, match


TEST_PAYLOAD = {
    "source": "unit-test fixture (not real odds)",
    "matches": [
        {
            "match_id": "fotmob_5550001",
            "label": "Arsenal - Lille",
            "odds_1": 1.22, "odds_x": 5.8, "odds_2": 12.5,
            "over_2_5": 1.5, "under_2_5": 2.5,
            "btts_yes": 2.1, "btts_no": None,
        },
        {
            "match_id": "fotmob_7770001",
            "label": "Inter - Club Brugge",
            "odds_1": 1.25, "odds_x": 6.5, "odds_2": 11.5,
            "over_2_5": 1.33, "under_2_5": 3.2,
            "btts_yes": 1.7, "btts_no": 2.1,
        },
    ],
}


class TestManualOddsLoader:
    def test_load_and_read_back_through_converter(self, db_session):
        loader = _load_loader_module()
        home, away, match = _seed_fixture(db_session)

        results = loader.load_manual_odds(db_session, TEST_PAYLOAD, api_base=None, calculated_at=T0)
        db_session.commit()

        by_id = {r.match_id: r for r in results}
        stored = by_id["fotmob_5550001"]
        assert stored.teams.db_match_id == match.id          # FK-safe: canonical matches.id
        assert stored.teams.resolved_from == "matches_table"
        assert stored.created == 6                           # btts_no was null -> skipped
        assert stored.skipped_fields == ["btts_no"]

        unknown = by_id["fotmob_7770001"]
        assert unknown.teams.db_match_id is None             # not in matches table -> NULL FK
        assert unknown.teams.resolved_from == "label"
        assert unknown.created == 7

        rows = db_session.query(AverageMarketOdds).all()
        assert len(rows) == 13
        assert all(r.bookmakers == [MANUAL_ODDS_SOURCE] for r in rows)
        assert all(r.bookmaker_count == 1 and r.min_odds == r.max_odds == r.average_odds for r in rows)

        quotes = load_canonical_odds_quotes(
            db_session, ["fotmob_5550001", match.id], home.id, away.id
        )
        assert {k: q.odds for k, q in quotes.items()} == {
            "HOME_WIN": 1.22, "DRAW": 5.8, "AWAY_WIN": 12.5,
            "OVER_2_5": 1.5, "UNDER_2_5": 2.5, "BTTS_YES": 2.1,
        }
        assert {q.source for q in quotes.values()} == {MANUAL_ODDS_SOURCE}

        # Fixture without a matches row is still found through provider_event_id
        quotes_unknown = load_canonical_odds_quotes(db_session, ["fotmob_7770001"])
        assert quotes_unknown["DRAW"].odds == 6.5
        assert quotes_unknown["OVER_2_5"].odds == 1.33
        assert "HOME_WIN" not in quotes_unknown  # no team ids given -> not guessed

    def test_reload_is_idempotent_upsert(self, db_session):
        loader = _load_loader_module()
        _seed_fixture(db_session)
        loader.load_manual_odds(db_session, TEST_PAYLOAD, api_base=None, calculated_at=T0)
        db_session.commit()

        changed = {"source": "x", "matches": [dict(TEST_PAYLOAD["matches"][0], odds_1=1.25)]}
        results = loader.load_manual_odds(db_session, changed, api_base=None, calculated_at=T0 + timedelta(hours=1))
        db_session.commit()

        assert results[0].created == 0 and results[0].updated == 6
        assert db_session.query(AverageMarketOdds).count() == 13
        home_row = db_session.query(AverageMarketOdds).filter(
            AverageMarketOdds.provider_event_id == manual_provider_event_id("fotmob_5550001"),
            AverageMarketOdds.outcome_name == "Arsenal",
        ).one()
        assert home_row.average_odds == 1.25

    def test_no_odds_rows_means_no_quotes(self, db_session):
        home, away, match = _seed_fixture(db_session)
        assert load_canonical_odds_quotes(db_session, [match.id], home.id, away.id) == {}
        assert load_canonical_odds_quotes(None, [match.id]) == {}


# ---------------------------------------------------------------------------
# Double chance, stricter h2h elimination, per-event h2h mapping
# ---------------------------------------------------------------------------


class TestDoubleChanceAndH2HSafety:
    def test_double_chance_rows_map_to_selector_keys(self):
        rows = [
            FakeRow("double_chance", "1X", 1.05),
            FakeRow("double_chance", "12", 1.12),
            FakeRow("double_chance", "x2", 4.2),
            FakeRow("double_chance", "2X", 3.0),   # unknown outcome -> skipped
        ]
        result = canonicalize_average_odds(rows, "Arsenal", "Lille")
        assert result == {"HOME_OR_DRAW": 1.05, "HOME_OR_AWAY": 1.12, "DRAW_OR_AWAY": 4.2}
        # Keys are exactly the ones SmartMarketSelector looks up
        assert OddsService.get_market_odds(result, "HOME_OR_DRAW").odds == 1.05
        assert OddsService.get_market_odds(result, "DRAW_OR_AWAY").odds == 4.2

    def test_unrelated_club_is_not_assigned_by_elimination(self):
        assert map_h2h_outcome_names(
            ["Galatasaray", "Draw", "Fenerbahce"], "Galatasaray", "Barcelona"
        ) == {"Draw": "DRAW"}
        assert map_h2h_outcome_names(
            ["Liverpool", "Draw", "Arsenal"], "Arsenal", "Lille"
        ) == {"Draw": "DRAW"}

    def test_abbreviation_still_maps_by_elimination(self):
        mapping = map_h2h_outcome_names(
            ["Atletico Madrid", "Draw", "Man Utd"], "Atlético Madrid", "Manchester United"
        )
        assert mapping == {"Atletico Madrid": "HOME_WIN", "Draw": "DRAW", "Man Utd": "AWAY_WIN"}

    def test_h2h_mapped_per_event_and_most_recent_wins(self):
        rows = [
            # Older Odds API event with full names (test fixture prices)
            FakeRow("h2h", "Arsenal FC", 1.30, provider_event_id="oddsapi_1", calculated_at=T0),
            FakeRow("h2h", "Lille OSC", 11.0, provider_event_id="oddsapi_1", calculated_at=T0),
            # Newer manual event with DB names
            FakeRow("h2h", "Arsenal", 1.22, provider_event_id=manual_provider_event_id("fotmob_1"),
                    bookmakers=[MANUAL_ODDS_SOURCE], calculated_at=T0 + timedelta(hours=1)),
            FakeRow("h2h", "Lille", 12.5, provider_event_id=manual_provider_event_id("fotmob_1"),
                    bookmakers=[MANUAL_ODDS_SOURCE], calculated_at=T0 + timedelta(hours=1)),
        ]
        quotes = build_canonical_odds_quotes(rows, "Arsenal", "Lille")
        assert quotes["HOME_WIN"].odds == 1.22 and quotes["HOME_WIN"].source == MANUAL_ODDS_SOURCE
        assert quotes["AWAY_WIN"].odds == 12.5


SAMPLE_REPORT_MD = """# Test report (fixture, not real odds)

## 1. Temel Maç Oranları (1X2 & Çifte Şans)

| Bahis Pazarı | Seçenek | Oran (Ortalama) | Oran Aralığı | İma Edilen Olasılık |
| :--- | :--- | :--- | :--- | :--- |
| **Maç Sonucu (1X2)** | **Ev Galibiyeti (1)** | **1.22** | 1.19 - 1.26 | %82 |
| | Beraberlik (X) | 5.80 | 4.90 - 6.50 | %13 |
| | Deplasman (2) | 12.50 | 11.00 - 14.00 | %5 |
| **Çifte Şans** | **1X (Ev veya Beraberlik)** | **1.05** | 1.03 - 1.07 | %95 |
| | 12 (Ev veya Deplasman) | 1.12 | 1.10 - 1.15 | %89 |
| | X2 (Beraberlik veya Deplasman) | 4.20 | 3.80 - 4.50 | %24 |

## 2. Gol Piyasaları

| Bahis Pazarı | Seçenek | Oran (Ortalama) | Açıklama |
| :--- | :--- | :--- | :--- |
| **2.5 Gol Alt/Üst** | **2.5 Gol Üst** | **1.50** (-200) | x |
| | 2.5 Gol Alt | 2.50 (+150) | x |
| **3.5 Gol Alt/Üst** | 3.5 Gol Üst | 2.25 | x |
| | **3.5 Gol Alt** | **1.58** (-175) | x |
| **Karşılıklı Gol (KG)** | KG Var (İki takım da atar) | 2.10 (+110) | x |
| | **KG Yok** | **1.65** (-154) | x |

## 3. Handikap & İlk Yarı Oranları

| Bahis Pazarı | Seçenek | Oran | Detay |
| :--- | :--- | :--- | :--- |
| **Asya Handikap** | **Ev (-1.5)** | **1.70** | x |
| **İlk Yarı Sonucu (İY)** | **İY 1 (Ev Önde)** | **1.60** | x |
| | İY X (Beraberlik) | 2.75 | x |
| **İlk Yarı / Maç Sonu** | **1 / 1** | **1.68** | x |

* **Ev Toplam Gol 1.5 Üst:** ~1.35
"""

EXPECTED_SAMPLE_PRICES = {
    "odds_1": 1.22, "odds_x": 5.8, "odds_2": 12.5,
    "dc_1x": 1.05, "dc_12": 1.12, "dc_x2": 4.2,
    "over_2_5": 1.5, "under_2_5": 2.5, "over_3_5": 2.25, "under_3_5": 1.58,
    "btts_yes": 2.1, "btts_no": 1.65,
}


class TestMarkdownReportParsing:
    def test_parses_only_explicit_markets(self):
        loader = _load_loader_module()
        # First-half, HT/FT, handicap and "~" team specials are not parsed
        assert loader.parse_odds_markdown(SAMPLE_REPORT_MD) == EXPECTED_SAMPLE_PRICES

    def test_folder_files_must_agree(self, tmp_path):
        loader = _load_loader_module()
        folder = tmp_path / "home-away"
        folder.mkdir()
        (folder / "home.md").write_text(SAMPLE_REPORT_MD, encoding="utf-8")
        (folder / "away.md").write_text(
            SAMPLE_REPORT_MD.replace("**1.05**", "**1.07**"), encoding="utf-8"
        )
        with pytest.raises(loader.MarkdownOddsError):
            loader.odds_from_markdown_folder(str(folder))

    def test_merge_fills_missing_and_rejects_mismatch(self, tmp_path):
        loader = _load_loader_module()
        folder = tmp_path / "home-away"
        folder.mkdir()
        (folder / "home.md").write_text(SAMPLE_REPORT_MD, encoding="utf-8")

        payload = {"matches": [{"match_id": "fotmob_1", "folder": "home-away", "odds_1": 1.22}]}
        loader.merge_markdown_odds(payload, str(tmp_path))
        assert {k: payload["matches"][0][k] for k in EXPECTED_SAMPLE_PRICES} == EXPECTED_SAMPLE_PRICES

        bad = {"matches": [{"match_id": "fotmob_1", "folder": "home-away", "odds_1": 1.30}]}
        with pytest.raises(loader.MarkdownOddsError):
            loader.merge_markdown_odds(bad, str(tmp_path))

    def test_loader_stores_double_chance_and_3_5_and_reads_back(self, db_session):
        loader = _load_loader_module()
        home, away, match = _seed_fixture(db_session)
        entry = dict(EXPECTED_SAMPLE_PRICES, match_id="fotmob_5550001", label="Arsenal - Lille")
        results = loader.load_manual_odds(db_session, {"matches": [entry]}, api_base=None, calculated_at=T0)
        db_session.commit()
        assert results[0].created == 12 and results[0].skipped_fields == []

        dc_rows = db_session.query(AverageMarketOdds).filter(
            AverageMarketOdds.market_key == "double_chance"
        ).all()
        assert sorted(r.outcome_name for r in dc_rows) == ["12", "1X", "X2"]

        quotes = load_canonical_odds_quotes(db_session, [match.id], home.id, away.id)
        assert {k: q.odds for k, q in quotes.items()} == {
            "HOME_WIN": 1.22, "DRAW": 5.8, "AWAY_WIN": 12.5,
            "HOME_OR_DRAW": 1.05, "HOME_OR_AWAY": 1.12, "DRAW_OR_AWAY": 4.2,
            "OVER_2_5": 1.5, "UNDER_2_5": 2.5, "OVER_3_5": 2.25, "UNDER_3_5": 1.58,
            "BTTS_YES": 2.1, "BTTS_NO": 1.65,
        }


class TestPickOddsSource:
    def test_pick_gets_source_of_its_market(self):
        from app.api.v1.endpoints.matches import _annotate_pick_odds_source

        quotes = build_canonical_odds_quotes(
            [FakeRow("btts", "Yes", 2.1, provider_event_id=manual_provider_event_id("fotmob_1"),
                     bookmakers=[MANUAL_ODDS_SOURCE])],
            "A", "B",
        )
        pick = {"market": "BTTS_YES", "bookmaker_odds": 2.1, "pass_decision": False}
        annotated = _annotate_pick_odds_source(pick, quotes)
        assert annotated["odds_source"] == MANUAL_ODDS_SOURCE
        assert "odds_source" not in pick  # original dict untouched

        unpriced = _annotate_pick_odds_source(
            {"market": "OVER_1_5", "bookmaker_odds": None, "pass_decision": False}, quotes
        )
        assert unpriced["odds_source"] is None
        passed = {"pass_decision": True, "pass_reason": "insufficient_value"}
        assert _annotate_pick_odds_source(passed, quotes) == passed
        assert _annotate_pick_odds_source(None, quotes) is None
