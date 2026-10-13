"""Database writes of the team-news live layer (shared by live refresh and backfill).

``TeamNewsStore`` wraps one SQLAlchemy session and keeps small caches (FotMob
provider source id, provider id -> local UUID for teams/matches/players) so
the backfill can process thousands of matches without re-querying.

Rules implemented here (see docs/live-layer.md):
  * players: per-field merge, an observation at least as new as the best
    source's latest observation overwrites; an older one only fills NULL
    fields. profile_source/profile_observed_at track the best-ranked source
    (player profile > squad > line-up) and its latest observation. Current team comes only from squad /
    player-profile observations. Market value is written as a unit (value,
    as-of date, source); an equal value never degrades a known as-of date.
  * player_availability: a fresh complete observation of a scope (squad of a
    team, match list of a side, profile of a player) is reconciled with the
    active rows of that scope; rows are cleared, never deleted. Observations
    older than the newest one already applied to the scope are ignored.
  * lineup_snapshots: a row per distinct line-up content; repeats only move
    last_observed_at.
  * player_match_stats: upsert on (provider_match_id, player_provider_id); a
    row is only overwritten by a response fetched at the same time or later.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from app.database.models import (
    LineupSnapshot,
    Match,
    Player,
    PlayerAvailability,
    PlayerMatchStat,
    ProviderSource,
    Team,
    TeamNewsMatch,
    TeamSquadMember,
)
from app.services.team_news.constants import (
    CLEARED_NOT_LISTED,
    CLEARED_SUPERSEDED,
    SOURCE_MATCH_LINEUP,
    SOURCE_PLAYER_PROFILE,
    SOURCE_TEAM_SQUAD,
)
from app.services.team_news.parsers import (
    AvailabilityObservation,
    ParsedLineupSide,
    ParsedMatch,
    ParsedTeam,
    PlayerObservation,
    lineup_content,
)

FOTMOB_PROVIDER_NAME = "fotmob"
_CHUNK = 500
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

_PROFILE_FIELDS = (
    "name",
    "date_of_birth",
    "nationality",
    "country_code",
    "position",
    "primary_position",
    "positions",
    "shirt_number",
    "height_cm",
    "preferred_foot",
    "contract_end",
)
_TEAM_SOURCES = (SOURCE_TEAM_SQUAD, SOURCE_PLAYER_PROFILE)
_PROFILE_SOURCE_RANK = {SOURCE_MATCH_LINEUP: 1, SOURCE_TEAM_SQUAD: 2, SOURCE_PLAYER_PROFILE: 3}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """DB datetimes come back naive from SQLite (stored as UTC) -> aware UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def content_hash(content: Any) -> str:
    raw = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _chunks(items: list, size: int = _CHUNK):
    for i in range(0, len(items), size):
        yield items[i : i + size]


class TeamNewsStore:
    """All writes of the layer for one session. Callers commit."""

    def __init__(self, session: Session):
        self.session = session
        self._source_id: Optional[str] = None
        self._players: dict[str, Player] = {}
        self._team_ids: dict[str, Optional[str]] = {}
        self._match_ids: dict[str, Optional[str]] = {}

    def _sync(self) -> None:
        """Flush pending objects before a lookup (sessions may run with autoflush=False)."""
        if self.session.new or self.session.dirty:
            self.session.flush()

    # ------------------------------------------------------------------ lookups

    @property
    def fotmob_source_id(self) -> str:
        if self._source_id is None:
            src = self.session.execute(
                select(ProviderSource).where(ProviderSource.name == FOTMOB_PROVIDER_NAME)
            ).scalar_one_or_none()
            if src is None:
                src = ProviderSource(name=FOTMOB_PROVIDER_NAME, base_url=None, is_active=True)
                self.session.add(src)
                self.session.flush()
            self._source_id = src.id
        return self._source_id

    def team_ids(self, provider_ids: Iterable[Optional[str]]) -> dict[str, Optional[str]]:
        """FotMob team id -> local teams.id (None when the team is not in the DB)."""
        wanted = {p for p in provider_ids if p and p not in self._team_ids}
        for chunk in _chunks(sorted(wanted)):
            rows = self.session.execute(
                select(Team.provider_id, Team.id).where(
                    Team.provider_source_id == self.fotmob_source_id, Team.provider_id.in_(chunk)
                )
            ).all()
            found = {r[0]: r[1] for r in rows}
            for p in chunk:
                self._team_ids[p] = found.get(p)
        return {p: self._team_ids.get(p) for p in provider_ids if p}

    def team_id(self, provider_id: Optional[str]) -> Optional[str]:
        if not provider_id:
            return None
        return self.team_ids([provider_id]).get(provider_id)

    def match_ids(self, provider_ids: Iterable[Optional[str]]) -> dict[str, Optional[str]]:
        """FotMob match id -> local matches.id (None when the match is not in the DB)."""
        wanted = {p for p in provider_ids if p and p not in self._match_ids}
        for chunk in _chunks(sorted(wanted)):
            rows = self.session.execute(
                select(Match.provider_id, Match.id).where(
                    Match.provider_source_id == self.fotmob_source_id, Match.provider_id.in_(chunk)
                )
            ).all()
            found = {r[0]: r[1] for r in rows}
            for p in chunk:
                self._match_ids[p] = found.get(p)
        return {p: self._match_ids.get(p) for p in provider_ids if p}

    def match_id(self, provider_id: Optional[str]) -> Optional[str]:
        if not provider_id:
            return None
        return self.match_ids([provider_id]).get(provider_id)

    def preload_players(self) -> int:
        """Load every FotMob player into the cache (backfill speed-up)."""
        rows = self.session.execute(
            select(Player).where(Player.provider_source_id == self.fotmob_source_id)
        ).scalars()
        n = 0
        for p in rows:
            self._players[p.provider_id] = p
            n += 1
        return n

    # ------------------------------------------------------------------ players

    def ensure_players(self, observations: Iterable[PlayerObservation]) -> dict[str, Player]:
        """Create/merge players for the observations; returns provider id -> Player."""
        obs_list = [o for o in observations if o is not None and o.provider_id]
        missing = sorted({o.provider_id for o in obs_list if o.provider_id not in self._players})
        if missing:
            self._sync()
        for chunk in _chunks(missing):
            for p in self.session.execute(
                select(Player).where(
                    Player.provider_source_id == self.fotmob_source_id, Player.provider_id.in_(chunk)
                )
            ).scalars():
                self._players[p.provider_id] = p
        team_map = self.team_ids({o.team_provider_id for o in obs_list if o.team_provider_id and o.source in _TEAM_SOURCES})
        out: dict[str, Player] = {}
        for obs in obs_list:
            player = self._players.get(obs.provider_id)
            if player is None:
                if not obs.name:
                    continue  # players.name is NOT NULL and nothing may be invented
                player = Player(
                    id=str(uuid.uuid4()),  # assigned now so dependent rows need no flush
                    provider_source_id=self.fotmob_source_id,
                    provider_id=obs.provider_id,
                    name=obs.name,
                )
                self.session.add(player)
                self._players[obs.provider_id] = player
            self._merge_player(player, obs, team_map.get(obs.team_provider_id) if obs.team_provider_id else None)
            out[obs.provider_id] = player
        return out

    def players_by_provider(self, provider_ids: Iterable[str]) -> dict[str, Player]:
        ids = [p for p in provider_ids if p]
        missing = sorted({p for p in ids if p not in self._players})
        if missing:
            self._sync()
        for chunk in _chunks(missing):
            for p in self.session.execute(
                select(Player).where(
                    Player.provider_source_id == self.fotmob_source_id, Player.provider_id.in_(chunk)
                )
            ).scalars():
                self._players[p.provider_id] = p
        return {p: self._players[p] for p in ids if p in self._players}

    @staticmethod
    def _merge_player(player: Player, obs: PlayerObservation, team_db_id: Optional[str]) -> None:
        obs_time = obs.observed_at
        cur_time = as_utc(player.profile_observed_at)
        newer = cur_time is None or (obs_time is not None and obs_time >= cur_time)
        for f in _PROFILE_FIELDS:
            value = getattr(obs, f)
            if value is None:
                continue
            current = getattr(player, f)
            if current is None or (newer and current != value):
                setattr(player, f, value)
        if obs.source in _TEAM_SOURCES and obs.team_provider_id:
            if player.team_provider_id is None or (newer and player.team_provider_id != obs.team_provider_id):
                player.team_provider_id = obs.team_provider_id
                player.team_id = team_db_id
            elif player.team_provider_id == obs.team_provider_id and player.team_id is None and team_db_id:
                player.team_id = team_db_id
        if obs.market_value_eur is not None and obs.source in _TEAM_SOURCES:
            if player.market_value_eur is None or (newer and player.market_value_eur != obs.market_value_eur):
                player.market_value_eur = obs.market_value_eur
                player.market_value_as_of = obs.market_value_as_of
                player.market_value_source = obs.source
            elif (
                player.market_value_eur == obs.market_value_eur
                and obs.market_value_as_of is not None
                and (player.market_value_as_of is None or newer)
            ):
                player.market_value_as_of = obs.market_value_as_of
                player.market_value_source = obs.source
        # profile_source = best-ranked source that observed the player (profile >
        # squad > line-up); profile_observed_at = its latest observation time.
        if obs_time is not None:
            rank = _PROFILE_SOURCE_RANK.get(obs.source, 0)
            cur_rank = _PROFILE_SOURCE_RANK.get(player.profile_source or "", 0)
            if rank > cur_rank or (rank == cur_rank and newer):
                player.profile_observed_at = obs_time
                player.profile_source = obs.source

    # ------------------------------------------------------------------ squads

    def upsert_squad(self, parsed: ParsedTeam, observed_at: datetime) -> dict[str, int]:
        """Write the squad members of one team observation (season as sent)."""
        counts = {"members_inserted": 0, "members_updated": 0}
        if not parsed.squad_sent or not parsed.season:
            return counts
        players = self.ensure_players(m.player for m in parsed.members)
        team_db_id = self.team_id(parsed.team_provider_id)
        self._sync()
        existing = {
            r.player_provider_id: r
            for r in self.session.execute(
                select(TeamSquadMember).where(
                    TeamSquadMember.team_provider_id == parsed.team_provider_id,
                    TeamSquadMember.season == parsed.season,
                )
            ).scalars()
        }
        for m in parsed.members:
            player = players.get(m.player.provider_id)
            if player is None:
                continue
            row = existing.get(m.player.provider_id)
            if row is None:
                self.session.add(
                    TeamSquadMember(
                        team_provider_id=parsed.team_provider_id,
                        team_id=team_db_id,
                        player_id=player.id,
                        player_provider_id=m.player.provider_id,
                        season=parsed.season,
                        role=m.role,
                        role_key=m.role_key,
                        shirt_number=m.shirt_number,
                        first_seen_at=observed_at,
                        last_seen_at=observed_at,
                        source=SOURCE_TEAM_SQUAD,
                    )
                )
                counts["members_inserted"] += 1
                continue
            if observed_at >= as_utc(row.last_seen_at):
                row.last_seen_at = observed_at
                row.role, row.role_key, row.shirt_number = m.role, m.role_key, m.shirt_number
                if row.team_id is None and team_db_id:
                    row.team_id = team_db_id
            if observed_at < as_utc(row.first_seen_at):
                row.first_seen_at = observed_at
            counts["members_updated"] += 1
        return counts

    # ------------------------------------------------------------------ availability

    def apply_availability(
        self,
        *,
        source: str,
        entries: list[AvailabilityObservation],
        observed_at: datetime,
        basis: str,
        team_provider_id: Optional[str] = None,
        provider_match_id: Optional[str] = None,
        side: Optional[str] = None,
        player_provider_id: Optional[str] = None,
        match_db_id: Optional[str] = None,
    ) -> dict[str, int]:
        """Reconcile one complete observation of a scope with its active rows."""
        counts = {"inserted": 0, "confirmed": 0, "cleared": 0, "superseded": 0, "stale": 0, "skipped": 0}
        q = select(PlayerAvailability).where(PlayerAvailability.source == source)
        if source == SOURCE_TEAM_SQUAD:
            q = q.where(PlayerAvailability.team_provider_id == team_provider_id)
        elif source == SOURCE_MATCH_LINEUP:
            q = q.where(
                PlayerAvailability.provider_match_id == provider_match_id, PlayerAvailability.side == side
            )
        elif source == SOURCE_PLAYER_PROFILE:
            q = q.where(PlayerAvailability.player_provider_id == player_provider_id)
        else:  # pragma: no cover - programming error
            raise ValueError(f"unknown availability source {source!r}")
        self._sync()
        rows = list(self.session.execute(q).scalars())

        latest = _EPOCH
        for r in rows:
            latest = max(latest, as_utc(r.last_observed_at), as_utc(r.cleared_at) or _EPOCH)
        if rows and observed_at < latest:
            counts["stale"] = 1
            return counts

        active: dict[tuple[str, str], list[PlayerAvailability]] = defaultdict(list)
        for r in rows:
            if r.cleared_at is None:
                active[(r.player_provider_id, r.status)].append(r)

        players = self.ensure_players(
            PlayerObservation(
                provider_id=e.player_provider_id,
                source=source,
                observed_at=None,  # identity only: never overwrites profile fields
                name=e.player_name,
            )
            for e in entries
        )
        team_map = self.team_ids({e.team_provider_id for e in entries if e.team_provider_id})
        seen: set[tuple[str, str]] = set()
        for e in entries:
            key = (e.player_provider_id, e.status)
            if key in seen:
                continue
            seen.add(key)
            previous = active.pop(key, [])
            keep = None
            for r in previous:
                if keep is None and _row_report_key(r) == e.report_key():
                    keep = r
                else:
                    r.cleared_at = observed_at
                    r.cleared_reason = CLEARED_SUPERSEDED
                    counts["superseded"] += 1
            if keep is not None:
                if observed_at > as_utc(keep.last_observed_at):
                    keep.last_observed_at = observed_at
                if e.source_updated_at is not None:
                    keep.source_updated_at = e.source_updated_at
                if keep.match_id is None and match_db_id:
                    keep.match_id = match_db_id
                if keep.team_id is None and e.team_provider_id and team_map.get(e.team_provider_id):
                    keep.team_id = team_map[e.team_provider_id]
                counts["confirmed"] += 1
                continue
            player = players.get(e.player_provider_id)
            if player is None:
                counts["skipped"] += 1  # no name sent for an unknown player
                continue
            self.session.add(
                PlayerAvailability(
                    player_id=player.id,
                    player_provider_id=e.player_provider_id,
                    team_id=team_map.get(e.team_provider_id) if e.team_provider_id else None,
                    team_provider_id=e.team_provider_id,
                    status=e.status,
                    raw_type=e.raw_type,
                    reason=e.reason,
                    injury_id=e.injury_id,
                    expected_return=e.expected_return,
                    expected_return_date=e.expected_return_date,
                    source=source,
                    source_updated_at=e.source_updated_at,
                    first_observed_at=observed_at,
                    last_observed_at=observed_at,
                    cleared_at=None,
                    cleared_reason=None,
                    timestamp_basis=basis,
                    match_id=match_db_id,
                    provider_match_id=provider_match_id,
                    side=side,
                )
            )
            counts["inserted"] += 1
        for rest in active.values():
            for r in rest:
                r.cleared_at = observed_at
                r.cleared_reason = CLEARED_NOT_LISTED
                counts["cleared"] += 1
        return counts

    # ------------------------------------------------------------------ line-ups

    def record_lineup_snapshot(
        self,
        *,
        provider_match_id: str,
        side: ParsedLineupSide,
        lineup_type: Optional[str],
        lineup_source: Optional[str],
        observed_at: datetime,
        basis: str,
        source: str = SOURCE_MATCH_LINEUP,
        match_db_id: Optional[str] = None,
    ) -> tuple[Optional[LineupSnapshot], bool]:
        """Store the side's line-up if its content changed. Returns (row, created)."""
        if not side.has_lineup:
            return None, False
        content = lineup_content(side, lineup_type, lineup_source)
        digest = content_hash(content)
        self._sync()
        rows = list(
            self.session.execute(
                select(LineupSnapshot)
                .where(LineupSnapshot.provider_match_id == provider_match_id, LineupSnapshot.side == side.side)
                .order_by(LineupSnapshot.observed_at.desc())
            ).scalars()
        )
        team_db_id = self.team_id(side.team_provider_id)
        latest = rows[0] if rows else None
        if latest is not None and observed_at < as_utc(latest.observed_at):
            # an older observation arriving late (e.g. backfill after live data)
            same = next((r for r in rows if r.content_hash == digest), None)
            if same is not None:
                if observed_at < as_utc(same.observed_at):
                    same.observed_at = observed_at
                return same, False
        elif latest is not None and latest.content_hash == digest:
            if observed_at > as_utc(latest.last_observed_at):
                latest.last_observed_at = observed_at
            if latest.match_id is None and match_db_id:
                latest.match_id = match_db_id
            if latest.team_id is None and team_db_id:
                latest.team_id = team_db_id
            return latest, False
        row = LineupSnapshot(
            provider_match_id=provider_match_id,
            match_id=match_db_id,
            side=side.side,
            team_provider_id=side.team_provider_id,
            team_id=team_db_id,
            lineup_type=lineup_type,
            lineup_source=lineup_source,
            based_on_match_id=side.based_on_match_id,
            formation=side.formation,
            starter_ids=[s.get("id") for s in side.starters],
            starters=side.starters,
            bench=side.bench,
            content_hash=digest,
            observed_at=observed_at,
            last_observed_at=observed_at,
            timestamp_basis=basis,
            source=source,
        )
        self.session.add(row)
        return row, True

    # ------------------------------------------------------------------ player match stats

    def upsert_player_match_stats(
        self, parsed: ParsedMatch, fetched_at: datetime, source: str, match_db_id: Optional[str] = None
    ) -> dict[str, int]:
        counts = {"inserted": 0, "updated": 0, "skipped_older": 0, "skipped_no_player": 0}
        if not parsed.player_stats:
            return counts
        players = self.ensure_players(
            PlayerObservation(
                provider_id=r["player_provider_id"], source=SOURCE_MATCH_LINEUP, observed_at=None, name=r.get("name")
            )
            for r in parsed.player_stats
        )
        team_map = self.team_ids({r["team_provider_id"] for r in parsed.player_stats if r.get("team_provider_id")})
        self._sync()
        existing = {
            r[0]: (r[1], as_utc(r[2]))
            for r in self.session.execute(
                select(PlayerMatchStat.player_provider_id, PlayerMatchStat.id, PlayerMatchStat.fetched_at).where(
                    PlayerMatchStat.provider_match_id == parsed.provider_match_id
                )
            ).all()
        }
        now = utc_now()
        new_rows, upd_rows = [], []
        for r in parsed.player_stats:
            pid = r["player_provider_id"]
            player = players.get(pid)
            if player is None:
                counts["skipped_no_player"] += 1
                continue
            values = {
                "provider_match_id": parsed.provider_match_id,
                "match_id": match_db_id,
                "match_date": parsed.kickoff_at,
                "competition_provider_id": parsed.competition_provider_id,
                "player_id": player.id,
                "player_provider_id": pid,
                "team_id": team_map.get(r.get("team_provider_id")) if r.get("team_provider_id") else None,
                "team_provider_id": r.get("team_provider_id"),
                "source": source,
                "fetched_at": fetched_at,
                "updated_at": now,
            }
            for k in (
                "side", "started", "appeared", "minutes", "rating", "goals", "assists", "xg", "xa", "npxg",
                "xgot", "shots", "shots_on_target", "yellow_cards", "red_cards", "position_id",
                "usual_position_id", "is_goalkeeper", "sub_in_minute", "sub_out_minute", "stats_available",
                "shotmap_count", "market_value_eur",
            ):
                values[k] = r.get(k)
            if pid in existing:
                row_id, prev_fetched = existing[pid]
                if prev_fetched is not None and fetched_at < prev_fetched:
                    counts["skipped_older"] += 1
                    continue
                values["id"] = row_id
                upd_rows.append(values)
            else:
                new_rows.append(values)
        if new_rows:
            for row in new_rows:
                row["created_at"] = now
            self.session.execute(insert(PlayerMatchStat), new_rows)
            counts["inserted"] = len(new_rows)
        if upd_rows:
            self.session.execute(update(PlayerMatchStat), upd_rows)
            counts["updated"] = len(upd_rows)
        return counts

    # ------------------------------------------------------------------ registry

    def upsert_team_news_match(
        self,
        *,
        provider_match_id: str,
        header_source: str,
        competition_provider_id: Optional[str] = None,
        home_team_provider_id: Optional[str] = None,
        away_team_provider_id: Optional[str] = None,
        home_team_name: Optional[str] = None,
        away_team_name: Optional[str] = None,
        kickoff_at: Optional[datetime] = None,
        source_status: Optional[str] = None,
    ) -> TeamNewsMatch:
        self._sync()
        row = self.session.execute(
            select(TeamNewsMatch).where(TeamNewsMatch.provider_match_id == provider_match_id)
        ).scalar_one_or_none()
        if row is None:
            row = TeamNewsMatch(provider_match_id=provider_match_id)
            self.session.add(row)
        values = {
            "competition_provider_id": competition_provider_id,
            "home_team_provider_id": home_team_provider_id,
            "away_team_provider_id": away_team_provider_id,
            "home_team_name": home_team_name,
            "away_team_name": away_team_name,
            "kickoff_at": kickoff_at,
            "source_status": source_status,
        }
        changed = False
        for k, v in values.items():
            if v is not None and getattr(row, k) != v:
                setattr(row, k, v)
                changed = True
        if changed or row.header_source is None:
            row.header_source = header_source
        if row.match_id is None:
            row.match_id = self.match_id(provider_match_id)
        return row


def _row_report_key(row: PlayerAvailability) -> tuple:
    return (
        row.status,
        row.raw_type,
        row.reason,
        row.injury_id,
        row.expected_return,
        row.expected_return_date,
    )
