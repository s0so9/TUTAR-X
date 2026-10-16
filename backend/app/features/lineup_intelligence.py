"""Lineup intelligence feature calculations.

This module implements player availability tracking and lineup impact estimation
using with/without player statistical methodology.

CRITICAL DATA REQUIREMENT:
- Requires historical lineup data (Lineup.starting_xi from match.py)
- If lineup data unavailable, all impact estimates = None
- NEVER fabricate impact percentages or hardcode player value estimates
- Uses statistical with/without comparison when sufficient historical samples exist

Data flow:
1. Identify player absences (injuries, suspensions, lineup changes)
2. Split historical matches into WITH and WITHOUT player using lineup data
3. Calculate performance differential (goals, xG, shots, points)
4. Validate sample sizes (min 3 matches per group)
5. Return impact estimates with confidence or None if insufficient data
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

from app.features.advanced_team_intelligence import MatchWithStatistics
from app.domain.enums import MatchStatus


class PlayerAvailabilityStatus(str, Enum):
    """Player availability status for a match."""
    CONFIRMED = "confirmed"  # Player confirmed in lineup/squad
    EXPECTED = "expected"  # Player expected to be available (not confirmed)
    INJURED = "injured"  # Out due to injury
    SUSPENDED = "suspended"  # Out due to suspension
    UNAVAILABLE = "unavailable"  # Out for other reasons (personal, tactical, etc.)
    UNKNOWN = "unknown"  # Status unknown


@dataclass
class PlayerAvailability:
    """Player availability information.
    
    Represents single player's availability status.
    """
    player_id: str
    player_name: Optional[str] = None
    status: PlayerAvailabilityStatus = PlayerAvailabilityStatus.UNKNOWN
    reason: Optional[str] = None  # "injury", "suspension", "personal", etc.
    provider: Optional[str] = None


@dataclass
class LineupImpactEstimate:
    """Statistical estimate of lineup changes impact.
    
    CRITICAL: NEVER fabricate impact if insufficient data.
    Uses with/without player methodology from historical matches.
    All impact values in range [-1.0, 1.0]:
    - Negative = weakening (e.g., -0.2 = 20% performance decline)
    - Positive = strengthening
    - None = cannot estimate from available data
    """
    team_id: str
    
    # Lineup status
    lineup_status: str = "UNAVAILABLE"  # "CONFIRMED", "EXPECTED", "UNAVAILABLE", "UNKNOWN"
    lineup_confirmed: bool = False
    lineup_expected: bool = False
    
    # Player availability
    players_available: List[PlayerAvailability] = field(default_factory=list)
    key_players_missing: List[str] = field(default_factory=list)  # player_ids
    injuries: List[Dict[str, Any]] = field(default_factory=list)
    suspensions: List[Dict[str, Any]] = field(default_factory=list)
    
    # Statistical impact estimates (None if cannot estimate from data)
    player_attack_impact: Optional[float] = None  # -1 to +1, statistical only
    player_defensive_impact: Optional[float] = None
    player_shot_impact: Optional[float] = None
    player_creation_impact: Optional[float] = None
    
    # Aggregated lineup adjustment
    attacking_adjustment: Optional[float] = None  # Combined effect on attacking strength
    defensive_adjustment: Optional[float] = None  # Combined effect on defensive strength
    shot_adjustment: Optional[float] = None  # Combined effect on shot production
    creation_adjustment: Optional[float] = None  # Combined effect on chance creation
    
    # Lineup quality score
    lineup_quality: Optional[float] = None  # 0-1 score, None if unknown
    
    # Uncertainty and confidence
    uncertainty: float = 1.0  # 1.0 = max uncertainty (lineup unknown), 0.0 = known
    data_quality: float = 0.0  # 0-1 based on historical data availability
    impact_confidence: float = 0.0  # 0-1 confidence in impact estimates
    
    # Methodology
    impact_method: str = "unavailable"  # "unavailable", "statistical_with_without", "insufficient_sample"
    
    # Provenance
    provider: Optional[str] = None
    sample_size_with: int = 0  # Total matches in WITH samples across all players
    sample_size_without: int = 0  # Total matches in WITHOUT samples across all players


class LineupIntelligenceCalculator:
    """Calculate lineup impact using with/without player statistical methodology.
    
    CRITICAL DATA REQUIREMENT: Requires historical lineup data (Lineup.starting_xi).
    If lineup data unavailable in historical matches, all impact estimates = None.
    
    NEVER use hardcoded percentages like "key player out = -10%".
    Only estimate impact when sufficient historical with/without samples exist.
    """
    
    def __init__(
        self,
        session,
        min_with_player: int = 3,
        min_without_player: int = 3
    ):
        """Initialize calculator with sample size requirements.
        
        Args:
            session: Database session (for future lineup data access)
            min_with_player: Minimum matches WITH player for reliable estimate
            min_without_player: Minimum matches WITHOUT player for reliable estimate
        """
        self.session = session
        self.min_with_player = min_with_player
        self.min_without_player = min_without_player
    
    def calculate_lineup_impact(
        self,
        team_id: str,
        player_absences: List[PlayerAvailability],
        historical_matches_with_stats: List[MatchWithStatistics],
        before_datetime: Optional[datetime] = None
    ) -> LineupImpactEstimate:
        """Calculate lineup impact using with/without player methodology.
        
        CRITICAL: NEVER fabricate impact percentages.
        Only estimate impact when sufficient historical with/without samples exist.
        
        TEMPORAL VALIDITY: Only uses matches strictly before before_datetime.
        
        Args:
            team_id: Team database ID
            player_absences: List of unavailable players with reasons
            historical_matches_with_stats: Historical matches (Match + statistics)
            before_datetime: Only use matches before this timestamp (temporal validity)
            
        Returns:
            LineupImpactEstimate with statistical impacts or None where unavailable
            
        Algorithm:
        1. Check if any players unavailable
        2. For each absent player:
           a. Split historical matches into WITH/WITHOUT player using lineup data
           b. Calculate performance differential:
              - Goals/match WITH vs WITHOUT
              - xG/match WITH vs WITHOUT (if available)
              - Shots/match WITH vs WITHOUT
              - Points/match WITH vs WITHOUT
           c. Validate sample sizes (n_with >= min, n_without >= min)
           d. Calculate impact = (performance_with - performance_without) / max(performance_with, 0.01)
              Capped to [-1.0, 1.0] range
           e. Calculate confidence based on sample sizes and balance
        3. Aggregate multiple player absences (controlled sum, not simple addition)
        4. Return LineupImpactEstimate with statistically-derived impacts or None
        
        Missing Data Handling:
        - If no historical lineup data exists → all impacts = None, method = "unavailable"
        - If insufficient with/without samples → all impacts = None, method = "insufficient_sample"
        - If player has never been absent → impact = None for that player
        - Never use hardcoded penalty values
        """
        # Filter to finished matches before cutoff
        finished_matches = [
            mws for mws in historical_matches_with_stats
            if mws.is_finished()
        ]
        
        if before_datetime is not None:
            finished_matches = [
                mws for mws in finished_matches
                if mws.match.scheduled_at < before_datetime  # STRICT < to prevent leakage
            ]
        
        # If no player absences, return neutral impact
        if not player_absences:
            return LineupImpactEstimate(
                team_id=team_id,
                lineup_status="UNAVAILABLE",
                impact_method="no_absences",
                uncertainty=0.5,  # Medium uncertainty when no changes
            )
        
        # Check if we have lineup data in historical matches
        # For now, since Lineup model exists but may not be populated,
        # we'll attempt calculation but gracefully handle missing lineup data
        
        # Calculate impact for each absent player
        total_attack_impact = 0.0
        total_defense_impact = 0.0
        total_shot_impact = 0.0
        impact_count = 0
        total_with = 0
        total_without = 0
        
        for player_absence in player_absences:
            if player_absence.status not in [
                PlayerAvailabilityStatus.INJURED,
                PlayerAvailabilityStatus.SUSPENDED,
                PlayerAvailabilityStatus.UNAVAILABLE
            ]:
                # Player is available or unknown, skip
                continue
            
            player_impact = self._calculate_player_impact_statistical(
                team_id=team_id,
                player_id=player_absence.player_id,
                matches_with_stats=finished_matches
            )
            
            if player_impact is not None:
                total_attack_impact += player_impact.get("attack_impact", 0.0) or 0.0
                total_defense_impact += player_impact.get("defense_impact", 0.0) or 0.0
                total_shot_impact += player_impact.get("shot_impact", 0.0) or 0.0
                impact_count += 1
                total_with += player_impact.get("n_with", 0)
                total_without += player_impact.get("n_without", 0)
        
        # If no impacts calculable, return unavailable
        if impact_count == 0:
            return LineupImpactEstimate(
                team_id=team_id,
                lineup_status="UNAVAILABLE",
                players_available=player_absences,
                key_players_missing=[pa.player_id for pa in player_absences],
                impact_method="unavailable",
                uncertainty=1.0,
                data_quality=0.0,
            )
        
        # Aggregate impacts (bounded)
        # Use dampened sum to avoid over-accumulation
        avg_attack = total_attack_impact / impact_count if impact_count > 0 else 0.0
        avg_defense = total_defense_impact / impact_count if impact_count > 0 else 0.0
        avg_shot = total_shot_impact / impact_count if impact_count > 0 else 0.0
        
        # Bound to [-1, 1]
        avg_attack = max(-1.0, min(1.0, avg_attack))
        avg_defense = max(-1.0, min(1.0, avg_defense))
        avg_shot = max(-1.0, min(1.0, avg_shot))
        
        # Calculate confidence based on sample sizes
        confidence = min(1.0, (total_with + total_without) / (self.min_with_player + self.min_without_player) / len(player_absences))
        
        return LineupImpactEstimate(
            team_id=team_id,
            lineup_status="EXPECTED",  # We have absence info but not confirmed lineup
            players_available=player_absences,
            key_players_missing=[pa.player_id for pa in player_absences if pa.status in [
                PlayerAvailabilityStatus.INJURED, PlayerAvailabilityStatus.SUSPENDED, PlayerAvailabilityStatus.UNAVAILABLE
            ]],
            player_attack_impact=avg_attack if impact_count > 0 else None,
            player_defensive_impact=avg_defense if impact_count > 0 else None,
            player_shot_impact=avg_shot if impact_count > 0 else None,
            attacking_adjustment=avg_attack if impact_count > 0 else None,
            defensive_adjustment=avg_defense if impact_count > 0 else None,
            shot_adjustment=avg_shot if impact_count > 0 else None,
            uncertainty=1.0 - confidence,
            data_quality=confidence,
            impact_confidence=confidence,
            impact_method="statistical_with_without" if impact_count > 0 else "insufficient_sample",
            sample_size_with=total_with,
            sample_size_without=total_without,
        )
    
    def _calculate_player_impact_statistical(
        self,
        team_id: str,
        player_id: str,
        matches_with_stats: List[MatchWithStatistics]
    ) -> Optional[Dict[str, Any]]:
        """Calculate statistical impact of single player using with/without methodology.
        
        CRITICAL LIMITATION: Current implementation cannot access lineup data.
        The Lineup model exists but requires database access to fetch starting_xi.
        This method returns None (unavailable) until lineup data access is implemented.
        
        Args:
            team_id: Team database ID
            player_id: Player database ID
            matches_with_stats: Historical matches to analyze
            
        Returns:
            Dictionary with impact metrics or None if insufficient data
            {
                "attack_impact": float,  # -1 to +1
                "defense_impact": float,
                "shot_impact": float,
                "n_with": int,
                "n_without": int
            }
        """
        # TODO: Implement lineup data access when database query available
        # For now, since we don't have access to Lineup.starting_xi in MatchWithStatistics,
        # we return None (unavailable)
        #
        # Future implementation would:
        # 1. Query Lineup table for each match_id in matches_with_stats
        # 2. Check if player_id in starting_xi
        # 3. Split into WITH/WITHOUT lists
        # 4. Calculate performance differentials
        # 5. Return impact if sufficient samples
        
        # Current behavior: return None (lineup data unavailable)
        return None
