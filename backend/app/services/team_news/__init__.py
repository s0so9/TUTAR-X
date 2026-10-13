"""Team-news live layer: squads, availability (injuries/suspensions), line-up
snapshots, player match stats and the team-news read model.

See docs/live-layer.md. Public entry points:
  * build_team_news(session, match_id) / build_team_squad(session, team_id)
  * TeamNewsService(session_factory, client).refresh_team_squads(team_ids) /
    refresh_match_team_news(match) / ingest_finished_match(match) / run_cycle()
  * apply_team_payload / apply_player_payload / apply_match_payload (raw body -> DB)
"""

from app.services.team_news.builder import TeamNewsNotFound, build_team_news, build_team_squad
from app.services.team_news.service import (
    MatchRef,
    TeamNewsService,
    apply_match_payload,
    apply_player_payload,
    apply_team_payload,
    ingest_finished_match,
    refresh_match_team_news,
    refresh_team_squads,
)

__all__ = [
    "MatchRef",
    "TeamNewsNotFound",
    "TeamNewsService",
    "apply_match_payload",
    "apply_player_payload",
    "apply_team_payload",
    "build_team_news",
    "build_team_squad",
    "ingest_finished_match",
    "refresh_match_team_news",
    "refresh_team_squads",
]
