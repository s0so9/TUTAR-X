"""Import of the hand-tracked night of 2026-10-14 as already-frozen records.

Sources (both written by hand before / during that night):
  docs/live-tests/2026-10-14/system_picks.json   the seven matches with banko / oranli key and rounded
                                                 probability, recorded_at_utc 18:58 (kick-off 19:00)
  docs/live-tests/2026-10-14/cl_2026-10-14.json  the fixture list of that day (team names, kick-off)
Nothing else is invented: no bookmaker odds (null), probabilities as recorded (2 decimals), fair odds
= 1 / recorded probability, line-ups as the record's own text states ("confirmed line-ups"). The
final scores come from the local matches table (FINISHED rows) or, when the row is missing, from
the live match centre. Re-running is harmless: existing records are never overwritten.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.prediction.headline_picks import PickCandidate, labels_for, valid_probability
from app.services.headline_tracking.records import (
    KINDS,
    SOURCE_MANUAL_2026_10_14,
    MatchFacts,
    freeze_pick,
    parse_iso,
    settle_row,
    unsettled_rows,
)
from app.services.headline_tracking.results import ResultFetcher, final_score_of, settle_outcome

logger = logging.getLogger(__name__)

DEFAULT_PICKS_FILE = Path("docs") / "live-tests" / "2026-10-14" / "system_picks.json"
DEFAULT_LISTING_FILE = Path("docs") / "live-tests" / "2026-10-14" / "cl_2026-10-14.json"
#: The night of 2026-10-14 was picked with rule headline_v1 (Oranli floor 0.45); a re-import keeps that
#: version even after RULE_VERSION moved on, so its picks never count for a later rule.
MANUAL_2026_10_14_RULE_VERSION = "headline_v1"


def _split_label(label: str) -> tuple[Optional[str], Optional[str]]:
    parts = [p.strip() for p in str(label or "").split(" - ", 1)]
    return (parts[0], parts[1]) if len(parts) == 2 and all(parts) else (None, None)


def load_manual_record(picks_file: Path, listing_file: Optional[Path]) -> List[Dict[str, Any]]:
    """One dict per recorded match: match_id, facts, picks {kind: (key, p)}, model_1x2, frozen_at."""
    record = json.loads(Path(picks_file).read_text(encoding="utf-8"))
    frozen_at = parse_iso(record.get("recorded_at_utc"))
    if frozen_at is None:
        raise ValueError(f"{picks_file}: recorded_at_utc missing or unreadable")
    listing: Dict[str, Dict[str, Any]] = {}
    if listing_file and Path(listing_file).exists():
        for m in json.loads(Path(listing_file).read_text(encoding="utf-8")):
            listing[str(m.get("id"))] = m

    out: List[Dict[str, Any]] = []
    for match_id, spec in record["picks"].items():
        listed = listing.get(match_id) or {}
        label_home, label_away = _split_label(spec.get("label", ""))
        home = ((listed.get("home_team") or {}).get("name")) or label_home
        away = ((listed.get("away_team") or {}).get("name")) or label_away
        facts = MatchFacts(
            match_id=match_id,
            kickoff_at=parse_iso(listed.get("scheduled_at")),
            competition_id=str(listed["competition_id"]) if listed.get("competition_id") is not None else None,
            competition_name=listed.get("competition_name"),
            home_team=home,
            away_team=away,
        )
        one_x_two = spec.get("model_1x2") or []
        model_1x2 = (
            {"home": one_x_two[0], "draw": one_x_two[1], "away": one_x_two[2]} if len(one_x_two) == 3 else None
        )
        picks = {}
        for kind in KINDS:
            key, p = spec.get(kind), spec.get(f"{kind}_p")
            if key and valid_probability(p):
                picks[kind] = (key, float(p))
        out.append({"facts": facts, "picks": picks, "model_1x2": model_1x2, "frozen_at": frozen_at,
                    "basis": record.get("basis")})
    return out


async def backfill_manual_2026_10_14(
    session_factory: Callable[[], Session],
    results: Optional[ResultFetcher],
    *,
    picks_file: Path,
    listing_file: Optional[Path] = None,
) -> Dict[str, Any]:
    """Freeze (idempotently) and settle the recorded picks. ``results=None`` freezes only."""
    summary: Dict[str, Any] = {"frozen": 0, "already_there": 0, "settled": 0, "unsettled": [], "matches": 0}
    for entry in load_manual_record(picks_file, listing_file):
        facts: MatchFacts = entry["facts"]
        summary["matches"] += 1
        with session_factory() as session:
            for kind, (key, p) in entry["picks"].items():
                market_name, outcome = labels_for(key, facts.home_team or "Ev sahibi", facts.away_team or "Deplasman")
                pick = PickCandidate(
                    key=key, market_name=market_name, outcome=outcome, probability=p, fair_odds=1 / p,
                    odds=None, odds_source=None,
                )
                row_id = freeze_pick(
                    session, kind, pick, facts,
                    frozen_at=entry["frozen_at"],
                    model_1x2=entry["model_1x2"],
                    lineup_types={
                        "home": "confirmed", "away": "confirmed",
                        "source": "manual record: the basis text of system_picks.json states confirmed line-ups",
                    },
                    source=SOURCE_MANUAL_2026_10_14,
                    extra={
                        # these picks were made with the rule of that night, not the current one
                        "rule_version": MANUAL_2026_10_14_RULE_VERSION,
                        "probability_precision": "rounded to 2 decimals in the manual record",
                        "fair_odds_derived_from": "recorded probability (1 / p)",
                        "recorded_basis": entry["basis"],
                    },
                    notes=["manual record of the hand-tracked night 2026-10-14, imported afterwards"],
                )
                summary["frozen" if row_id else "already_there"] += 1
        if results is None:
            continue
        result = await results(facts.match_id)
        if result is None or not result.is_final:
            summary["unsettled"].append(facts.match_id)
            continue
        with session_factory() as session:
            for row in unsettled_rows(session):
                if row.match_id != facts.match_id:
                    continue
                outcome, reason = settle_outcome(row.selected_market, result)
                if outcome and settle_row(
                    session, row, outcome=outcome, final_score=final_score_of(result), reason=reason,
                    result_source=result.source,
                ):
                    summary["settled"] += 1
    return summary
