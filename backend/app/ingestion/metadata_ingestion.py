"""Metadata ingestion (competitions, teams, players, standings)."""

from sqlalchemy.orm import Session

from app.providers.models import (
    ProviderCompetition,
    ProviderTeam,
    ProviderPlayer,
    ProviderStanding,
)
from app.database.repository import (
    ProviderSourceRepository,
    CompetitionRepository,
    TeamRepository,
    PlayerRepository,
    StandingRepository,
)
from app.database.models import Competition, Team, Player, Standing


class MetadataIngester:
    """Ingest metadata (competitions, teams, players, standings)."""
    
    def __init__(self, session: Session):
        """Initialize metadata ingester.
        
        Args:
            session: SQLAlchemy session
        """
        self.session = session
        self.provider_source_repo = ProviderSourceRepository(session)
        self.competition_repo = CompetitionRepository(session)
        self.team_repo = TeamRepository(session)
        self.player_repo = PlayerRepository(session)
        self.standing_repo = StandingRepository(session)
    
    def ingest_competition(self, provider_comp: ProviderCompetition) -> Competition:
        """Ingest a competition.
        
        Args:
            provider_comp: Normalized provider competition
            
        Returns:
            Competition database entity
        """
        provider_source = self.provider_source_repo.get_or_create_by_name(
            name=provider_comp.provider
        )
        
        comp_data = {
            "name": provider_comp.name,
            "country": provider_comp.country,
            "level": provider_comp.level,
            "type": provider_comp.type,
            "season": provider_comp.season,
            "logo_url": provider_comp.logo_url,
        }
        
        competition = self.competition_repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id=provider_comp.source_id,
            data=comp_data,
            preserve_fields=["name", "country", "logo_url"]
        )
        
        return competition
    
    def ingest_team(self, provider_team: ProviderTeam) -> Team:
        """Ingest a team.
        
        Args:
            provider_team: Normalized provider team
            
        Returns:
            Team database entity
        """
        provider_source = self.provider_source_repo.get_or_create_by_name(
            name=provider_team.provider
        )
        
        team_data = {
            "name": provider_team.name,
            "short_name": provider_team.short_name,
            "code": provider_team.code,
            "country": provider_team.country,
            "founded": provider_team.founded,
            "venue_name": provider_team.venue_name,
            "logo_url": provider_team.logo_url,
        }
        
        team = self.team_repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id=provider_team.source_id,
            data=team_data,
            preserve_fields=["name", "country", "founded", "venue_name", "logo_url"]
        )
        
        return team
    
    def ingest_player(self, provider_player: ProviderPlayer) -> Player:
        """Ingest a player.
        
        Args:
            provider_player: Normalized provider player
            
        Returns:
            Player database entity
        """
        provider_source = self.provider_source_repo.get_or_create_by_name(
            name=provider_player.provider
        )
        
        # Get team if available
        team_id = None
        if provider_player.team_id:
            team = self.team_repo.get_by_provider_id(
                provider_source_id=provider_source.id,
                provider_id=provider_player.team_id
            )
            if team:
                team_id = team.id
        
        player_data = {
            "name": provider_player.name,
            "date_of_birth": provider_player.date_of_birth,
            "nationality": provider_player.nationality,
            "position": provider_player.position,
            "shirt_number": provider_player.shirt_number,
            "team_id": team_id,
            "height_cm": provider_player.height_cm,
            "weight_kg": provider_player.weight_kg,
            "photo_url": provider_player.photo_url,
        }
        
        player = self.player_repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id=provider_player.source_id,
            data=player_data,
            preserve_fields=["name", "date_of_birth", "nationality", "photo_url"]
        )
        
        return player
    
    def ingest_standing(self, provider_standing: ProviderStanding) -> Standing:
        """Ingest a league standing.
        
        Args:
            provider_standing: Normalized provider standing
            
        Returns:
            Standing database entity
        """
        provider_source = self.provider_source_repo.get_or_create_by_name(
            name=provider_standing.provider
        )
        
        # Get competition
        competition_id = None
        if provider_standing.competition_id:
            competition = self.competition_repo.get_by_provider_id(
                provider_source_id=provider_source.id,
                provider_id=provider_standing.competition_id
            )
            if competition:
                competition_id = competition.id
        
        # Get team
        team = self.team_repo.get_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id=provider_standing.team_id
        )
        if team is None:
            team = self.team_repo.upsert_by_provider_id(
                provider_source_id=provider_source.id,
                provider_id=provider_standing.team_id,
                data={"name": provider_standing.team_name}
            )
        
        standing_data = {
            "competition_id": competition_id,
            "season": provider_standing.season or "Unknown",
            "team_id": team.id,
            "position": provider_standing.position,
            "played": provider_standing.played,
            "won": provider_standing.won,
            "drawn": provider_standing.drawn,
            "lost": provider_standing.lost,
            "goals_for": provider_standing.goals_for,
            "goals_against": provider_standing.goals_against,
            "goal_difference": provider_standing.goal_difference,
            "points": provider_standing.points,
            "home_played": provider_standing.home_played,
            "home_won": provider_standing.home_won,
            "home_drawn": provider_standing.home_drawn,
            "home_lost": provider_standing.home_lost,
            "away_played": provider_standing.away_played,
            "away_won": provider_standing.away_won,
            "away_drawn": provider_standing.away_drawn,
            "away_lost": provider_standing.away_lost,
            "form": provider_standing.form,
            "provider_fetched_at": provider_standing.fetched_at,
        }
        
        standing = self.standing_repo.upsert_by_provider_id(
            provider_source_id=provider_source.id,
            provider_id=provider_standing.source_id,
            data=standing_data
        )
        
        return standing
