"""Read side of the headline tracking: the track record and the frozen picks of one match.

Reads prediction_versions only (no network). A pick that is not settled yet is "pending" and is
not part of any hit rate; void picks (cancelled match, extra time) are counted separately and are
not part of it either. hit_rate = won / (won + lost), None while nothing is settled.

Every frozen pick carries the rule version it was picked with (prediction_data.rule_version). The
track record shows one rule version at a time (default: the current RULE_VERSION; "all" = every
version), so the headline_v1 picks (Oranli floor 0.45, no tiers) never mix with the headline_v2
picks. The Banko tier of a pick is derived from its stored probability with the thresholds of
app/prediction/headline_picks.py (banko_tier), so headline_v1 records get tiers too - nothing is
written back to the database.

The summary, every by_competition row and every by_week row carry "banko_strong" next to "banko":
the Bankos with p >= 0.85 only (tiers banko + cok_guclu), the figure a ~90 % claim is about. "banko"
still counts every frozen Banko slot pick, the "guclu" (0.70-0.85, not a Banko) ones included.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import PredictionVersionDB
from app.prediction.headline_picks import (
    BANKO_TIERS,
    KNOWN_RULE_VERSIONS,
    RULE_VERSION,
    TIER_BANKO,
    TIER_BANKO_MIN_P,
    TIER_COK_GUCLU,
    banko_tier,
    short_label,
)
from app.services.headline_tracking.records import (
    HEADLINE_STAGES,
    KIND_BY_STAGE,
    KINDS,
    STAGE_BY_KIND,
    RESULT_LOST,
    RESULT_VOID,
    RESULT_WON,
    as_utc,
    iso,
    parse_iso,
    utc_now,
)

#: Query value of the rule-version filter that keeps every version.
ALL_RULE_VERSIONS = "all"

#: Recorded Bankos (p >= 0.85) needed before a ~90 % hit rate means something: with 270 of 300 the 90 %
#: Wilson interval is 0.8678-0.925 (backend/data/research/roadmap_live_sample_size.json ->
#: by_sample_size[n_picks == 300].wilson90_if_observed_0.90; roadmap section 1: "yaklasik 300 kayitli Banko").
BANKO_PROOF_TARGET = 300

# Names of the featured competitions when a record carries none (FotMob league ids).
FEATURED_COMPETITION_NAMES: Dict[str, str] = {
    "47": "Premier League", "87": "LaLiga", "55": "Serie A", "54": "Bundesliga", "53": "Ligue 1",
    "57": "Eredivisie", "61": "Liga Portugal", "40": "Belgian Pro League", "71": "Süper Lig",
    "122": "Scottish Premiership", "42": "Champions League", "73": "Europa League",
    "10216": "Conference League",
}


def row_to_item(row: PredictionVersionDB) -> Dict[str, Any]:
    data = row.prediction_data or {}
    kickoff = parse_iso(data.get("kickoff_at"))
    competition_id = data.get("competition_id")
    competition_name = data.get("competition_name") or FEATURED_COMPETITION_NAMES.get(str(competition_id))
    key = row.selected_market or ""
    kind = KIND_BY_STAGE.get(row.stage, row.stage)
    return {
        "id": row.id,
        "match_id": row.match_id,
        "kind": kind,
        "stage": row.stage,
        "home_team": data.get("home_team"),
        "away_team": data.get("away_team"),
        "competition_id": str(competition_id) if competition_id is not None else None,
        "competition_name": competition_name,
        "kickoff_at": iso(kickoff),
        "frozen_at": data.get("frozen_at") or iso(as_utc(row.created_at)),
        "minutes_before_kickoff": data.get("minutes_before_kickoff"),
        "market_key": key,
        "label": short_label(key),
        "selection_text": row.selection_text,
        "market_name": data.get("market_name"),
        "probability": row.selection_probability,
        "fair_odds": row.selection_fair_odds,
        "odds": row.selection_odds,
        "lineup_type": data.get("lineup_type") or {"home": None, "away": None, "source": None},
        "model_1x2": data.get("model_1x2"),
        "result": row.actual_result,
        "final_score": data.get("final_score"),
        "settled_at": iso(as_utc(row.settled_at)),
        "source": data.get("source"),
        "rule_version": data.get("rule_version"),
        # Banko tier from the stored probability (None for the Oranli and outside 0.70-0.95)
        "tier": banko_tier(row.selection_probability) if kind == "banko" else None,
    }


def _sort_key(item: Dict[str, Any]) -> str:
    return item["kickoff_at"] or item["frozen_at"] or ""


def kind_summary(items: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    won = lost = void = pending = 0
    for item in items:
        result = item["result"]
        if result == RESULT_WON:
            won += 1
        elif result == RESULT_LOST:
            lost += 1
        elif result == RESULT_VOID:
            void += 1
        else:
            pending += 1
    settled = won + lost
    return {"won": won, "lost": lost, "void": void, "pending": pending, "settled": settled,
            "hit_rate": (won / settled) if settled else None}


#: The Banko tiers that are a Banko proper (p >= 0.85); "guclu" (0.70-0.85) is shown but is not a Banko.
STRONG_BANKO_TIERS = (TIER_BANKO, TIER_COK_GUCLU)


def _is_strong_banko(item: Dict[str, Any]) -> bool:
    return item["kind"] == "banko" and item["tier"] in STRONG_BANKO_TIERS


def _both(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Banko and Oranli summaries, plus banko_strong: the Bankos with p >= 0.85 only (tiers banko +
    cok_guclu). The "banko" summary counts every Banko slot pick, the guclu ones included."""
    summaries = {kind: kind_summary(i for i in items if i["kind"] == kind) for kind in KINDS}
    summaries["banko_strong"] = kind_summary(i for i in items if _is_strong_banko(i))
    return summaries


def _tiers(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Banko summary per tier (cok_guclu, banko, guclu); a Banko without a tier is in none of them."""
    bankos = [i for i in items if i["kind"] == "banko"]
    return {tier: kind_summary(i for i in bankos if i["tier"] == tier) for tier in BANKO_TIERS}


def _matches_rule_version(item: Dict[str, Any], rule_version: str) -> bool:
    return rule_version == ALL_RULE_VERSIONS or item["rule_version"] == rule_version


def _week_start(item: Dict[str, Any]) -> Optional[str]:
    moment = parse_iso(item["kickoff_at"]) or parse_iso(item["frozen_at"])
    if moment is None:
        return None
    day = moment.date()
    return (day - timedelta(days=day.weekday())).isoformat()


def load_items(session: Session, since: Optional[datetime]) -> List[Dict[str, Any]]:
    stmt = select(PredictionVersionDB).where(PredictionVersionDB.stage.in_(HEADLINE_STAGES))
    if since is not None:
        # frozen at most a few hours before kick-off: a generous created_at pre-filter, the exact
        # kick-off filter follows in Python (the kick-off lives in the JSON column)
        stmt = stmt.where(PredictionVersionDB.created_at >= (since - timedelta(days=2)).replace(tzinfo=None))
    items = [row_to_item(r) for r in session.execute(stmt).scalars().all()]
    if since is not None:
        items = [i for i in items if (parse_iso(i["kickoff_at"]) or parse_iso(i["frozen_at"]) or since) >= since]
    return sorted(items, key=_sort_key, reverse=True)


def banko_progress(session: Session, rule_version: str) -> Dict[str, Any]:
    """Every recorded Banko with p >= 0.85 (tiers banko + cok_guclu) of a rule version, over all time and
    every competition: how far the record is from the ~300 needed to check a ~90 % hit rate."""
    stmt = select(PredictionVersionDB).where(
        PredictionVersionDB.stage == STAGE_BY_KIND["banko"],
        PredictionVersionDB.selection_probability >= TIER_BANKO_MIN_P,
    )
    items = [row_to_item(r) for r in session.execute(stmt).scalars().all()]
    strong = [i for i in items if _is_strong_banko(i) and _matches_rule_version(i, rule_version)]
    return {
        **kind_summary(strong),
        "rule_version": rule_version,
        "min_probability": TIER_BANKO_MIN_P,
        "target": BANKO_PROOF_TARGET,
    }


def build_track_record(
    session: Session,
    *,
    days: int = 30,
    competition_id: Optional[str] = None,
    rule_version: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Track record of one rule version (default: the current RULE_VERSION; "all" = every version)."""
    now = now or utc_now()
    since = now - timedelta(days=days)
    version = (rule_version or "").strip() or RULE_VERSION
    period_items = [i for i in load_items(session, since) if _matches_rule_version(i, version)]

    competitions: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for item in period_items:  # options of the competition filter: independent of the filter itself
        cid = item["competition_id"]
        if cid is not None and cid not in competitions:
            competitions[cid] = {"id": cid, "name": item["competition_name"] or f"Yarışma {cid}"}

    items = [i for i in period_items if competition_id in (None, "") or i["competition_id"] == str(competition_id)]

    by_competition: List[Dict[str, Any]] = []
    grouped: "OrderedDict[Optional[str], List[Dict[str, Any]]]" = OrderedDict()
    for item in items:
        grouped.setdefault(item["competition_id"], []).append(item)
    for cid, group in grouped.items():
        name = next((g["competition_name"] for g in group if g["competition_name"]), None)
        by_competition.append(
            {"competition_id": cid, "competition_name": name, **_both(group), "total": len(group)}
        )
    by_competition.sort(key=lambda c: c["total"], reverse=True)

    weeks: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
    for item in items:
        week = _week_start(item)
        if week is not None:
            weeks.setdefault(week, []).append(item)
    by_week = [{"week_start": week, **_both(group)} for week, group in sorted(weeks.items(), reverse=True)]

    return {
        "generated_at": iso(now),
        "days": days,
        "competition_id": str(competition_id) if competition_id not in (None, "") else None,
        "rule_version": version,
        "current_rule_version": RULE_VERSION,
        "available_rule_versions": list(KNOWN_RULE_VERSIONS),
        "summary": _both(items),
        "banko_tiers": _tiers(items),
        "banko_progress": banko_progress(session, version),
        "by_competition": by_competition,
        "by_week": by_week,
        "available_competitions": list(competitions.values()),
        "picks": items,
        "note": (
            "Banko ve Oranlı, maçtan yaklaşık 20 dakika önce kaydedilir ve sonradan değiştirilmez. "
            "Başarı oranı = tutan / (tutan + tutmayan); bekleyen ve iptal edilen seçimler dahil değildir. "
            "Her kural sürümü ayrı sayılır."
        ),
    }


def match_id_aliases(session: Session, match_id: str) -> List[str]:
    """Route ids of one match: the id as given, fotmob_<id> for a bare FotMob id, and fotmob_<provider_id>
    for a local matches.id (UUID)."""
    ids = [match_id]
    if match_id.isdigit():
        ids.append(f"fotmob_{match_id}")
    else:
        try:
            from app.database.models import Match

            row = session.query(Match.provider_id).filter(Match.id == match_id).first()
            if row and row[0]:
                ids.append(f"fotmob_{row[0]}")
        except Exception:  # noqa: BLE001 - alias lookup is a convenience only
            session.rollback()
    return ids


def match_headline_record(session: Session, match_id: str) -> Dict[str, Any]:
    """The frozen Banko / Oranlı of one match (null per kind when nothing was frozen)."""
    ids = match_id_aliases(session, match_id)
    stmt = select(PredictionVersionDB).where(
        PredictionVersionDB.match_id.in_(ids), PredictionVersionDB.stage.in_(HEADLINE_STAGES)
    )
    picks: Dict[str, Optional[Dict[str, Any]]] = {kind: None for kind in KINDS}
    for row in session.execute(stmt).scalars().all():
        item = row_to_item(row)
        picks[item["kind"]] = item
    return {"match_id": match_id, "frozen": any(picks.values()), "picks": picks}
