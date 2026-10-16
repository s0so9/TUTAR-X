"""Match history of a team: local database + FotMob team-fixtures gap fill.

* ``load_database_history`` reads finished matches of the production database
  (read only). ``teams.provider_id`` is the FotMob team id; ``matches.provider_id``
  the FotMob match id; ``home_xg`` / ``away_xg`` are FotMob xG when known.
* ``parse_team_fixtures`` turns the FotMob team page (``/api/data/teams?id=``,
  ``fixtures.allFixtures.fixtures``) into matches that are NEWER than the local
  database knows. Those rows carry ``source = "fotmob_team_fixtures"`` and no xG.
* ``build_window`` / ``build_rest`` are pure functions over a list of matches.

Friendlies are kept in the history (they count for rest days) but are not part of
the last-5 windows: a pre-season friendly says little about form.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, aliased

from app.database.models import Competition, Match, Team
from app.domain.enums import MatchStatus
from app.services.match_preview.schemas import FormWindow, PreviewMatch, RestInfo

WINDOW_SIZE = 5
HISTORY_LIMIT = 40
FRIENDLY_COMPETITION_IDS = {"489", "114", "293", "344"}  # FotMob "Club Friendlies" / "Friendlies" / "Friendlies U21"


class FixturesPayloadError(ValueError):
    """The FotMob team page has no usable fixtures list."""


# ----------------------------------------------------------------------------- helpers


def as_utc(value: datetime) -> datetime:
    """The database stores naive UTC datetimes."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def is_friendly(name: Optional[str], provider_id: Optional[str] = None) -> bool:
    if provider_id is not None and str(provider_id) in FRIENDLY_COMPETITION_IDS:
        return True
    return "friendl" in (name or "").lower()


def result_letter(goals_for: Optional[int], goals_against: Optional[int]) -> Optional[str]:
    if goals_for is None or goals_against is None:
        return None
    if goals_for > goals_against:
        return "G"
    if goals_for < goals_against:
        return "M"
    return "B"


def _is_fotmob_match_id(value: Optional[str]) -> bool:
    """FotMob match ids are plain integers of up to 8 digits; other providers' ids are not usable at FotMob."""
    return bool(value) and str(value).isdigit() and len(str(value)) <= 8


def usable_fotmob_match_id(match: PreviewMatch) -> Optional[str]:
    return match.match_id if _is_fotmob_match_id(match.match_id) else None


# ----------------------------------------------------------------------------- database


def database_latest_match(db: Session) -> Optional[datetime]:
    """Kick-off of the newest finished match in the database (None when empty)."""
    value = db.query(func.max(Match.scheduled_at)).filter(Match.status == MatchStatus.FINISHED).scalar()
    return as_utc(value) if value is not None else None


def load_database_history(
    db: Session, team_provider_id: str, before: datetime, limit: int = HISTORY_LIMIT
) -> list[PreviewMatch]:
    """Finished matches of the team (FotMob team id) before ``before``, most recent first."""
    team_ids = [row[0] for row in db.query(Team.id).filter(Team.provider_id == str(team_provider_id)).all()]
    if not team_ids:
        return []
    home_team = aliased(Team)
    away_team = aliased(Team)
    cutoff = as_utc(before).replace(tzinfo=None)
    rows = (
        db.query(Match, home_team, away_team, Competition)
        .join(home_team, Match.home_team_id == home_team.id)
        .join(away_team, Match.away_team_id == away_team.id)
        .outerjoin(Competition, Match.competition_id == Competition.id)
        .filter(or_(Match.home_team_id.in_(team_ids), Match.away_team_id.in_(team_ids)))
        .filter(Match.status == MatchStatus.FINISHED, Match.scheduled_at < cutoff)
        .filter(Match.home_score.isnot(None), Match.away_score.isnot(None))
        .order_by(Match.scheduled_at.desc())
        .limit(limit * 2)  # head-room for the duplicate rows removed below
        .all()
    )
    out: list[PreviewMatch] = []
    for match, home, away, comp in rows:
        is_home = match.home_team_id in team_ids
        goals_for = match.home_score if is_home else match.away_score
        goals_against = match.away_score if is_home else match.home_score
        has_xg = match.home_xg is not None and match.away_xg is not None
        xg_for = (match.home_xg if is_home else match.away_xg) if has_xg else None
        xg_against = (match.away_xg if is_home else match.home_xg) if has_xg else None
        opponent = away if is_home else home
        comp_name = comp.name if comp is not None else None
        out.append(
            PreviewMatch(
                match_id=str(match.provider_id) if match.provider_id else None,
                date=as_utc(match.scheduled_at),
                competition=comp_name,
                is_friendly=is_friendly(comp_name, comp.provider_id if comp is not None else None),
                venue="home" if is_home else "away",
                opponent=opponent.name,
                opponent_id=str(opponent.provider_id) if opponent.provider_id else None,
                goals_for=goals_for,
                goals_against=goals_against,
                result=result_letter(goals_for, goals_against),
                xg_for=round(float(xg_for), 2) if xg_for is not None else None,
                xg_against=round(float(xg_against), 2) if xg_against is not None else None,
                source="database",
            )
        )
    return dedupe_matches(out)[:limit]


def dedupe_matches(matches: Iterable[PreviewMatch]) -> list[PreviewMatch]:
    """The database can hold one fixture twice under two ids (same teams, same day, same score).
    Keep the row with xG, else the one with the FotMob-style (short) id. Sorted most recent first."""
    best: dict[tuple, PreviewMatch] = {}
    for m in matches:
        key = (m.venue, m.opponent_id or m.opponent, m.date.date(), m.goals_for, m.goals_against)
        cur = best.get(key)
        if cur is None:
            best[key] = m
            continue
        cur_rank = (cur.xg_for is not None, _is_fotmob_match_id(cur.match_id))
        new_rank = (m.xg_for is not None, _is_fotmob_match_id(m.match_id))
        if new_rank > cur_rank:
            best[key] = m
    return sorted(best.values(), key=lambda m: m.date, reverse=True)


# ----------------------------------------------------------------------------- FotMob team page


def _parse_dt(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _int_or_none(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def parse_team_fixtures(
    data: Any,
    team_id: str,
    *,
    before: datetime,
    after: Optional[datetime],
    known_match_ids: set[str],
) -> list[PreviewMatch]:
    """Finished fixtures of the FotMob team page played in (after, before), not already known.

    Raises FixturesPayloadError when the body has no fixtures list."""
    fixtures = None
    if isinstance(data, dict):
        block = data.get("fixtures")
        block = block.get("allFixtures") if isinstance(block, dict) else None
        fixtures = block.get("fixtures") if isinstance(block, dict) else None
    if not isinstance(fixtures, list):
        raise FixturesPayloadError("FotMob team page has no fixtures.allFixtures.fixtures list")
    before_utc = as_utc(before)
    out: list[PreviewMatch] = []
    for fx in fixtures:
        if not isinstance(fx, dict):
            continue
        status = fx.get("status") if isinstance(fx.get("status"), dict) else {}
        if not status.get("finished") or status.get("cancelled"):
            continue
        kickoff = _parse_dt(status.get("utcTime"))
        if kickoff is None or kickoff >= before_utc or (after is not None and kickoff <= after):
            continue
        match_id = str(fx.get("id")) if fx.get("id") is not None else None
        if match_id and match_id in known_match_ids:
            continue
        home = fx.get("home") if isinstance(fx.get("home"), dict) else {}
        away = fx.get("away") if isinstance(fx.get("away"), dict) else {}
        home_id, away_id = str(home.get("id")), str(away.get("id"))
        if str(team_id) not in (home_id, away_id):
            continue
        is_home = home_id == str(team_id)
        home_goals, away_goals = _int_or_none(home.get("score")), _int_or_none(away.get("score"))
        if home_goals is None or away_goals is None:
            continue
        goals_for, goals_against = (home_goals, away_goals) if is_home else (away_goals, home_goals)
        opponent = away if is_home else home
        tournament = fx.get("tournament") if isinstance(fx.get("tournament"), dict) else {}
        comp_name = tournament.get("name") if isinstance(tournament.get("name"), str) else None
        league_id = tournament.get("leagueId")
        out.append(
            PreviewMatch(
                match_id=match_id,
                date=kickoff,
                competition=comp_name,
                is_friendly=is_friendly(comp_name, str(league_id) if league_id is not None else None),
                venue="home" if is_home else "away",
                opponent=opponent.get("name") if isinstance(opponent.get("name"), str) else None,
                opponent_id=str(opponent.get("id")) if opponent.get("id") is not None else None,
                goals_for=goals_for,
                goals_against=goals_against,
                result=result_letter(goals_for, goals_against),
                source="fotmob_team_fixtures",
            )
        )
    return out


def merge_history(database: list[PreviewMatch], gap_fill: list[PreviewMatch]) -> list[PreviewMatch]:
    """Database matches plus the FotMob gap fill, most recent first."""
    return dedupe_matches([*database, *gap_fill])


# ----------------------------------------------------------------------------- windows


def build_window(
    history: list[PreviewMatch], *, scope: str, venue: Optional[str] = None, size: int = WINDOW_SIZE
) -> FormWindow:
    """Last ``size`` non-friendly matches (optionally only those played at ``venue``)."""
    pool = [m for m in history if not m.is_friendly and m.result is not None]
    if venue is not None:
        pool = [m for m in pool if m.venue == venue]
    chosen = pool[:size]
    window = FormWindow(scope=scope, venue=venue, played=len(chosen), matches=chosen)  # type: ignore[arg-type]
    if not chosen:
        where = {"home": " evde", "away": " deplasmanda"}.get(venue or "", "")
        window.missing_reason = f"Bu takım için{where} kayıtlı maç bulunamadı."
        window.xg_missing_reason = "Maç kaydı olmadığı için xG yok."
        return window
    window.results = "".join(m.result or "?" for m in chosen)
    window.wins = sum(1 for m in chosen if m.result == "G")
    window.draws = sum(1 for m in chosen if m.result == "B")
    window.losses = sum(1 for m in chosen if m.result == "M")
    window.goals_for = sum(m.goals_for or 0 for m in chosen)
    window.goals_against = sum(m.goals_against or 0 for m in chosen)
    with_xg = [m for m in chosen if m.xg_for is not None and m.xg_against is not None]
    window.xg_matches = len(with_xg)
    if with_xg:
        window.xg_for = round(sum(m.xg_for or 0.0 for m in with_xg), 2)
        window.xg_against = round(sum(m.xg_against or 0.0 for m in with_xg), 2)
        if len(with_xg) < len(chosen):
            window.xg_missing_reason = f"xG yalnızca {len(with_xg)}/{len(chosen)} maçta var."
    else:
        window.xg_missing_reason = "Bu maçlar için xG verisi yok."
    if len(chosen) < size:
        window.missing_reason = f"Son {size} yerine {len(chosen)} maç bulundu."
    return window


def build_rest(history: list[PreviewMatch], kickoff: datetime) -> RestInfo:
    """Rest days (calendar days between the previous match's date and the kick-off date, UTC) and
    the number of matches in the 14 days before kick-off. Friendlies count: they are matches played."""
    kickoff_utc = as_utc(kickoff)
    prior = sorted((m for m in history if m.date < kickoff_utc), key=lambda m: m.date, reverse=True)
    if not prior:
        return RestInfo(missing_reason="Önceki maç kaydı bulunamadı.")
    previous = prior[0]
    return RestInfo(
        previous_match=previous,
        rest_days=(kickoff_utc.date() - previous.date.date()).days,
        matches_last_14_days=sum(1 for m in prior if m.date >= kickoff_utc - timedelta(days=14)),
    )


def previous_competitive_match(history: list[PreviewMatch], kickoff: datetime) -> Optional[PreviewMatch]:
    """The most recent non-friendly match before kick-off (the one the previous XI is taken from)."""
    kickoff_utc = as_utc(kickoff)
    for m in sorted(history, key=lambda m: m.date, reverse=True):
        if m.date < kickoff_utc and not m.is_friendly:
            return m
    return None
