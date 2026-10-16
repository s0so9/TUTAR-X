"""Database-backed provider adapter for canonical UUID lookups.

This provider bridges the gap between external providers and the database
by handling canonical UUID lookups through the database when external
providers cannot resolve them.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from sqlalchemy.orm import Session

from app.providers.base import FootballDataProvider
from app.domain.match import Match
from app.domain.entities import Team, Competition, Season
from app.domain.statistics import TeamMatchStatistic
from app.database.models import (
    Match as MatchDB,
    Team as TeamDB,
    Competition as CompetitionDB,
    MatchStatistic as MatchStatisticDB,
)
from app.database.repository import MatchRepository, TeamRepository
from app.domain.enums import MatchStatus


logger = logging.getLogger(__name__)


class DatabaseBackedProvider(FootballDataProvider):
    """Provider that serves data from the database for canonical UUID lookups.
    
    This provider is used as a fallback when external providers cannot resolve
    canonical UUIDs. It directly queries the database to retrieve match and
    team information.
    """
    
    def __init__(self, session: Session):
        """Initialize database-backed provider.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.match_repo = MatchRepository(session)
        self.team_repo = TeamRepository(session)
    
    def is_development_data(self) -> bool:
        """Return False since this uses real database data."""
        return False
    
    def get_provider_name(self) -> str:
        """Return the provider name."""
        return "DatabaseBackedProvider"
    
    def get_competition(self, competition_id: str) -> Optional[Competition]:
        """Get competition by ID from database.
        
        Args:
            competition_id: Competition UUID
            
        Returns:
            Competition domain object or None if not found
        """
        comp_db = self.session.query(CompetitionDB).filter(CompetitionDB.id == competition_id).first()
        
        if not comp_db:
            return None
        
        return Competition(
            id=comp_db.id,
            name=comp_db.name,
            country=comp_db.country,
            level=comp_db.level,
            type=comp_db.type,
        )
    
    def get_seasons(self, competition_id: str) -> List[Season]:
        """Get seasons for a competition from database.
        
        Args:
            competition_id: Competition ID
            
        Returns:
            List of seasons (simplified implementation)
        """
        # For now, return a default season based on database matches
        # This can be enhanced when Season table is available
        return [Season(
            id="2024/25",
            competition_id=competition_id,
            year="2024/25",
            is_current=True
        )]
    
    def get_current_season(self, competition_id: str) -> Optional[Season]:
        """Get current season for a competition.
        
        Args:
            competition_id: Competition ID
            
        Returns:
            Current season (simplified implementation)
        """
        return Season(
            id="2024/25",
            competition_id=competition_id,
            year="2024/25",
            is_current=True
        )
    
    def get_match(self, match_id: str) -> Optional[Match]:
        """Get match by canonical UUID from database.
        
        Args:
            match_id: Canonical match UUID
            
        Returns:
            Match domain object or None if not found
        """
        match_db = self.session.query(MatchDB).filter(MatchDB.id == match_id).first()
        
        if not match_db:
            return None
        
        # Convert database model to domain model
        return Match(
            id=match_db.id,
            home_team_id=match_db.home_team_id,
            away_team_id=match_db.away_team_id,
            competition_id=match_db.competition_id or "unknown",
            season_id=match_db.season or "unknown",
            scheduled_at=match_db.scheduled_at,
            status=match_db.status,
            home_score=match_db.home_score,
            away_score=match_db.away_score,
            home_score_ht=match_db.home_score_ht,
            away_score_ht=match_db.away_score_ht,
            outcome=match_db.outcome,
            round=match_db.round,
            created_at=match_db.created_at,
            updated_at=match_db.updated_at,
            provider_fetched_at=match_db.provider_fetched_at,
        )
    
    def get_team(self, team_id: str) -> Optional[Team]:
        """Get team by canonical UUID from database.
        
        Args:
            team_id: Canonical team UUID
            
        Returns:
            Team domain object or None if not found
        """
        team_db = self.session.query(TeamDB).filter(TeamDB.id == team_id).first()
        
        if not team_db:
            return None
        
        # Convert database model to domain model
        return Team(
            id=team_db.id,
            name=team_db.name,
            short_name=team_db.short_name,
            code=team_db.code,
            logo_url=team_db.logo_url,
        )
    
    def get_matches(
        self,
        competition_id: Optional[str] = None,
        season_id: Optional[str] = None,
        team_id: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        status: Optional[str] = None,
    ) -> List[Match]:
        """Get matches from database with filters.
        
        Args:
            competition_id: Filter by competition
            season_id: Filter by season  
            team_id: Filter by team
            from_date: Filter from date
            to_date: Filter to date
            status: Filter by status
            
        Returns:
            List of Match domain objects
        """
        query = self.session.query(MatchDB)
        
        # Apply filters with type safety
        if competition_id:
            if isinstance(competition_id, str):
                query = query.filter(MatchDB.competition_id == competition_id)
            else:
                logger.warning(f"competition_id parameter is not a string: {type(competition_id)}")
        
        if season_id:
            if isinstance(season_id, str):
                query = query.filter(MatchDB.season == season_id)
            else:
                logger.warning(f"season_id parameter is not a string: {type(season_id)}")
            
        if team_id:
            if isinstance(team_id, str):
                query = query.filter(
                    (MatchDB.home_team_id == team_id) | (MatchDB.away_team_id == team_id)
                )
            else:
                logger.warning(f"team_id parameter is not a string: {type(team_id)}")
        
        if from_date:
            # Ensure from_date is actually a date object
            if not isinstance(from_date, date):
                logger.warning(f"from_date parameter is not a date object: {type(from_date)}, skipping date filter")
            else:
                from_datetime = datetime.combine(from_date, datetime.min.time())
                query = query.filter(MatchDB.scheduled_at >= from_datetime)
            
        if to_date:
            # Ensure to_date is actually a date object
            if not isinstance(to_date, date):
                logger.warning(f"to_date parameter is not a date object: {type(to_date)}, skipping date filter")
            else:
                to_datetime = datetime.combine(to_date, datetime.max.time())
                query = query.filter(MatchDB.scheduled_at <= to_datetime)
        
        if status:
            # Ensure status is actually a string
            if not isinstance(status, str):
                logger.warning(f"status parameter is not a string: {type(status)}, skipping status filter")
            else:
                try:
                    match_status = MatchStatus(status.upper())
                    query = query.filter(MatchDB.status == match_status)
                except ValueError:
                    # Invalid status, return empty list
                    return []
        
        # Execute query and convert to domain objects
        matches_db = query.order_by(MatchDB.scheduled_at).all()
        
        matches = []
        for match_db in matches_db:
            match = Match(
                id=match_db.id,
                home_team_id=match_db.home_team_id,
                away_team_id=match_db.away_team_id,
                competition_id=match_db.competition_id or "unknown",
                season_id=match_db.season or "unknown",
                scheduled_at=match_db.scheduled_at,
                status=match_db.status,
                home_score=match_db.home_score,
                away_score=match_db.away_score,
                home_score_ht=match_db.home_score_ht,
                away_score_ht=match_db.away_score_ht,
                outcome=match_db.outcome,
                round=match_db.round,
                created_at=match_db.created_at,
                updated_at=match_db.updated_at,
                provider_fetched_at=match_db.provider_fetched_at,
            )
            matches.append(match)
        
        return matches
    
    def get_team_match_statistics(self, match_id: str) -> List[TeamMatchStatistic]:
        """Get team match statistics from database.
        
        Args:
            match_id: Canonical match UUID
            
        Returns:
            List of TeamMatchStatistic objects
        """
        stats_db = self.session.query(MatchStatisticDB).filter(
            MatchStatisticDB.match_id == match_id
        ).all()
        
        statistics = []
        for stat_db in stats_db:
            stat = TeamMatchStatistic(
                id=str(stat_db.id),  # Add missing id field
                match_id=match_id,   # Add missing match_id field
                team_id=stat_db.team_id,
                goals_scored=stat_db.goals_scored or 0,      # Handle None values
                goals_conceded=stat_db.goals_conceded or 0,  # Handle None values
                xg=stat_db.xg,
                xg_against=stat_db.xg_against,
                shots_total=stat_db.shots_total,
                shots_on_target=stat_db.shots_on_target,
                shots_off_target=stat_db.shots_off_target,
                shots_blocked=stat_db.shots_blocked,
                possession_percentage=stat_db.possession_percentage,
                passes_completed=stat_db.passes_completed,
                passes_attempted=stat_db.passes_attempted,
                pass_accuracy=stat_db.pass_accuracy,
                corners=stat_db.corners,
                free_kicks=stat_db.free_kicks,
                offsides=stat_db.offsides,
                yellow_cards=stat_db.yellow_cards,
                red_cards=stat_db.red_cards,
                fouls_committed=stat_db.fouls_committed,
                tackles=stat_db.tackles,
                interceptions=stat_db.interceptions,
                clearances=stat_db.clearances,
                saves=stat_db.saves,
            )
            statistics.append(stat)
        
        return statistics
    
    def get_team_match_statistics_firsthalf(self, match_id: str) -> List[TeamMatchStatistic]:
        """Get first-half team match statistics from database.
        
        Args:
            match_id: Canonical match UUID
            
        Returns:
            List of TeamMatchStatistic objects for first half
        """
        # Note: This assumes first-half statistics are stored separately
        # If they're not available, return empty list
        # This can be enhanced when first-half data is available in database
        return []
    
    # Required abstract methods from FootballDataProvider
    def get_competitions(self, country: Optional[str] = None) -> List[Competition]:
        """Get competitions from database."""
        query = self.session.query(CompetitionDB)
        
        if country:
            query = query.filter(CompetitionDB.country == country)
        
        competitions_db = query.all()
        
        competitions = []
        for comp_db in competitions_db:
            comp = Competition(
                id=comp_db.id,
                name=comp_db.name,
                country=comp_db.country,
                level=comp_db.level,
                type=comp_db.type,
            )
            competitions.append(comp)
        
        return competitions
    
    def get_teams(self, competition_id: str, season_id: Optional[str] = None) -> List[Team]:
        """Get teams from database for a competition."""
        # Get teams that have matches in this competition
        query = self.session.query(TeamDB).join(
            MatchDB,
            (MatchDB.home_team_id == TeamDB.id) | (MatchDB.away_team_id == TeamDB.id)
        ).filter(MatchDB.competition_id == competition_id)
        
        if season_id:
            query = query.filter(MatchDB.season == season_id)
        
        teams_db = query.distinct().all()
        
        teams = []
        for team_db in teams_db:
            team = Team(
                id=team_db.id,
                name=team_db.name,
                short_name=team_db.short_name,
                code=team_db.code,
                logo_url=team_db.logo_url,
            )
            teams.append(team)
        
        return teams