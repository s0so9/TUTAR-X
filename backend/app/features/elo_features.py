"""ELO rating features calculator.

Calculates ELO ratings for teams based on historical match results.
Ensures temporal validity - only uses matches before the prediction date.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging

from sqlalchemy.orm import Session
from app.database.models import Match, MatchStatus, MatchOutcome

logger = logging.getLogger(__name__)

# PERFORMANCE OPTIMIZATION: Module-level ELO system cache
# Prevents rebuilding ELO system on every prediction request
_global_elo_system = None
_global_elo_cached_until = None
_global_elo_session_id = None


@dataclass
class EloFeatures:
    """ELO rating features for both teams."""
    
    home_elo: Optional[float] = None
    away_elo: Optional[float] = None
    elo_difference: Optional[float] = None
    home_elo_form: Optional[float] = None  # ELO change in last 5 matches
    away_elo_form: Optional[float] = None


class EloFeatureCalculator:
    """Calculator for ELO rating features."""
    
    def __init__(
        self, 
        session: Session,
        k_factor: float = 32.0,
        initial_rating: float = 1500.0,
        home_advantage: float = 100.0,
        min_matches: int = 3
    ):
        """Initialize ELO feature calculator.
        
        Args:
            session: Database session
            k_factor: ELO rating sensitivity
            initial_rating: Starting rating for new teams
            home_advantage: Home advantage in ELO points
            min_matches: Minimum matches required for reliable ratings
        """
        self.session = session
        self.k_factor = k_factor
        self.initial_rating = initial_rating
        self.home_advantage = home_advantage
        self.min_matches = min_matches
        self._elo_system = None
        self._cached_until = None
    
    def calculate_for_match(
        self,
        home_team_id: str,
        away_team_id: str,
        match_date: datetime
    ) -> EloFeatures:
        """Calculate ELO features for a specific match.
        
        Args:
            home_team_id: Home team ID
            away_team_id: Away team ID  
            match_date: Match date (only uses data before this date)
            
        Returns:
            EloFeatures with calculated ratings
        """
        import time
        try:
            # Ensure match_date is timezone-aware (use UTC if naive)
            if match_date.tzinfo is None:
                match_date = match_date.replace(tzinfo=timezone.utc)
            
            # Ensure ELO system is up to date
            step_start = time.time()
            # OPTIMIZATION: Pass team IDs to limit query scope
            self._ensure_elo_system_current(match_date, relevant_teams={home_team_id, away_team_id})
            ensure_time = (time.time() - step_start) * 1000
            logger.debug(f"[ELO_PERF] _ensure_elo_system_current took {ensure_time:.2f}ms")
            
            if self._elo_system is None:
                logger.warning("[ELO] No ELO system available - insufficient historical data")
                return EloFeatures()
            
            # Get ratings at the match date (temporal safety)
            step_start = time.time()
            home_elo = self._elo_system.get_rating_at_time(home_team_id, match_date)
            away_elo = self._elo_system.get_rating_at_time(away_team_id, match_date)
            ratings_time = (time.time() - step_start) * 1000
            logger.debug(f"[ELO_PERF] get_rating_at_time (both teams) took {ratings_time:.2f}ms")
            
            # OPTIMIZATION: Count matches from ELO system's processed history
            # This avoids separate DB queries for counting
            step_start = time.time()
            if hasattr(self._elo_system, '_history'):
                home_matches = len([m for m in self._elo_system._history 
                                  if m.home_team_id == home_team_id or m.away_team_id == home_team_id])
                away_matches = len([m for m in self._elo_system._history 
                                  if m.home_team_id == away_team_id or m.away_team_id == away_team_id])
            else:
                # Fallback to DB query
                home_matches = self._count_team_matches_before(home_team_id, match_date)
                away_matches = self._count_team_matches_before(away_team_id, match_date)
            count_time = (time.time() - step_start) * 1000
            logger.debug(f"[ELO_PERF] count from history (both teams) took {count_time:.2f}ms")
            
            logger.info(
                f"[ELO] Match history: home_team={home_team_id[:8]}... ({home_matches} matches), "
                f"away_team={away_team_id[:8]}... ({away_matches} matches)"
            )
            
            if home_matches < self.min_matches or away_matches < self.min_matches:
                logger.info(
                    f"[ELO] Insufficient match history: home={home_matches}, "
                    f"away={away_matches}, min={self.min_matches} - ELO unavailable"
                )
                return EloFeatures()
            
            # Calculate additional features - use in-memory history instead of DB queries
            step_start = time.time()
            elo_difference = home_elo - away_elo
            
            # OPTIMIZATION: Calculate form from in-memory match history
            home_elo_form = self._calculate_elo_form_from_history(home_team_id, match_date)
            away_elo_form = self._calculate_elo_form_from_history(away_team_id, match_date)
            form_time = (time.time() - step_start) * 1000
            logger.debug(f"[ELO_PERF] _calculate_elo_form (both teams) took {form_time:.2f}ms")
            
            logger.info(f"[ELO] Ratings calculated: home={home_elo:.1f}, away={away_elo:.1f}")
            
            return EloFeatures(
                home_elo=home_elo,
                away_elo=away_elo,
                elo_difference=elo_difference,
                home_elo_form=home_elo_form,
                away_elo_form=away_elo_form
            )
            
        except Exception as e:
            logger.error(f"[ELO] Error calculating features: {e}", exc_info=True)
            return EloFeatures()
    
    def _ensure_elo_system_current(self, until_date: datetime, relevant_teams: Optional[set] = None) -> None:
        """Ensure ELO system is processed up to the given date.
        
        OPTIMIZATION: Uses module-level cache to avoid rebuilding ELO system
        across multiple prediction requests in the same session.
        
        When relevant_teams is provided, builds a targeted ELO system for just
        those teams and their opponents, dramatically reducing query time.
        """
        # CRITICAL: Declare global variables at method start, not in try block
        global _global_elo_system, _global_elo_cached_until, _global_elo_session_id
        
        # Ensure until_date is timezone-aware
        if until_date.tzinfo is None:
            until_date = until_date.replace(tzinfo=timezone.utc)
        
        # Generate session ID from database connection (reuse cache across same DB session)
        current_session_id = id(self.session)
        
        # OPTIMIZATION: Check global cache first (fastest path)
        if (_global_elo_system is not None and 
            _global_elo_cached_until is not None and
            _global_elo_session_id == current_session_id):
            
            # Ensure cached_until is timezone-aware for comparison
            cached_until_aware = _global_elo_cached_until
            if cached_until_aware.tzinfo is None:
                cached_until_aware = cached_until_aware.replace(tzinfo=timezone.utc)
            
            if cached_until_aware >= until_date:
                # Global cache is valid - reuse it
                self._elo_system = _global_elo_system
                self._cached_until = _global_elo_cached_until
                logger.debug(f"[ELO] Using GLOBAL cached ELO system (valid until {_global_elo_cached_until})")
                return
        
        # OPTIMIZATION: Check instance cache
        if self._elo_system is not None and self._cached_until:
            cached_until_aware = self._cached_until
            if cached_until_aware.tzinfo is None:
                cached_until_aware = cached_until_aware.replace(tzinfo=timezone.utc)
            
            if cached_until_aware >= until_date:
                # Instance cache is still valid
                logger.debug(f"[ELO] Using instance cached ELO system (valid until {self._cached_until})")
                return
        
        logger.info(f"[ELO] Building ELO rating system from historical matches until {until_date}")
        
        # Create new ELO system
        # Import here to avoid circular imports
        from app.prediction.elo import EloRatingSystem
        
        # Create new ELO system
        self._elo_system = EloRatingSystem(
            k_factor=self.k_factor,
            initial_rating=self.initial_rating,
            home_advantage=self.home_advantage
        )
        
        # Get finished matches - optimize query based on relevant teams
        import time
        query_start = time.time()
        
        if relevant_teams:
            # OPTIMIZATION: Load only matches involving relevant teams
            # This dramatically reduces query time when we only need ratings for 2 teams
            from sqlalchemy import or_
            team_filters = []
            for team_id in relevant_teams:
                team_filters.append(
                    or_(Match.home_team_id == team_id, Match.away_team_id == team_id)
                )
            
            matches = self.session.query(Match).filter(
                Match.status == MatchStatus.FINISHED,
                Match.scheduled_at < until_date,
                Match.home_score.isnot(None),
                Match.away_score.isnot(None),
                or_(*team_filters)
            ).order_by(Match.scheduled_at).all()
        else:
            # Load all matches (for global ELO system)
            matches = self.session.query(Match).filter(
                Match.status == MatchStatus.FINISHED,
                Match.scheduled_at < until_date,
                Match.home_score.isnot(None),
                Match.away_score.isnot(None)
            ).order_by(Match.scheduled_at).all()
        
        query_time = (time.time() - query_start) * 1000
        
        logger.info(f"[ELO] Query took {query_time:.2f}ms, found {len(matches)} finished matches in database")
        
        if len(matches) < 10:
            logger.warning(f"[ELO] Very few historical matches found: {len(matches)} - ELO unavailable")
            self._elo_system = None
            return
        
        logger.info(f"[ELO] Processing {len(matches)} historical matches for ELO ratings")
        
        # Process matches chronologically
        match_data = []
        for match in matches:
            match_data.append({
                "match_id": match.id,
                "home_team_id": match.home_team_id,
                "away_team_id": match.away_team_id,
                "home_goals": match.home_score,
                "away_goals": match.away_score,
                "played_at": match.scheduled_at
            })
        
        try:
            self._elo_system.process_matches_chronologically(match_data)
            self._cached_until = until_date
            
            # OPTIMIZATION: Store in global cache for reuse across requests
            # CRITICAL: Only cache full ELO system (not team-filtered), otherwise
            # cache would be invalid for other team pairs
            if relevant_teams is None:
                # Full system - safe to cache globally
                _global_elo_system = self._elo_system
                _global_elo_cached_until = until_date
                _global_elo_session_id = current_session_id
                logger.info(
                    f"[ELO] Full system built and cached globally: {len(match_data)} matches processed, "
                    f"{len(self._elo_system._ratings)} teams rated"
                )
            else:
                # Filtered system - don't cache globally (team-specific)
                logger.info(
                    f"[ELO] Targeted system built (NOT cached globally): {len(match_data)} matches processed, "
                    f"{len(self._elo_system._ratings)} teams rated"
                )
            
        except Exception as e:
            logger.error(f"[ELO] Failed to build system: {e}", exc_info=True)
            self._elo_system = None
    
    def _count_team_matches_before(self, team_id: str, before_date: datetime) -> int:
        """Count finished matches for a team before the given date."""
        # Ensure before_date is timezone-aware
        if before_date.tzinfo is None:
            before_date = before_date.replace(tzinfo=timezone.utc)
        
        return self.session.query(Match).filter(
            Match.status == MatchStatus.FINISHED,
            Match.scheduled_at < before_date,
            (Match.home_team_id == team_id) | (Match.away_team_id == team_id),
            Match.home_score.isnot(None),
            Match.away_score.isnot(None)
        ).count()
    
    def _calculate_elo_form_from_history(self, team_id: str, match_date: datetime, n_matches: int = 5) -> Optional[float]:
        """Calculate ELO form using in-memory match history (optimized).
        
        OPTIMIZATION: Uses ELO system's in-memory history instead of separate DB query.
        """
        if self._elo_system is None or not hasattr(self._elo_system, '_history'):
            return None
        
        # Ensure match_date is timezone-aware
        if match_date.tzinfo is None:
            match_date = match_date.replace(tzinfo=timezone.utc)
        
        # Filter matches for this team before match_date
        team_matches = []
        for m in self._elo_system._history:
            if not (m.home_team_id == team_id or m.away_team_id == team_id):
                continue
            
            # Handle timezone comparison safely
            played_at = m.played_at
            if played_at.tzinfo is None:
                played_at = played_at.replace(tzinfo=timezone.utc)
            
            if played_at < match_date:
                team_matches.append(m)
        
        # Sort by date descending and take last N
        team_matches.sort(key=lambda m: m.played_at if m.played_at.tzinfo else m.played_at.replace(tzinfo=timezone.utc), reverse=True)
        recent_matches = team_matches[:n_matches]
        
        if len(recent_matches) < 2:
            return None
        
        # Get rating change between first and last match
        first_match = recent_matches[-1]  # Oldest
        last_match = recent_matches[0]    # Most recent
        
        try:
            # Get ratings after each match
            if first_match.home_team_id == team_id:
                rating_start = first_match.home_rating_after
            else:
                rating_start = first_match.away_rating_after
                
            if last_match.home_team_id == team_id:
                rating_end = last_match.home_rating_after
            else:
                rating_end = last_match.away_rating_after
                
            return rating_end - rating_start
        except Exception:
            return None
    
    def _calculate_elo_form(self, team_id: str, match_date: datetime, n_matches: int = 5) -> Optional[float]:
        """Calculate ELO form (rating change over last N matches)."""
        if self._elo_system is None:
            return None
        
        # Ensure match_date is timezone-aware
        if match_date.tzinfo is None:
            match_date = match_date.replace(tzinfo=timezone.utc)
        
        # Get last N matches for this team before the match date
        matches = self.session.query(Match).filter(
            Match.status == MatchStatus.FINISHED,
            Match.scheduled_at < match_date,
            (Match.home_team_id == team_id) | (Match.away_team_id == team_id),
            Match.home_score.isnot(None),
            Match.away_score.isnot(None)
        ).order_by(Match.scheduled_at.desc()).limit(n_matches).all()
        
        if len(matches) < 2:
            return None
        
        # Get rating after first and last match in the period
        first_match = matches[-1]  # Oldest match (last in desc order)
        last_match = matches[0]    # Most recent match
        
        try:
            # Rating before first match (approximate)
            rating_start = self._elo_system.get_rating_at_time(team_id, first_match.scheduled_at)
            # Rating after last match
            rating_end = self._elo_system.get_rating_at_time(team_id, last_match.scheduled_at)
            
            return rating_end - rating_start
            
        except Exception:
            return None