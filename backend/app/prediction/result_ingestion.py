"""Result ingestion service for match outcomes.

Fetches real match results from providers and prepares them for settlement.
Never fabricates results.
"""

from typing import Optional
from dataclasses import dataclass
from datetime import datetime

from app.providers.base import FootballDataProvider
from app.domain.enums import MatchStatus, MatchOutcome


@dataclass
class MatchResult:
    """Match result data for settlement."""
    
    match_id: str
    status: MatchStatus
    home_score: Optional[int]
    away_score: Optional[int]
    outcome: Optional[MatchOutcome]
    is_final: bool
    fetched_at: datetime
    
    def is_settleable(self) -> bool:
        """Check if result is valid for settlement."""
        return (
            self.is_final and
            self.status == MatchStatus.FINISHED and
            self.home_score is not None and
            self.away_score is not None and
            self.outcome is not None
        )


class ResultIngestionService:
    """Service for ingesting match results from providers."""
    
    def __init__(self, provider: FootballDataProvider):
        """Initialize result ingestion service.
        
        Args:
            provider: Football data provider
        """
        self.provider = provider
    
    def get_match_result(self, match_id: str) -> Optional[MatchResult]:
        """Get match result from provider.
        
        Args:
            match_id: Match identifier
        
        Returns:
            MatchResult if available, None if match not found
        
        Raises:
            ValueError: If match data is incomplete/invalid
        """
        # Fetch match from provider
        match = self.provider.get_match(match_id)
        
        if match is None:
            return None
        
        # Determine if match is final
        is_final = match.status == MatchStatus.FINISHED
        
        # For POSTPONED/CANCELLED, outcome is None but is_final could be True
        # (allows settlement as VOID)
        if match.status in (MatchStatus.POSTPONED, MatchStatus.CANCELLED):
            return MatchResult(
                match_id=match_id,
                status=match.status,
                home_score=None,
                away_score=None,
                outcome=None,
                is_final=True,  # Postponed/cancelled are "final" states
                fetched_at=datetime.utcnow()
            )
        
        # For FINISHED, scores and outcome must be present
        if is_final:
            if match.home_score is None or match.away_score is None:
                raise ValueError(
                    f"Match {match_id} status is FINISHED but scores are missing"
                )
            
            if match.outcome is None:
                raise ValueError(
                    f"Match {match_id} status is FINISHED but outcome is missing"
                )
        
        return MatchResult(
            match_id=match_id,
            status=match.status,
            home_score=match.home_score,
            away_score=match.away_score,
            outcome=match.outcome,
            is_final=is_final,
            fetched_at=datetime.utcnow()
        )
