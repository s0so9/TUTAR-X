"""Match data ingestion."""

from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from app.providers.models import (
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchStats,
)
from app.database.repository import (
    ProviderSourceRepository,
    CompetitionRepository,
    TeamRepository,
    MatchRepository,
    MatchEventRepository,
    MatchStatisticRepository,
)
from app.database.models import Match, MatchEvent, MatchStatistic
from app.ingestion.deduplication import DeduplicationChecker


# Fields that should never be overwritten with None
PRESERVE_MATCH_FIELDS = [
    "home_score",
    "away_score",
    "home_score_ht",
    "away_score_ht",
    "home_xg",
    "away_xg",
    "outcome",
    "minute",
    "season",
    "venue_name",
]

PRESERVE_STATS_FIELDS = [
    "xg",
    "xg_against",
    "shots_total",
    "shots_on_target",
    "possession_percentage",
    "passes_completed",
    "passes_attempted",
    "corners",
    "yellow_cards",
    "red_cards",
]


class MatchIngester:
    """Ingest match data from providers."""
    
    def __init__(self, session: Session):
        """Initialize match ingester.
        
        Args:
            session: SQLAlchemy session
        """
        self.session = session
        self.provider_source_repo = ProviderSourceRepository(session)
        self.competition_repo = CompetitionRepository(session)
        self.team_repo = TeamRepository(session)
        self.match_repo = MatchRepository(session)
        self.match_event_repo = MatchEventRepository(session)
        self.match_stat_repo = MatchStatisticRepository(session)
        self.dedup_checker = DeduplicationChecker()
    
    def ingest_match(self, provider_match: ProviderMatch) -> Match:
        """Ingest a single match from provider.
        
        Creates or updates match, ensuring:
        - Provider source is tracked
        - Teams exist (creates if needed)
        - Competition exists (creates if needed)
        - Non-None fields are never overwritten with None
        
        Args:
            provider_match: Normalized provider match data
            
        Returns:
            Match database entity
        """
        # Get or create provider source
        provider_source = self.provider_source_repo.get_or_create_by_name(
            name=provider_match.provider,
            base_url=None
        )
        
        # Get or create teams
        home_team = self.team_repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id=provider_match.home_team_id,
            data={
                "name": provider_match.home_team_name,
            }
        )
        
        away_team = self.team_repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id=provider_match.away_team_id,
            data={
                "name": provider_match.away_team_name,
            }
        )
        
        # Get or create competition if available
        competition_id = None
        if provider_match.competition_id:
            competition = self.competition_repo.upsert_by_provider_id(
                provider_source_id=provider_source.id,
                provider_id=provider_match.competition_id,
                data={
                    "name": provider_match.competition_name or "Unknown Competition",
                    "season": provider_match.season,
                }
            )
            competition_id = competition.id
        
        # Prepare match data
        match_data = {
            "competition_id": competition_id,
            "home_team_id": home_team.id,
            "away_team_id": away_team.id,
            "scheduled_at": provider_match.scheduled_at,
            "status": provider_match.status,
            "minute": provider_match.minute,
            "added_time": provider_match.added_time,
            "home_score": provider_match.home_score,
            "away_score": provider_match.away_score,
            "home_score_ht": provider_match.home_score_ht,
            "away_score_ht": provider_match.away_score_ht,
            "outcome": provider_match.outcome,
            "round": provider_match.round,
            "season": provider_match.season,
            "venue_name": provider_match.venue_name,
            "provider_fetched_at": provider_match.fetched_at,
            "provider_updated_at": provider_match.source_updated_at,
            "last_provider_update": provider_match.fetched_at,
        }
        
        # Upsert match with field preservation
        match = self.match_repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id=provider_match.source_id,
            data=match_data,
            preserve_fields=PRESERVE_MATCH_FIELDS
        )
        
        return match
    
    def ingest_matches(self, provider_matches: List[ProviderMatch]) -> List[Match]:
        """Ingest multiple matches from provider.
        
        Args:
            provider_matches: List of normalized provider matches
            
        Returns:
            List of Match database entities
        """
        matches = []
        for provider_match in provider_matches:
            match = self.ingest_match(provider_match)
            matches.append(match)
        return matches
    
    def ingest_match_event(
        self,
        provider_event: ProviderMatchEvent,
        match_db_id: Optional[str] = None
    ) -> MatchEvent:
        """Ingest a match event.
        
        Args:
            provider_event: Normalized provider match event
            match_db_id: Optional internal match ID (if already known)
            
        Returns:
            MatchEvent database entity
        """
        # Get provider source
        provider_source = self.provider_source_repo.get_or_create_by_name(
            name=provider_event.provider
        )
        
        # Get match if not provided
        if match_db_id is None:
            match = self.match_repo.get_by_provider_id(
                provider_source_id=provider_source.id,
                provider_id=provider_event.match_id
            )
            if match is None:
                raise ValueError(f"Match not found: {provider_event.match_id}")
            match_db_id = match.id
        
        # Get team
        team = self.team_repo.get_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id=provider_event.team_id
        )
        if team is None:
            # Create team if doesn't exist
            team = self.team_repo.upsert_by_provider_id(
                provider_source_id=provider_source.id,
                provider_id=provider_event.team_id,
                data={"name": provider_event.team_name or "Unknown Team"}
            )
        
        # Get player if available
        player_id = None
        if provider_event.player_id:
            # Note: Player might not exist yet, handle gracefully
            # For now, we'll skip player FK if player doesn't exist
            pass
        
        # Prepare event data
        event_data = {
            "match_id": match_db_id,
            "type": provider_event.type,
            "minute": provider_event.minute,
            "added_time": provider_event.added_time,
            "team_id": team.id,
            "player_id": player_id,
            "related_player_id": None,  # TODO: Handle if needed
            "description": provider_event.description,
            "provider_fetched_at": provider_event.fetched_at,
        }
        
        # Upsert event
        event = self.match_event_repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id=provider_event.source_id,
            data=event_data
        )
        
        return event
    
    def ingest_match_stats(
        self,
        provider_stats: ProviderMatchStats,
        match_db_id: Optional[str] = None
    ) -> MatchStatistic:
        """Ingest match statistics for a team.
        
        Args:
            provider_stats: Normalized provider match statistics
            match_db_id: Optional internal match ID
            
        Returns:
            MatchStatistic database entity
        """
        # Get provider source
        provider_source = self.provider_source_repo.get_or_create_by_name(
            name=provider_stats.provider
        )
        
        # Get match if not provided
        if match_db_id is None:
            match = self.match_repo.get_by_provider_id(
                provider_source_id=provider_source.id,
                provider_id=provider_stats.match_id
            )
            if match is None:
                raise ValueError(f"Match not found: {provider_stats.match_id}")
            match_db_id = match.id
        
        # Get team
        team = self.team_repo.get_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id=provider_stats.team_id
        )
        if team is None:
            team = self.team_repo.upsert_by_provider_id(
                provider_source_id=provider_source.id,
                provider_id=provider_stats.team_id,
                data={"name": provider_stats.team_name or "Unknown Team"}
            )
        
        # Prepare statistics data
        stats_data = {
            "match_id": match_db_id,
            "team_id": team.id,
            "goals_scored": provider_stats.goals_scored,
            "goals_conceded": provider_stats.goals_conceded,
            "xg": provider_stats.xg,
            "xg_against": provider_stats.xg_against,
            "shots_total": provider_stats.shots_total,
            "shots_on_target": provider_stats.shots_on_target,
            "shots_off_target": provider_stats.shots_off_target,
            "shots_blocked": provider_stats.shots_blocked,
            "possession_percentage": provider_stats.possession_percentage,
            "passes_completed": provider_stats.passes_completed,
            "passes_attempted": provider_stats.passes_attempted,
            "pass_accuracy": provider_stats.pass_accuracy,
            "corners": provider_stats.corners,
            "free_kicks": provider_stats.free_kicks,
            "offsides": provider_stats.offsides,
            "yellow_cards": provider_stats.yellow_cards,
            "red_cards": provider_stats.red_cards,
            "fouls_committed": provider_stats.fouls_committed,
            "tackles": provider_stats.tackles,
            "interceptions": provider_stats.interceptions,
            "clearances": provider_stats.clearances,
            "saves": provider_stats.saves,
            "provider_fetched_at": provider_stats.fetched_at,
        }
        
        # Upsert statistics with field preservation
        statistic = self.match_stat_repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id=provider_stats.source_id,
            data=stats_data,
            preserve_fields=PRESERVE_STATS_FIELDS
        )
        
        return statistic
