"""Market derivation engine.

Derives all betting market probabilities mathematically from score distributions.

Markets derived:
- 1X2 (home/draw/away)
- Double Chance (1X, X2, 12)
- Over/Under (0.5, 1.5, 2.5, 3.5)
- Both Teams To Score (yes/no)
- Team Totals (home/away over 0.5, 1.5, 2.5)
- Exact Score (top 20 scorelines)
- Asian Handicap (±0.5, ±1.0, ±1.5, ±2.0)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import math


@dataclass
class MarketProbabilities:
    """Complete set of derived market probabilities."""
    
    # 1X2 market
    home_win: float
    draw: float
    away_win: float
    
    # Double chance
    home_or_draw: float  # 1X
    draw_or_away: float  # X2
    home_or_away: float  # 12
    
    # Over/Under markets (total goals)
    over_under: Dict[float, Tuple[float, float]] = field(default_factory=dict)  # line -> (over_prob, under_prob)
    
    # Both Teams To Score
    btts_yes: float = 0.0
    btts_no: float = 0.0
    
    # Combined markets
    over_2_5_and_btts_yes: float = 0.0  # Over 2.5 goals AND both teams score
    
    # Team totals
    home_team_over: Dict[float, float] = field(default_factory=dict)  # line -> over_prob
    away_team_over: Dict[float, float] = field(default_factory=dict)  # line -> over_prob
    
    # Exact score (top N scorelines)
    exact_score_top: List[Tuple[str, float]] = field(default_factory=list)  # ("H-A", probability)
    
    # Asian handicap (from home perspective)
    asian_handicap: Dict[float, Tuple[float, float, float]] = field(default_factory=dict)  # line -> (home_win, push, away_win)
    
    def validate(self) -> None:
        """Validate probability consistency."""
        # Check 1X2 sums to 1.0
        total_1x2 = self.home_win + self.draw + self.away_win
        if not (0.999 <= total_1x2 <= 1.001):
            raise ValueError(f"1X2 probabilities must sum to 1.0, got {total_1x2:.6f}")
        
        # Check double chance consistency
        expected_1x = self.home_win + self.draw
        if not math.isclose(self.home_or_draw, expected_1x, rel_tol=0.001):
            raise ValueError(f"1X should equal home+draw: {self.home_or_draw:.6f} vs {expected_1x:.6f}")
        
        expected_x2 = self.draw + self.away_win
        if not math.isclose(self.draw_or_away, expected_x2, rel_tol=0.001):
            raise ValueError(f"X2 should equal draw+away: {self.draw_or_away:.6f} vs {expected_x2:.6f}")
        
        expected_12 = self.home_win + self.away_win
        if not math.isclose(self.home_or_away, expected_12, rel_tol=0.001):
            raise ValueError(f"12 should equal home+away: {self.home_or_away:.6f} vs {expected_12:.6f}")
        
        # Check BTTS sums to 1.0
        if self.btts_yes > 0 or self.btts_no > 0:
            total_btts = self.btts_yes + self.btts_no
            if not (0.999 <= total_btts <= 1.001):
                raise ValueError(f"BTTS probabilities must sum to 1.0, got {total_btts:.6f}")
        
        # Check each over/under pair sums to 1.0
        for line, (over, under) in self.over_under.items():
            total = over + under
            if not (0.999 <= total <= 1.001):
                raise ValueError(f"Over/Under {line} must sum to 1.0, got {total:.6f}")


class MarketDerivationEngine:
    """Derives all market probabilities from score distribution.
    
    Algorithm:
    1. Input: score_distribution dict ("H-A" -> probability) from Monte Carlo
    2. Derive 1X2 by summing scorelines where H>A, H==A, H<A
    3. Derive double chance by combining 1X2 probabilities
    4. Derive O/U by summing scorelines where H+A > line or H+A <= line
    5. Derive BTTS by summing scorelines where H>0 AND A>0
    6. Derive team totals by summing scorelines where H>line or A>line
    7. Derive exact score by sorting scorelines by probability
    8. Derive Asian handicaps by applying handicap to scorelines
    
    All derived probabilities are mathematically consistent (complementary markets sum to 1.0).
    """
    
    def __init__(self, top_scorelines: int = 20):
        """Initialize market derivation engine.
        
        Args:
            top_scorelines: Number of top scorelines to include in exact score market
        """
        self.top_scorelines = top_scorelines
    
    def derive(
        self,
        score_distribution: Dict[Tuple[int, int], float]
    ) -> MarketProbabilities:
        """Derive all markets from score distribution.
        
        Args:
            score_distribution: Score distribution from simulation
                Format: {(home_goals, away_goals): probability, ...}
        
        Returns:
            MarketProbabilities with all derived markets
        
        Raises:
            ValueError: If score distribution is invalid
        """
        if not score_distribution:
            raise ValueError("Score distribution cannot be empty")
        
        # Normalize distribution to sum to exactly 1.0
        total_prob = sum(score_distribution.values())
        if total_prob == 0:
            raise ValueError("Score distribution probabilities sum to zero")
        
        normalized_dist = {
            scoreline: prob / total_prob
            for scoreline, prob in score_distribution.items()
        }
        
        # Derive 1X2
        home_win = sum(
            prob for (h, a), prob in normalized_dist.items() if h > a
        )
        draw = sum(
            prob for (h, a), prob in normalized_dist.items() if h == a
        )
        away_win = sum(
            prob for (h, a), prob in normalized_dist.items() if h < a
        )
        
        # Normalize 1X2 (handle floating point errors)
        total_1x2 = home_win + draw + away_win
        if total_1x2 > 0:
            home_win /= total_1x2
            draw /= total_1x2
            away_win /= total_1x2
        
        # Derive double chance
        home_or_draw = home_win + draw
        draw_or_away = draw + away_win
        home_or_away = home_win + away_win
        
        # Derive over/under for standard lines
        over_under = {}
        for line in [0.5, 1.5, 2.5, 3.5]:
            over_prob = sum(
                prob for (h, a), prob in normalized_dist.items() if h + a > line
            )
            under_prob = sum(
                prob for (h, a), prob in normalized_dist.items() if h + a <= line
            )
            
            # Normalize
            total = over_prob + under_prob
            if total > 0:
                over_prob /= total
                under_prob /= total
            
            over_under[line] = (over_prob, under_prob)
        
        # Derive BTTS
        btts_yes = sum(
            prob for (h, a), prob in normalized_dist.items() if h > 0 and a > 0
        )
        btts_no = sum(
            prob for (h, a), prob in normalized_dist.items() if h == 0 or a == 0
        )
        
        # Normalize BTTS
        total_btts = btts_yes + btts_no
        if total_btts > 0:
            btts_yes /= total_btts
            btts_no /= total_btts
        
        # Derive combined markets
        # Over 2.5 + BTTS Yes: total goals >= 3 AND both teams score
        over_2_5_and_btts_yes = sum(
            prob for (h, a), prob in normalized_dist.items() 
            if h + a >= 3 and h > 0 and a > 0
        )
        
        # Derive team totals
        home_team_over = {}
        away_team_over = {}
        
        for line in [0.5, 1.5, 2.5]:
            home_over = sum(
                prob for (h, a), prob in normalized_dist.items() if h > line
            )
            away_over = sum(
                prob for (h, a), prob in normalized_dist.items() if a > line
            )
            
            home_team_over[line] = home_over
            away_team_over[line] = away_over
        
        # Derive exact score top N
        sorted_scorelines = sorted(
            normalized_dist.items(),
            key=lambda x: x[1],
            reverse=True
        )
        exact_score_top = [
            (f"{h}-{a}", prob)
            for (h, a), prob in sorted_scorelines[:self.top_scorelines]
        ]
        
        # Derive Asian handicap
        asian_handicap = self._derive_asian_handicap(normalized_dist)
        
        # Build result
        markets = MarketProbabilities(
            home_win=home_win,
            draw=draw,
            away_win=away_win,
            home_or_draw=home_or_draw,
            draw_or_away=draw_or_away,
            home_or_away=home_or_away,
            over_under=over_under,
            btts_yes=btts_yes,
            btts_no=btts_no,
            over_2_5_and_btts_yes=over_2_5_and_btts_yes,
            home_team_over=home_team_over,
            away_team_over=away_team_over,
            exact_score_top=exact_score_top,
            asian_handicap=asian_handicap
        )
        
        # Validate consistency
        markets.validate()
        
        return markets
    
    def _derive_asian_handicap(
        self,
        score_distribution: Dict[Tuple[int, int], float]
    ) -> Dict[float, Tuple[float, float, float]]:
        """Derive Asian handicap probabilities.
        
        Asian handicap adjusts the score by a handicap line from home perspective.
        
        Examples:
        - Handicap -0.5: Home must win by at least 1 goal
        - Handicap -1.0: Home must win by at least 2 goals (1 goal = push)
        - Handicap +0.5: Home can draw or win
        
        Args:
            score_distribution: Normalized score distribution
        
        Returns:
            Dict mapping handicap line to (home_win, push, away_win) probabilities
        """
        handicaps = {}
        
        for line in [-2.0, -1.5, -1.0, -0.5, 0.5, 1.0, 1.5, 2.0]:
            home_wins = 0.0
            pushes = 0.0
            away_wins = 0.0
            
            for (h, a), prob in score_distribution.items():
                # Apply handicap from home perspective
                adjusted_margin = (h - a) + line
                
                if adjusted_margin > 0:
                    home_wins += prob
                elif adjusted_margin == 0:
                    pushes += prob
                else:
                    away_wins += prob
            
            # Normalize
            total = home_wins + pushes + away_wins
            if total > 0:
                home_wins /= total
                pushes /= total
                away_wins /= total
            
            handicaps[line] = (home_wins, pushes, away_wins)
        
        return handicaps
