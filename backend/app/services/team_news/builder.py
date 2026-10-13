"""Read side of the team-news layer: build_team_news / build_team_squad (DB only).

No network calls. Every number comes from stored observations:
  * line-up: latest lineup_snapshots row of the match side (observed at or
    before ``as_of``);
  * absentees: player_availability rows active at ``as_of`` from the match
    list, the team squad and player profiles;
  * last-5 form: the team's last N FINISHED matches before kickoff in
    ``matches`` and the player_match_stats rows of those matches;
  * freshness: observed_at of every source used.
``as_of`` is the kickoff for started/finished matches (point-in-time view) and
"now" for upcoming ones. Missing data -> None + missing_reason code.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.database.models import (
    Competition,
    LineupSnapshot,
    Match,
    Player,
    PlayerAvailability,
    PlayerMatchStat,
    Team,
    TeamNewsMatch,
    TeamSquadMember,
)
from app.domain.enums import MatchStatus
from app.services.team_news.constants import (
    FORM_WINDOW_MATCHES,
    LINEUP_STATUS_BY_TYPE,
    LINEUP_TYPE_LABELS_TR,
    SOURCE_LABELS_TR,
    SOURCE_MATCH_DETAILS,
    SOURCE_MATCH_LINEUP,
    SOURCE_PLAYER_PROFILE,
    SOURCE_TEAM_SQUAD,
    STATUS_LABELS_TR,
)
from app.services.team_news.schemas import (
    Absentee,
    AvailabilityReport,
    ContributionShare,
    FormCoverage,
    LineupPlayer,
    MatchInfo,
    PlayerForm,
    PlayerRef,
    SideFreshness,
    SideLineup,
    SideTeamNews,
    SourceRef,
    SquadPlayer,
    TeamLast5,
    TeamLast5Match,
    TeamNewsResponse,
    TeamRef,
    TeamSquadResponse,
)
from app.services.team_news.service import MatchRef, resolve_match_ref, split_match_identifier
from app.services.team_news.store import TeamNewsStore, as_utc, utc_now

_SOURCE_PRIORITY = {SOURCE_MATCH_LINEUP: 0, SOURCE_TEAM_SQUAD: 1, SOURCE_PLAYER_PROFILE: 2}

NOTES_TR = [
    "Eksik oyuncu listesi kaynakların bildirdiği raporlardır; listede olmamak oyuncunun hazır olduğunu garanti etmez.",
    "Form değerleri takımın maç öncesindeki son maçlarından, FotMob oyuncu istatistikleriyle hesaplanır; "
    "FotMob'un göndermediği değerler sayılmaz (kapsam alanlarına bakın).",
    "xG: şut verisi olan maçlarda şut çekmeyen oyuncunun xG'si 0 kabul edilir (xg_zero_rule_apps); "
    "şut verisi olmayan maçlarda xG bilinmez.",
]


class TeamNewsNotFound(Exception):
    """The match is neither in `matches` nor tracked by the team-news layer."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _active_at(as_of: datetime):
    return and_(
        PlayerAvailability.first_observed_at <= as_of,
        or_(PlayerAvailability.cleared_at.is_(None), PlayerAvailability.cleared_at > as_of),
    )


def _round(value: Optional[float], digits: int = 2) -> Optional[float]:
    return None if value is None else round(value, digits)


# =========================================================================== team news


def build_team_news(
    session: Session, match_id: str, *, now: Optional[datetime] = None, window: int = FORM_WINDOW_MATCHES
) -> TeamNewsResponse:
    now = now or utc_now()
    ref = resolve_match_ref(session, match_id)
    if ref is None:
        raise TeamNewsNotFound("match_not_tracked")
    kickoff = ref.kickoff_at
    started = ref.status in ("started", "finished") or (kickoff is not None and kickoff <= now)
    as_of = kickoff if (started and kickoff is not None) else now
    window_end = kickoff or now
    store = TeamNewsStore(session)
    reg = session.execute(
        select(TeamNewsMatch).where(TeamNewsMatch.provider_match_id == ref.provider_match_id)
    ).scalar_one_or_none()

    sources: dict[str, Optional[datetime]] = {}
    sides: dict[str, SideTeamNews] = {}
    for side in ("home", "away"):
        team_pid = ref.home_team_provider_id if side == "home" else ref.away_team_provider_id
        team_name = ref.home_team_name if side == "home" else ref.away_team_name
        sides[side] = _build_side(
            session, store, ref, reg, side, team_pid, team_name, as_of, window_end, window, sources
        )

    return TeamNewsResponse(
        match=MatchInfo(
            requested_id=match_id,
            provider_match_id=ref.provider_match_id,
            match_id=ref.match_db_id,
            competition_provider_id=ref.competition_provider_id,
            kickoff_at=kickoff,
            status=ref.status,
            as_of=as_of,
            home=sides["home"].team,
            away=sides["away"].team,
        ),
        home=sides["home"],
        away=sides["away"],
        sources=[
            SourceRef(source=k, label=SOURCE_LABELS_TR.get(k, k), observed_at=v)
            for k, v in sorted(sources.items())
        ],
        generated_at=now,
        is_development_data=False,
        notes=list(NOTES_TR),
    )


def _note_source(sources: dict[str, Optional[datetime]], key: str, at: Optional[datetime]) -> None:
    at = as_utc(at)
    prev = sources.get(key)
    if key not in sources or (at is not None and (prev is None or at > prev)):
        sources[key] = at


def _build_side(
    session: Session,
    store: TeamNewsStore,
    ref: MatchRef,
    reg: Optional[TeamNewsMatch],
    side: str,
    team_pid: Optional[str],
    team_name: Optional[str],
    as_of: datetime,
    window_end: datetime,
    window: int,
    sources: dict[str, Optional[datetime]],
) -> SideTeamNews:
    team_db_id = store.team_id(team_pid)
    if team_name is None and team_db_id:
        t = session.get(Team, team_db_id)
        team_name = t.name if t else None
    team = TeamRef(team_id=team_db_id, provider_id=team_pid, name=team_name)
    freshness = SideFreshness()

    # ---------------------------------------------------------------- last N team matches
    last5, window_matches = _team_last_matches(session, team_db_id, window_end, window)
    if window_matches:
        freshness.last_team_match_at = as_utc(window_matches[0].scheduled_at)
        _note_source(sources, "local_matches", freshness.last_team_match_at)
    window_pids = [m.provider_id for m in window_matches]
    stat_rows: list[PlayerMatchStat] = []
    if team_pid and window_pids:
        stat_rows = list(
            session.execute(
                select(PlayerMatchStat).where(
                    PlayerMatchStat.provider_match_id.in_(window_pids),
                    PlayerMatchStat.team_provider_id == team_pid,
                )
            ).scalars()
        )
    rows_by_match: dict[str, dict[str, PlayerMatchStat]] = defaultdict(dict)
    for r in stat_rows:
        rows_by_match[r.provider_match_id][r.player_provider_id] = r
        freshness.player_match_stats_fetched_at = _max_dt(freshness.player_match_stats_fetched_at, r.fetched_at)
    matches_with_data = [m for m in window_matches if m.provider_id in rows_by_match]
    for item in last5.matches:
        item.player_data = item.provider_match_id in rows_by_match
    if stat_rows:
        _note_source(sources, SOURCE_MATCH_DETAILS, freshness.player_match_stats_fetched_at)
    form_ctx = _FormContext(window_matches, matches_with_data, rows_by_match, team_db_id)

    # ---------------------------------------------------------------- line-up
    lineup = None
    lineup_missing = None
    snap = session.execute(
        select(LineupSnapshot)
        .where(
            LineupSnapshot.provider_match_id == ref.provider_match_id,
            LineupSnapshot.side == side,
            LineupSnapshot.observed_at <= as_of,
        )
        .order_by(LineupSnapshot.observed_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    starter_pids: list[str] = []
    if snap is not None:
        starter_pids = [str(s.get("id")) for s in (snap.starters or []) if s.get("id") is not None]
    absentee_rows = _availability_rows(session, ref.provider_match_id, side, team_pid, as_of)
    absent_pids = list(dict.fromkeys(r.player_provider_id for r in absentee_rows))
    players = store.players_by_provider(starter_pids + absent_pids)

    if snap is not None:
        freshness.lineup_observed_at = as_utc(snap.last_observed_at)
        _note_source(sources, SOURCE_MATCH_LINEUP, freshness.lineup_observed_at)
        starters = []
        for s in snap.starters or []:
            pid = str(s.get("id")) if s.get("id") is not None else None
            if pid is None:
                continue
            p = players.get(pid)
            starters.append(
                LineupPlayer(
                    player_id=p.id if p else None,
                    provider_id=pid,
                    name=s.get("name") or (p.name if p else None),
                    shirt_number=s.get("shirt_number"),
                    position_id=s.get("position_id"),
                    usual_position_id=s.get("usual_position_id"),
                    primary_position=p.primary_position if p else None,
                    form=form_ctx.form(pid),
                )
            )
        bench = None
        if snap.bench is not None:
            bench = [
                PlayerRef(
                    provider_id=str(b.get("id")),
                    name=b.get("name"),
                    shirt_number=b.get("shirt_number"),
                    usual_position_id=b.get("usual_position_id"),
                )
                for b in snap.bench
                if b.get("id") is not None
            ]
        lineup = SideLineup(
            snapshot_id=snap.id,
            lineup_type=snap.lineup_type,
            lineup_status=LINEUP_STATUS_BY_TYPE.get(snap.lineup_type or "", "other"),
            lineup_type_label=LINEUP_TYPE_LABELS_TR.get(snap.lineup_type or ""),
            lineup_source=snap.lineup_source,
            based_on_match_id=snap.based_on_match_id,
            formation=snap.formation,
            observed_at=as_utc(snap.observed_at),
            last_observed_at=as_utc(snap.last_observed_at),
            timestamp_basis=snap.timestamp_basis,
            starters=starters,
            bench=bench,
        )
    else:
        lineup_missing = "lineup_not_observed"

    # ---------------------------------------------------------------- absentees
    by_player: dict[str, list[PlayerAvailability]] = defaultdict(list)
    for r in absentee_rows:
        by_player[r.player_provider_id].append(r)
    absentees: list[Absentee] = []
    for pid, rows in by_player.items():
        rows.sort(key=lambda r: (_SOURCE_PRIORITY.get(r.source, 9), -(as_utc(r.last_observed_at).timestamp())))
        primary = rows[0]
        p = players.get(pid)
        for r in rows:
            _note_source(sources, r.source, r.last_observed_at)
        absentees.append(
            Absentee(
                player=PlayerRef(
                    player_id=p.id if p else primary.player_id,
                    provider_id=pid,
                    name=p.name if p else None,
                    shirt_number=p.shirt_number if p else None,
                    primary_position=p.primary_position if p else None,
                ),
                status=primary.status,
                status_label=STATUS_LABELS_TR.get(primary.status, primary.status),
                raw_type=primary.raw_type,
                reason=primary.reason or next((r.reason for r in rows if r.reason), None),
                expected_return=primary.expected_return,
                expected_return_date=primary.expected_return_date,
                primary_source=primary.source,
                reports=[_report(r) for r in rows],
                listed_in_lineup=pid in starter_pids,
                form=form_ctx.form(pid),
                share=form_ctx.share(pid),
            )
        )
    absentees.sort(key=lambda a: (a.status, a.player.name or ""))

    match_list_at = None
    if reg is not None:
        match_list_at = as_utc(getattr(reg, f"{side}_unavailable_observed_at"))
        if match_list_at is not None and match_list_at > as_of:
            match_list_at = None
    freshness.match_unavailable_observed_at = match_list_at
    squad_first, squad_last = None, None
    if team_pid:
        squad_first, squad_last = session.execute(
            select(func.min(TeamSquadMember.first_seen_at), func.max(TeamSquadMember.last_seen_at)).where(
                TeamSquadMember.team_provider_id == team_pid
            )
        ).one()
        freshness.squad_observed_at = as_utc(squad_last)
        prof_at = session.execute(
            select(func.max(Player.profile_observed_at)).where(
                Player.team_provider_id == team_pid, Player.profile_source == SOURCE_PLAYER_PROFILE
            )
        ).scalar_one_or_none()
        freshness.player_profiles_observed_at = as_utc(prof_at)
    squad_seen_by_as_of = squad_first is not None and as_utc(squad_first) <= as_of
    absentees_missing = None
    if not absentee_rows and match_list_at is None and not squad_seen_by_as_of:
        absentees_missing = "availability_not_observed"

    return SideTeamNews(
        side=side,
        team=team,
        lineup=lineup,
        lineup_missing_reason=lineup_missing,
        absentees=absentees,
        absentees_missing_reason=absentees_missing,
        last5=last5,
        freshness=freshness,
    )


def _max_dt(a: Optional[datetime], b: Optional[datetime]) -> Optional[datetime]:
    a, b = as_utc(a), as_utc(b)
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def _report(r: PlayerAvailability) -> AvailabilityReport:
    return AvailabilityReport(
        id=r.id,
        source=r.source,
        status=r.status,
        raw_type=r.raw_type,
        reason=r.reason,
        injury_id=r.injury_id,
        expected_return=r.expected_return,
        expected_return_date=r.expected_return_date,
        first_observed_at=as_utc(r.first_observed_at),
        last_observed_at=as_utc(r.last_observed_at),
        timestamp_basis=r.timestamp_basis,
        source_updated_at=as_utc(r.source_updated_at),
    )


def _availability_rows(
    session: Session, provider_match_id: str, side: str, team_pid: Optional[str], as_of: datetime
) -> list[PlayerAvailability]:
    conds = [
        and_(
            PlayerAvailability.source == SOURCE_MATCH_LINEUP,
            PlayerAvailability.provider_match_id == provider_match_id,
            PlayerAvailability.side == side,
        )
    ]
    if team_pid:
        conds.append(
            and_(PlayerAvailability.source == SOURCE_TEAM_SQUAD, PlayerAvailability.team_provider_id == team_pid)
        )
        team_players = select(Player.provider_id).where(Player.team_provider_id == team_pid)
        conds.append(
            and_(
                PlayerAvailability.source == SOURCE_PLAYER_PROFILE,
                PlayerAvailability.player_provider_id.in_(team_players),
            )
        )
    return list(session.execute(select(PlayerAvailability).where(or_(*conds), _active_at(as_of))).scalars())


def _team_last_matches(
    session: Session, team_db_id: Optional[str], before: datetime, window: int
) -> tuple[TeamLast5, list[Match]]:
    if team_db_id is None:
        return TeamLast5(missing_reason="team_not_in_local_db"), []
    # Two queries on the team indexes (home / away) with the FINISHED filter in
    # Python: with an OR, or with `status` in the WHERE clause, SQLite (no
    # ANALYZE stats) walks the status / scheduled_at index over all matches
    # (~35 ms per query instead of ~0.5 ms).
    candidates: list[Match] = []
    page = max(window * 3, 10)
    for column in (Match.home_team_id, Match.away_team_id):
        found: list[Match] = []
        offset = 0
        while len(found) < window:
            rows = list(
                session.execute(
                    select(Match)
                    .where(column == team_db_id, Match.scheduled_at < before)
                    .order_by(Match.scheduled_at.desc())
                    .offset(offset)
                    .limit(page)
                ).scalars()
            )
            found.extend(m for m in rows if m.status == MatchStatus.FINISHED)
            if len(rows) < page:
                break
            offset += page
        candidates.extend(found[:window])
    matches = sorted({m.id: m for m in candidates}.values(), key=lambda m: m.scheduled_at, reverse=True)[:window]
    if not matches:
        return TeamLast5(missing_reason="no_finished_matches_before_kickoff"), []
    team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
    teams = {t.id: t for t in session.execute(select(Team).where(Team.id.in_(sorted(team_ids)))).scalars()}
    comp_ids = {m.competition_id for m in matches if m.competition_id}
    comps = (
        {c.id: c for c in session.execute(select(Competition).where(Competition.id.in_(sorted(comp_ids)))).scalars()}
        if comp_ids
        else {}
    )
    items: list[TeamLast5Match] = []
    wins = draws = losses = 0
    gf_total = ga_total = 0
    scores_known = 0
    xgf_total = xga_total = 0.0
    xg_matches = 0
    for m in matches:
        home = m.home_team_id == team_db_id
        opp = teams.get(m.away_team_id if home else m.home_team_id)
        gf = m.home_score if home else m.away_score
        ga = m.away_score if home else m.home_score
        xgf = m.home_xg if home else m.away_xg
        xga = m.away_xg if home else m.home_xg
        result = None
        if gf is not None and ga is not None:
            result = "W" if gf > ga else ("D" if gf == ga else "L")
            wins += result == "W"
            draws += result == "D"
            losses += result == "L"
            gf_total += gf
            ga_total += ga
            scores_known += 1
        if xgf is not None and xga is not None:
            xgf_total += xgf
            xga_total += xga
            xg_matches += 1
        comp = comps.get(m.competition_id)
        items.append(
            TeamLast5Match(
                match_id=m.id,
                provider_match_id=m.provider_id,
                kickoff_at=as_utc(m.scheduled_at),
                competition_provider_id=comp.provider_id if comp else None,
                competition_name=comp.name if comp else None,
                venue="home" if home else "away",
                opponent=TeamRef(
                    team_id=opp.id if opp else None,
                    provider_id=opp.provider_id if opp else None,
                    name=opp.name if opp else None,
                ),
                goals_for=gf,
                goals_against=ga,
                result=result,
                xg_for=xgf,
                xg_against=xga,
            )
        )
    last5 = TeamLast5(
        matches=items,
        played=len(items),
        wins=wins if scores_known else None,
        draws=draws if scores_known else None,
        losses=losses if scores_known else None,
        goals_for=gf_total if scores_known else None,
        goals_against=ga_total if scores_known else None,
        xg_for=_round(xgf_total) if xg_matches else None,
        xg_against=_round(xga_total) if xg_matches else None,
        xg_matches=xg_matches,
    )
    return last5, matches


class _FormContext:
    """Per-side helper computing player form and contribution shares."""

    def __init__(
        self,
        window_matches: list[Match],
        matches_with_data: list[Match],
        rows_by_match: dict[str, dict[str, PlayerMatchStat]],
        team_db_id: Optional[str],
    ):
        self.window_matches = window_matches
        self.with_data = matches_with_data
        self.rows = rows_by_match
        self.team_db_id = team_db_id

    def _base_reason(self) -> Optional[str]:
        if not self.window_matches:
            return "no_finished_matches_before_kickoff"
        if not self.with_data:
            return "no_player_match_data"
        if len(self.with_data) < len(self.window_matches):
            return "partial_player_match_data"
        return None

    def form(self, pid: str) -> PlayerForm:
        form = PlayerForm(window_matches=len(self.window_matches), matches_with_data=len(self.with_data))
        reason = self._base_reason()
        if not self.with_data:
            form.missing_reason = reason
            return form
        cov = FormCoverage()
        apps = starts = minutes = goals = assists = 0
        xg = xa = 0.0
        ratings: list[float] = []
        for m in self.with_data:
            r = self.rows[m.provider_id].get(pid)
            if r is None or not r.appeared:
                continue
            apps += 1
            starts += int(bool(r.started))
            if r.minutes is not None:
                minutes += r.minutes
                cov.minutes_apps += 1
            if r.goals is not None:
                goals += r.goals
                cov.goals_apps += 1
            if r.assists is not None:
                assists += r.assists
                cov.assists_apps += 1
            if r.xg is not None:
                xg += r.xg
                cov.xg_apps += 1
            elif r.stats_available and r.shotmap_count == 0:
                cov.xg_apps += 1
                cov.xg_zero_rule_apps += 1
            if r.xa is not None:
                xa += r.xa
                cov.xa_apps += 1
            if r.rating is not None:
                ratings.append(r.rating)
                cov.rated_apps += 1
        form.apps, form.starts, form.coverage = apps, starts, cov
        if apps == 0:
            # no appearance in matches whose full line-ups are known: no minutes, no contributions
            form.minutes, form.goals, form.assists, form.xg, form.xa = 0, 0, 0, 0.0, 0.0
            form.missing_reason = ",".join(x for x in (reason, "did_not_appear") if x)
            return form
        form.minutes = minutes if cov.minutes_apps else None
        form.goals = goals if cov.goals_apps else None
        form.assists = assists if cov.assists_apps else None
        form.xg = _round(xg) if cov.xg_apps else None
        form.xa = _round(xa) if cov.xa_apps else None
        form.avg_rating = _round(sum(ratings) / len(ratings)) if ratings else None
        form.missing_reason = reason
        return form

    def share(self, pid: str) -> ContributionShare:
        share = ContributionShare(matches_used=len(self.with_data))
        if not self.with_data or self.team_db_id is None:
            share.missing_reason = self._base_reason() or "no_player_match_data"
            return share
        team_goals = player_goals = 0
        goals_known = True
        team_xg = player_xg = 0.0
        xg_matches = 0
        team_minutes = player_minutes = 0
        minutes_known = True
        for m in self.with_data:
            home = m.home_team_id == self.team_db_id
            rows = self.rows[m.provider_id]
            r = rows.get(pid)
            appeared = r is not None and bool(r.appeared)
            gf = m.home_score if home else m.away_score
            if gf is None:
                goals_known = False
            else:
                team_goals += gf
                if appeared:
                    if r.goals is None:
                        goals_known = False
                    else:
                        player_goals += r.goals
            txg = m.home_xg if home else m.away_xg
            if txg is not None:
                p_xg: Optional[float] = 0.0
                if appeared:
                    if r.xg is not None:
                        p_xg = r.xg
                    elif not (r.stats_available and r.shotmap_count == 0):
                        p_xg = None
                if p_xg is not None:
                    team_xg += txg
                    player_xg += p_xg
                    xg_matches += 1
            match_minutes = [x.minutes for x in rows.values() if x.minutes is not None]
            if match_minutes:
                team_minutes += max(match_minutes)
                if appeared:
                    if r.minutes is None:
                        minutes_known = False
                    else:
                        player_minutes += r.minutes
            else:
                minutes_known = False
        reasons = []
        if goals_known:
            share.player_goals, share.team_goals = player_goals, team_goals
            if team_goals > 0:
                share.goals_share = _round(player_goals / team_goals, 3)
            else:
                reasons.append("team_scored_no_goals")
        else:
            reasons.append("player_goals_unavailable")
        if xg_matches:
            share.player_xg, share.team_xg = _round(player_xg), _round(team_xg)
            if team_xg > 0:
                share.xg_share = _round(player_xg / team_xg, 3)
        else:
            reasons.append("team_xg_unavailable")
        if minutes_known and team_minutes > 0:
            share.player_minutes, share.team_minutes = player_minutes, team_minutes
            share.minutes_share = _round(player_minutes / team_minutes, 3)
        else:
            reasons.append("team_minutes_unavailable")
        base = self._base_reason()
        if base:
            reasons.insert(0, base)
        share.missing_reason = ",".join(reasons) if reasons else None
        return share


# =========================================================================== squad


def resolve_team(session: Session, team_id: str) -> tuple[Optional[str], Optional[Team]]:
    """'fotmob_9825' / '9825' / local UUID -> (FotMob team id, local Team or None)."""
    provider_id, local_id = split_match_identifier(team_id)
    if local_id is not None:
        team = session.get(Team, local_id)
        if team is None:
            return None, None
        return team.provider_id, team
    if provider_id is None:
        return None, None
    team = session.execute(select(Team).where(Team.provider_id == provider_id)).scalars().first()
    return provider_id, team


def build_team_squad(
    session: Session, team_id: str, *, now: Optional[datetime] = None, include_former: bool = False
) -> TeamSquadResponse:
    now = now or utc_now()
    team_pid, team = resolve_team(session, team_id)
    if team_pid is None:
        raise TeamNewsNotFound("team_not_found")
    team_ref = TeamRef(team_id=team.id if team else None, provider_id=team_pid, name=team.name if team else None)
    latest = session.execute(
        select(TeamSquadMember.season, func.max(TeamSquadMember.last_seen_at))
        .where(TeamSquadMember.team_provider_id == team_pid)
        .group_by(TeamSquadMember.season)
        .order_by(func.max(TeamSquadMember.last_seen_at).desc())
        .limit(1)
    ).first()
    if latest is None:
        if team is None:
            raise TeamNewsNotFound("team_not_found")
        return TeamSquadResponse(team=team_ref, missing_reason="squad_not_observed", generated_at=now)
    season, observed = latest[0], as_utc(latest[1])
    members = list(
        session.execute(
            select(TeamSquadMember).where(
                TeamSquadMember.team_provider_id == team_pid, TeamSquadMember.season == season
            )
        ).scalars()
    )
    if not include_former:
        members = [m for m in members if as_utc(m.last_seen_at) >= observed]
    pids = [m.player_provider_id for m in members]
    players = TeamNewsStore(session).players_by_provider(pids)
    reports: dict[str, list[PlayerAvailability]] = defaultdict(list)
    for i in range(0, len(pids), 500):
        chunk = pids[i : i + 500]
        for r in session.execute(
            select(PlayerAvailability).where(
                PlayerAvailability.player_provider_id.in_(chunk),
                PlayerAvailability.cleared_at.is_(None),
                PlayerAvailability.source.in_((SOURCE_TEAM_SQUAD, SOURCE_PLAYER_PROFILE)),
            )
        ).scalars():
            if r.source == SOURCE_TEAM_SQUAD and r.team_provider_id != team_pid:
                continue
            reports[r.player_provider_id].append(r)
    out = []
    prof_at = None
    for m in members:
        p = players.get(m.player_provider_id)
        if p is None:
            continue
        if p.profile_source == SOURCE_PLAYER_PROFILE:
            prof_at = _max_dt(prof_at, p.profile_observed_at)
        rep = reports.get(m.player_provider_id, [])
        out.append(
            SquadPlayer(
                player_id=p.id,
                provider_id=m.player_provider_id,
                name=p.name,
                shirt_number=m.shirt_number if m.shirt_number is not None else p.shirt_number,
                role=m.role,
                role_key=m.role_key,
                position=p.position,
                primary_position=p.primary_position,
                positions=p.positions,
                date_of_birth=p.date_of_birth,
                nationality=p.nationality,
                country_code=p.country_code,
                height_cm=p.height_cm,
                preferred_foot=p.preferred_foot,
                market_value_eur=p.market_value_eur,
                market_value_as_of=as_utc(p.market_value_as_of),
                market_value_source=p.market_value_source,
                contract_end=p.contract_end,
                first_seen_at=as_utc(m.first_seen_at),
                last_seen_at=as_utc(m.last_seen_at),
                in_latest_squad=as_utc(m.last_seen_at) >= observed,
                availability_status="unavailable" if rep else "no_report",
                availability=[_report(r) for r in rep],
            )
        )
    _ROLE_ORDER = {"keepers": 0, "defenders": 1, "midfielders": 2, "attackers": 3}
    out.sort(key=lambda s: (_ROLE_ORDER.get(s.role or "", 9), s.shirt_number if s.shirt_number is not None else 999, s.name or ""))
    srcs = [SourceRef(source=SOURCE_TEAM_SQUAD, label=SOURCE_LABELS_TR[SOURCE_TEAM_SQUAD], observed_at=observed)]
    if prof_at is not None:
        srcs.append(
            SourceRef(source=SOURCE_PLAYER_PROFILE, label=SOURCE_LABELS_TR[SOURCE_PLAYER_PROFILE], observed_at=prof_at)
        )
    return TeamSquadResponse(
        team=team_ref,
        season=season,
        squad_observed_at=observed,
        players=out,
        sources=srcs,
        generated_at=now,
    )
