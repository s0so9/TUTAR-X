"""Shot production probability modeling.

This module implements shot-market probability calculation using statistical distributions.
Models shot volume as count data (Poisson or Negative Binomial) and calculates
P(shots > T) for various market thresholds.

Distribution Selection:
- If variance > mean: Negative Binomial (overdispersed)
- If variance ≤ mean: Poisson (equidispersed)

Negative Binomial parameterization:
- r = μ² / (σ² - μ)  (shape parameter)
- p = r / (r + μ)     (success probability for scipy)
- μ = mean, σ² = variance

Poisson parameterization:
- λ = μ

Threshold probabilities:
- P(X > T) = 1 - CDF(T)

Data flow:
1. Receive raw shot counts from ShotIntelligenceCalculator
2. Calculate mean and variance
3. Select distribution (Poisson vs NegBin)
4. Parameterize distribution
5. Calculate threshold probabilities P(shots > T)
6. Apply opponent adjustment if opponent data available
7. Return ShotProduction with probabilities and provenance
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Tuple
from scipy.stats import poisson, nbinom
import math

from app.features.shot_intelligence import ShotIntelligenceMetrics


@dataclass
class ShotProduction:
    """Shot production distribution and threshold probabilities.
    
    Models shot volume as count distribution (Poisson or Negative Binomial).
    Calculates P(shots > T) for configurable thresholds.
    
    All probability fields are Optional — None if insufficient data for modeling.
    """
    team_id: str
    
    # Distribution parameters for shots
    expected_shots_mean: Optional[float] = None  # μ
    expected_shots_variance: Optional[float] = None  # σ²
    shots_distribution_model: Optional[str] = None  # "poisson", "negative_binomial", "none"
    
    # Distribution parameters for shots on target
    expected_sot_mean: Optional[float] = None
    expected_sot_variance: Optional[float] = None
    sot_distribution_model: Optional[str] = None
    
    # Negative Binomial parameters (when overdispersed)
    nb_r_shots: Optional[float] = None  # r = μ²/(σ²-μ)
    nb_p_shots: Optional[float] = None  # p = r/(r+μ) for scipy
    
    nb_r_sot: Optional[float] = None
    nb_p_sot: Optional[float] = None
    
    # Poisson parameter (when equidispersed)
    poisson_lambda_shots: Optional[float] = None  # λ = μ
    poisson_lambda_sot: Optional[float] = None
    
    # Shot threshold probabilities P(X > T)
    over_10_shots_prob: Optional[float] = None
    over_12_shots_prob: Optional[float] = None
    over_15_shots_prob: Optional[float] = None
    over_18_shots_prob: Optional[float] = None
    over_20_shots_prob: Optional[float] = None
    
    # SOT threshold probabilities P(X > T)
    over_3_sot_prob: Optional[float] = None
    over_4_sot_prob: Optional[float] = None
    over_5_sot_prob: Optional[float] = None
    over_6_sot_prob: Optional[float] = None
    
    # Total shots (home + away combined) - for total shots markets
    expected_total_shots_mean: Optional[float] = None
    expected_total_shots_variance: Optional[float] = None
    total_shots_distribution_model: Optional[str] = None
    
    # Total shot thresholds
    total_over_20_prob: Optional[float] = None
    total_over_22_prob: Optional[float] = None
    total_over_25_prob: Optional[float] = None
    total_over_30_prob: Optional[float] = None
    
    # Opponent adjustment
    opponent_suppression_applied: bool = False
    opponent_adjusted_mean: Optional[float] = None
    
    # Calibration metadata
    historical_calibration_available: bool = False
    sample_size: int = 0
    data_quality_score: float = 0.0
    uncertainty_score: float = 1.0  # 0=low uncertainty, 1=high uncertainty


class ShotProductionCalculator:
    """Calculate shot production probabilities using statistical distributions.
    
    Implements Poisson and Negative Binomial distribution fitting.
    Calculates threshold probabilities for shot markets.
    """
    
    MIN_MATCHES_FOR_DISTRIBUTION = 5
    SHOT_THRESHOLDS = [10, 12, 15, 18, 20]
    SOT_THRESHOLDS = [3, 4, 5, 6]
    TOTAL_SHOTS_THRESHOLDS = [20, 22, 25, 30]
    
    def __init__(self, session, min_matches: int = 5):
        """Initialize calculator with minimum sample size.
        
        Args:
            session: Database session (for future repository access)
            min_matches: Minimum matches required for distribution fitting
        """
        self.session = session
        self.min_matches = min_matches
    
    def calculate(
        self,
        team_id: str,
        shot_counts: List[float],
        sot_counts: Optional[List[float]] = None,
        opponent_shots_allowed: Optional[List[float]] = None,
        before_datetime: Optional[datetime] = None  # For documentation/provenance only
    ) -> ShotProduction:
        """Calculate shot production distribution and threshold probabilities.
        
        Args:
            team_id: Team database ID
            shot_counts: Raw shots per match (already filtered < before_datetime)
            sot_counts: Raw SOT per match (optional)
            opponent_shots_allowed: Opponent's shots conceded per match (for adjustment)
            before_datetime: For provenance only (filtering already done by caller)
            
        Returns:
            ShotProduction with threshold probabilities or None if insufficient data
        """
        # Check sufficient sample
        if len(shot_counts) < self.MIN_MATCHES_FOR_DISTRIBUTION:
            return ShotProduction(
                team_id=team_id,
                shots_distribution_model="none",
                sample_size=len(shot_counts),
                data_quality_score=0.0,
                uncertainty_score=1.0,
            )
        
        # Fit distribution for shots
        (
            shots_model,
            shots_mean,
            shots_variance,
            shots_nb_r,
            shots_nb_p
        ) = self._fit_distribution(shot_counts)
        
        if shots_model is None:
            return ShotProduction(
                team_id=team_id,
                shots_distribution_model="none",
                sample_size=len(shot_counts),
                data_quality_score=0.0,
                uncertainty_score=1.0,
            )
        
        # Calculate shot threshold probabilities
        shot_probs = {}
        for threshold in self.SHOT_THRESHOLDS:
            prob = self._threshold_probability(
                threshold=threshold,
                model=shots_model,
                mu=shots_mean,
                nb_r=shots_nb_r,
                nb_p=shots_nb_p
            )
            shot_probs[threshold] = prob
        
        # Fit distribution for SOT if available
        sot_model = None
        sot_mean = None
        sot_variance = None
        sot_nb_r = None
        sot_nb_p = None
        sot_probs = {}
        
        if sot_counts and len(sot_counts) >= self.MIN_MATCHES_FOR_DISTRIBUTION:
            (
                sot_model,
                sot_mean,
                sot_variance,
                sot_nb_r,
                sot_nb_p
            ) = self._fit_distribution(sot_counts)
            
            if sot_model is not None:
                for threshold in self.SOT_THRESHOLDS:
                    prob = self._threshold_probability(
                        threshold=threshold,
                        model=sot_model,
                        mu=sot_mean,
                        nb_r=sot_nb_r,
                        nb_p=sot_nb_p
                    )
                    sot_probs[threshold] = prob
        
        # Calculate data quality and uncertainty
        data_quality = min(1.0, len(shot_counts) / (self.MIN_MATCHES_FOR_DISTRIBUTION * 2))
        uncertainty = 1.0 - data_quality
        
        return ShotProduction(
            team_id=team_id,
            # Shots distribution
            expected_shots_mean=shots_mean,
            expected_shots_variance=shots_variance,
            shots_distribution_model=shots_model,
            nb_r_shots=shots_nb_r,
            nb_p_shots=shots_nb_p,
            poisson_lambda_shots=shots_mean if shots_model == "poisson" else None,
            # SOT distribution
            expected_sot_mean=sot_mean,
            expected_sot_variance=sot_variance,
            sot_distribution_model=sot_model or "none",
            nb_r_sot=sot_nb_r,
            nb_p_sot=sot_nb_p,
            poisson_lambda_sot=sot_mean if sot_model == "poisson" else None,
            # Shot thresholds
            over_10_shots_prob=shot_probs.get(10),
            over_12_shots_prob=shot_probs.get(12),
            over_15_shots_prob=shot_probs.get(15),
            over_18_shots_prob=shot_probs.get(18),
            over_20_shots_prob=shot_probs.get(20),
            # SOT thresholds
            over_3_sot_prob=sot_probs.get(3),
            over_4_sot_prob=sot_probs.get(4),
            over_5_sot_prob=sot_probs.get(5),
            over_6_sot_prob=sot_probs.get(6),
            # Provenance
            sample_size=len(shot_counts),
            data_quality_score=data_quality,
            uncertainty_score=uncertainty,
        )
    
    def calculate_total(
        self,
        home_shot_counts: List[float],
        away_shot_counts: List[float]
    ) -> ShotProduction:
        """Calculate total shots (home + away) distribution for match.
        
        Args:
            home_shot_counts: Home team's shot counts per match
            away_shot_counts: Away team's shot counts per match
            
        Returns:
            ShotProduction with total shots probabilities
        """
        # For total shots, we need to model the sum of two count distributions
        # Simplified approach: assume independence and use convolution
        # For now, use simple approach: fit distribution to combined mean/variance
        
        if len(home_shot_counts) < self.MIN_MATCHES_FOR_DISTRIBUTION or \
           len(away_shot_counts) < self.MIN_MATCHES_FOR_DISTRIBUTION:
            return ShotProduction(
                team_id="total",
                total_shots_distribution_model="none",
                sample_size=0,
                data_quality_score=0.0,
                uncertainty_score=1.0,
            )
        
        # Calculate combined mean and variance
        # E[X + Y] = E[X] + E[Y]
        # Var[X + Y] = Var[X] + Var[Y] (if independent)
        
        home_mean = sum(home_shot_counts) / len(home_shot_counts)
        home_var = sum((x - home_mean) ** 2 for x in home_shot_counts) / (len(home_shot_counts) - 1)
        
        away_mean = sum(away_shot_counts) / len(away_shot_counts)
        away_var = sum((x - away_mean) ** 2 for x in away_shot_counts) / (len(away_shot_counts) - 1)
        
        total_mean = home_mean + away_mean
        total_var = home_var + away_var
        
        # Select distribution
        if total_var > total_mean and total_var > total_mean + 0.5:
            # Negative Binomial
            if total_var <= total_mean:
                total_var = total_mean + 0.5  # Ensure variance > mean
            
            r = (total_mean ** 2) / (total_var - total_mean)
            p = r / (r + total_mean)
            
            if r <= 0 or p <= 0 or p >= 1:
                model = "none"
                r = None
                p = None
            else:
                model = "negative_binomial"
        else:
            # Poisson
            model = "poisson"
            r = None
            p = None
        
        if model == "none":
            return ShotProduction(
                team_id="total",
                total_shots_distribution_model="none",
                expected_total_shots_mean=total_mean,
                expected_total_shots_variance=total_var,
                sample_size=min(len(home_shot_counts), len(away_shot_counts)),
                data_quality_score=0.0,
                uncertainty_score=1.0,
            )
        
        # Calculate total shot threshold probabilities
        total_probs = {}
        for threshold in self.TOTAL_SHOTS_THRESHOLDS:
            prob = self._threshold_probability(
                threshold=threshold,
                model=model,
                mu=total_mean,
                nb_r=r,
                nb_p=p
            )
            total_probs[threshold] = prob
        
        sample_size = min(len(home_shot_counts), len(away_shot_counts))
        data_quality = min(1.0, sample_size / (self.MIN_MATCHES_FOR_DISTRIBUTION * 2))
        
        return ShotProduction(
            team_id="total",
            expected_total_shots_mean=total_mean,
            expected_total_shots_variance=total_var,
            total_shots_distribution_model=model,
            total_over_20_prob=total_probs.get(20),
            total_over_22_prob=total_probs.get(22),
            total_over_25_prob=total_probs.get(25),
            total_over_30_prob=total_probs.get(30),
            sample_size=sample_size,
            data_quality_score=data_quality,
            uncertainty_score=1.0 - data_quality,
        )
    
    def _fit_distribution(
        self,
        values: List[float]
    ) -> Tuple[Optional[str], Optional[float], Optional[float], Optional[float], Optional[float]]:
        """Fit Poisson or Negative Binomial distribution to count data.
        
        Algorithm:
        1. Calculate mean μ and variance σ²
        2. If variance > mean: use Negative Binomial (overdispersed)
        3. If variance ≤ mean: use Poisson (equidispersed)
        4. For NegBin: r = μ²/(σ²-μ), p = r/(r+μ)
        5. Validate parameters (r > 0, 0 < p < 1)
        6. Return (model_name, μ, σ², r, p)
        
        Returns:
            Tuple of (model_name, mu, variance, nb_r, nb_p)
            Returns (None, None, None, None, None) if insufficient data or invalid parameters
        """
        if len(values) < 2:
            return (None, None, None, None, None)
        
        # Calculate mean and variance
        n = len(values)
        mu = sum(values) / n
        variance = sum((v - mu) ** 2 for v in values) / (n - 1)
        
        # Check for invalid values
        if mu <= 0:
            return (None, None, None, None, None)
        
        if variance <= 0:
            return (None, None, None, None, None)
        
        # Select distribution based on variance-to-mean ratio
        if variance > mu and variance > mu + 0.5:  # Overdispersed (with buffer)
            # Negative Binomial
            r = (mu ** 2) / (variance - mu)
            p = r / (r + mu)  # scipy parameterization: p = P(success) = r/(r+μ)
            
            # Validate parameters
            if r <= 0 or p <= 0 or p >= 1 or not math.isfinite(r) or not math.isfinite(p):
                return (None, None, None, None, None)
            
            return ("negative_binomial", mu, variance, r, p)
        else:
            # Poisson (equidispersed or underdispersed)
            return ("poisson", mu, variance, None, None)
    
    def _threshold_probability(
        self,
        threshold: int,
        model: str,
        mu: float,
        nb_r: Optional[float] = None,
        nb_p: Optional[float] = None
    ) -> Optional[float]:
        """Calculate P(X > threshold) using distribution CDF.
        
        For Negative Binomial: uses scipy.stats.nbinom(n=r, p=p)
        For Poisson: uses scipy.stats.poisson(mu=λ)
        
        Returns P(X > threshold) = 1 - CDF(threshold)
        
        Args:
            threshold: Threshold value T
            model: "poisson" or "negative_binomial"
            mu: Mean of distribution
            nb_r: Negative binomial r parameter (n in scipy)
            nb_p: Negative binomial p parameter (p in scipy)
            
        Returns:
            Probability P(X > threshold) or None if calculation fails
        """
        try:
            if model == "negative_binomial":
                if nb_r is None or nb_p is None:
                    return None
                
                # scipy.stats.nbinom(n, p) where p = P(success)
                # P(X > T) = 1 - P(X <= T) = 1 - CDF(T)
                cdf_value = nbinom.cdf(threshold, n=nb_r, p=nb_p)
                prob = 1.0 - cdf_value
                
            elif model == "poisson":
                # scipy.stats.poisson(mu)
                # P(X > T) = 1 - CDF(T)
                cdf_value = poisson.cdf(threshold, mu=mu)
                prob = 1.0 - cdf_value
                
            else:
                return None
            
            # Ensure valid probability
            if not math.isfinite(prob) or prob < 0 or prob > 1:
                return None
            
            return prob
            
        except Exception:
            return None
