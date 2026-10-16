"""Analysis context domain models."""

from datetime import datetime
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field

from app.domain.match import Match, Lineup
from app.domain.entities import Team, Competition
from app.domain.statistics import TeamMatchStatistic, Standing
from app.domain.availability import Injury, Suspension
from app.domain.odds import Odds
from app.domain.prediction import Prediction, PredictionMarket, Model
from app.domain.live import LiveMatchState, FeatureSnapshot


class AnalysisContext(BaseModel):
    """
    Structured analysis context for AI Analyst.
    
    This is the authoritative source of truth that will be passed to the AI Analyst.
    The AI Analyst must ONLY use information from this context and must NEVER
    invent or modify any numerical values.
    
    If information is missing, it will be None/empty, and the AI must explicitly
    state that information is unavailable.
    """

    # === Core Match Information ===
    match: Match = Field(..., description="Match details")
    home_team: Team = Field(..., description="Home team details")
    away_team: Team = Field(..., description="Away team details")
    competition: Competition = Field(..., description="Competition details")
    
    # === Recent Form ===
    home_recent_matches: Optional[List[Match]] = Field(
        None, description="Home team recent matches"
    )
    away_recent_matches: Optional[List[Match]] = Field(
        None, description="Away team recent matches"
    )
    home_form_string: Optional[str] = Field(
        None, description="Home form string (e.g., 'WWDLL')"
    )
    away_form_string: Optional[str] = Field(
        None, description="Away form string (e.g., 'WDWDL')"
    )
    
    # === Head-to-Head ===
    head_to_head_matches: Optional[List[Match]] = Field(
        None, description="Historical head-to-head matches"
    )
    h2h_home_wins: Optional[int] = Field(None, description="Home wins in H2H")
    h2h_draws: Optional[int] = Field(None, description="Draws in H2H")
    h2h_away_wins: Optional[int] = Field(None, description="Away wins in H2H")
    
    # === Team Strength Metrics ===
    home_team_strength: Optional[Dict[str, float]] = Field(
        None, description="Home team strength metrics"
    )
    away_team_strength: Optional[Dict[str, float]] = Field(
        None, description="Away team strength metrics"
    )
    
    # === League Standings ===
    home_standing: Optional[Standing] = Field(None, description="Home team standing")
    away_standing: Optional[Standing] = Field(None, description="Away team standing")
    
    # === Player Availability ===
    home_injuries: Optional[List[Injury]] = Field(
        None, description="Home team injuries"
    )
    away_injuries: Optional[List[Injury]] = Field(
        None, description="Away team injuries"
    )
    home_suspensions: Optional[List[Suspension]] = Field(
        None, description="Home team suspensions"
    )
    away_suspensions: Optional[List[Suspension]] = Field(
        None, description="Away team suspensions"
    )
    
    # === Lineups ===
    home_lineup: Optional[Lineup] = Field(None, description="Home team lineup")
    away_lineup: Optional[Lineup] = Field(None, description="Away team lineup")
    
    # === Statistical Features ===
    statistical_features: Optional[Dict[str, Optional[float]]] = Field(
        None, description="Calculated statistical features (None values indicate unavailable data)"
    )
    home_feature_snapshot: Optional[FeatureSnapshot] = Field(
        None, description="Home team feature snapshot"
    )
    away_feature_snapshot: Optional[FeatureSnapshot] = Field(
        None, description="Away team feature snapshot"
    )
    
    # === Expected Goals Data ===
    home_avg_xg: Optional[float] = Field(None, description="Home team average xG")
    away_avg_xg: Optional[float] = Field(None, description="Away team average xG")
    home_avg_xga: Optional[float] = Field(None, description="Home team average xGA")
    away_avg_xga: Optional[float] = Field(None, description="Away team average xGA")
    
    # === Model Predictions ===
    model_predictions: Optional[List[Prediction]] = Field(
        None, description="Individual model predictions"
    )
    models_used: Optional[List[Model]] = Field(
        None, description="Models that generated predictions"
    )
    
    # === Ensemble Prediction ===
    ensemble_prediction: Optional[Prediction] = Field(
        None, description="Combined ensemble prediction"
    )
    
    # === Prediction Markets ===
    prediction_markets: Optional[List[PredictionMarket]] = Field(
        None, description="Market-specific predictions"
    )
    
    # === Predicted Score ===
    predicted_score: Optional[str] = Field(
        None, description="Most likely scoreline (e.g., '3-1') - distinct from TUTAR X PICK"
    )
    
    # === Calibration Information ===
    model_calibration_info: Optional[Dict[str, float]] = Field(
        None, description="Model calibration metrics"
    )
    historical_accuracy: Optional[Dict[str, float]] = Field(
        None, description="Historical model accuracy"
    )
    
    # === TUTAR X PICK ===
    mensione_pick: Optional[Dict[str, Any]] = Field(
        None, description="TUTAR X recommended pick (field name: mensione_pick for backward compatibility)"
    )
    
    # === Prediction Versioning ===
    prediction_version_id: Optional[str] = Field(
        None, description="Unique identifier for this prediction version"
    )
    
    # === Market Odds ===
    market_odds: Optional[Odds] = Field(
        None, description="Bookmaker odds"
    )
    implied_probabilities: Optional[Dict[str, float]] = Field(
        None, description="Market implied probabilities"
    )
    
    # === Live Match State ===
    live_state: Optional[LiveMatchState] = Field(
        None, description="Current live match state"
    )
    live_prediction_update: Optional[Prediction] = Field(
        None, description="Updated prediction based on live state"
    )
    
    # === Data Quality ===
    data_freshness: Optional[datetime] = Field(
        None, description="When this context was assembled"
    )
    data_completeness: Optional[Dict[str, bool]] = Field(
        None, description="Flags indicating which data sections are available"
    )
    
    # === Shot Markets ===
    shot_markets: Optional[Dict[str, Any]] = Field(
        None, description="Shot market predictions (team shots, SOT, total shots)"
    )
    missing_data_notes: Optional[List[str]] = Field(
        None, description="Explicit notes about missing information"
    )
    
    # === Database-Backed Features ===
    feature_set: Optional[Dict[str, Any]] = Field(
        None, description="Complete feature set from database-backed feature engineering"
    )
    home_form_features: Optional[Dict[str, Any]] = Field(
        None, description="Home team form features (W/D/L, goals, form string)"
    )
    away_form_features: Optional[Dict[str, Any]] = Field(
        None, description="Away team form features (W/D/L, goals, form string)"
    )
    # Form metrics (structured form data for API response)
    home_form: Optional[Any] = Field(
        None, description="Home team form metrics (FormMetrics object)"
    )
    away_form: Optional[Any] = Field(
        None, description="Away team form metrics (FormMetrics object)"
    )
    attack_defence_home: Optional[Dict[str, Any]] = Field(
        None, description="Home team attack/defence features (goals/xG per match)"
    )
    attack_defence_away: Optional[Dict[str, Any]] = Field(
        None, description="Away team attack/defence features (goals/xG per match)"
    )
    match_context_features: Optional[Dict[str, Any]] = Field(
        None, description="Match context features (home advantage, rest days, form difference)"
    )
    data_quality_features: Optional[Dict[str, Any]] = Field(
        None, description="Data quality metrics (sample size, confidence, freshness)"
    )
    
    # === Provider Metadata ===
    provider_metadata: Optional[Dict[str, Any]] = Field(
        None, description="Metadata from the data provider (source, timestamps, IDs)"
    )
    selected_provider: Optional[str] = Field(
        None, description="Name of the provider used for this match data"
    )
    provider_fetched_at: Optional[datetime] = Field(
        None, description="When the provider data was fetched"
    )
    provider_updated_at: Optional[datetime] = Field(
        None, description="When the provider last updated the data"
    )
    data_freshness_seconds: Optional[int] = Field(
        None, description="Age of the data in seconds"
    )
    
    # === Latency Tracking ===
    latency_metrics: Optional[Dict[str, Any]] = Field(
        None, description="Real-time data latency metrics"
    )
    provider_to_mensione_ms: Optional[float] = Field(
        None, description="Latency from provider event to TUTAR X receipt (milliseconds, field name kept for backward compatibility)"
    )
    total_latency_ms: Optional[float] = Field(
        None, description="Total end-to-end latency (milliseconds)"
    )
    has_clock_skew: Optional[bool] = Field(
        None, description="Whether clock skew was detected in provider timestamps"
    )
    
    # === Warnings and Limitations ===
    warnings: Optional[List[str]] = Field(
        None, description="Warnings about data quality or limitations"
    )
    
    class Config:
        """Pydantic configuration."""

        from_attributes = True
        # Suppress warnings about model_* field names conflicting with Pydantic's namespace
        protected_namespaces = ()
        json_schema_extra = {
            "example": {
                "match": {
                    "id": "match_123",
                    "home_team_id": "team_1",
                    "away_team_id": "team_2",
                    "scheduled_at": "2026-10-05T15:00:00",
                },
                "home_team": {
                    "id": "team_1",
                    "name": "Team A",
                },
                "away_team": {
                    "id": "team_2",
                    "name": "Team B",
                },
                "competition": {
                    "id": "comp_1",
                    "name": "Premier League",
                },
                "data_completeness": {
                    "form": True,
                    "injuries": True,
                    "predictions": True,
                    "odds": False,
                },
                "missing_data_notes": [
                    "Market odds not available for this match",
                    "Player-level xG data not available",
                ],
            }
        }
