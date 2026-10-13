"""Prediction service for generating match predictions.

# Force reload for min_matches fix
import time

This service coordinates the canonical MENSIONE Intelligence Pipeline:
1. Feature extraction → MatchFeatureSnapshot
2. ModelOrchestrator → runs all compatible models
3. Ensemble → combines model outputs with reliability weighting
4. Calibration → calibrates ensemble probabilities
5. Confidence → assesses confidence from real pipeline values
6. Market Derivation → derives all markets from score distributions
7. TUTAR X Pick → generates recommended pick from markets
8. AnalysisContext → populates context for AI Analyst

The pipeline implements:
- Predicted Score vs TUTAR X PICK separation
- Multi-model ensemble with computed agreement (NOT hardcoded)
- Real confidence assessment from data quality, model agreement, calibration
- Comprehensive market derivation
- Immutable prediction versioning with full pipeline metadata
"""

from typing import Dict, Optional, List, Any, Tuple, Tuple
from datetime import datetime
from dataclasses import dataclass, field
import uuid

from sqlalchemy.orm import Session

from app.domain.match import Match
from app.domain.entities import Team, Competition
from app.domain.prediction import (
    Prediction,
    PredictionMarket,
    Model,
    ModelRun,
)
from app.domain.enums import PredictionMarketType, ModelType, MatchStatus
from app.domain.analysis import AnalysisContext
from app.features import MatchFeatureExtractor
from app.prediction.poisson import PoissonModel
from app.prediction.market_analysis import MarketAnalyser
from app.prediction.easy_matches import EasyMatchDetector
from app.prediction.market_derivation import MarketDerivationEngine
from app.prediction.prediction_version import PredictionVersionManager, PredictionStage
from app.prediction.confidence_engine import ConfidenceEngine, ConfidenceComponents, ConfidenceAssessment
from app.prediction.model_orchestrator import (
    ModelOrchestrator,
    EnsembleIntegration,
    CalibrationIntegration,
    ConfidenceIntegration,
    ModelOrchestrationResult,
)
from app.prediction.feature_snapshot import extract_feature_snapshot, MatchFeatureSnapshot
from app.prediction.data_quality import DataQualityGate, DataQualityReport
from app.prediction.interfaces import ModelPrediction
from app.providers.base import FootballDataProvider


@dataclass
class PipelineResult:
    """Result of complete MENSIONE pipeline execution.

    Single execution produces all outputs - no redundant feature extraction or model runs.
    """
    # Core inputs (required)
    snapshot: MatchFeatureSnapshot
    match: Match
    orchestration_result: ModelOrchestrationResult
    ensemble_prediction: ModelPrediction
    calibrated_prediction: ModelPrediction
    confidence_assessment: ConfidenceAssessment

    # Optional fields with defaults
    calibration_metadata: Dict[str, Any] = field(default_factory=dict)
    market_probabilities: Optional[Any] = None  # MarketProbabilities from market_derivation
    market_analysis: Optional[Any] = None  # MarketAnalysis from market_analyser
    mensione_pick: Optional[Dict[str, Any]] = None
    easy_match: Optional[Dict[str, Any]] = None
    prediction_version: Optional[Any] = None  # PredictionVersion
    analysis_context: Optional[AnalysisContext] = None
    execution_time_ms: float = 0.0
    pipeline_version: str = "1.0.0"
    pipeline_metadata: Dict[str, Any] = field(default_factory=dict)


from dataclasses import dataclass


@dataclass
class PredictionServiceConfig:
    """Configuration for PredictionService behavior.

    This configuration controls how the service handles missing data
    and other runtime behaviors.
    """
    min_matches: int = 3
    min_sample_size: int = 5
    allow_dev_baseline_fallback: bool = False  # EXPLICIT control for production safety
    is_development: bool = False  # True for development mode

    @classmethod
    def for_production(cls, min_matches: int = 5, min_sample_size: int = 8) -> "PredictionServiceConfig":
        """Create production-safe configuration.

        Production config:
        - Higher minimum data requirements
        - NO baseline fallback (missing data returns None)
        """
        return cls(
            min_matches=min_matches,
            min_sample_size=min_sample_size,
            allow_dev_baseline_fallback=False,  # Never allow in production
            is_development=False
        )

    @classmethod
    def for_development(cls, min_matches: int = 3, min_sample_size: int = 5) -> "PredictionServiceConfig":
        """Create development configuration.

        Development config:
        - Lower minimum data requirements
        - Baseline fallback allowed (enables testing with minimal data)
        """
        return cls(
            min_matches=min_matches,
            min_sample_size=min_sample_size,
            allow_dev_baseline_fallback=True,  # Allow for dev/testing
            is_development=True
        )


class PredictionService:
    """Service for generating match predictions.

    This service:
    1. Extracts features using MatchFeatureExtractor
    2. Runs prediction models (currently Poisson)
    3. Generates structured Prediction and PredictionMarket objects
    4. Populates AnalysisContext for AI Analyst consumption

    The service does NOT invent missing data. If features are insufficient,
    predictions will indicate unavailability.
    """

    def __init__(
        self,
        provider: FootballDataProvider,
        poisson_model: Optional[PoissonModel] = None,
        feature_extractor: Optional[MatchFeatureExtractor] = None,
        market_analyser: Optional[MarketAnalyser] = None,
        db_session: Optional[Session] = None,
        min_matches: Optional[int] = None,  # None → use the mode's default (prod 5 / dev 3)
        min_sample_size: Optional[int] = None,  # None → use the mode's default (prod 8 / dev 5)
        config: Optional[PredictionServiceConfig] = None,
    ):
        """Initialize prediction service with canonical pipeline components.

        Args:
            provider: Data provider for fetching match/team data
            poisson_model: Poisson model instance (default: create new)
            feature_extractor: Feature extractor (default: create new)
            market_analyser: Market analyser (default: create new)
            db_session: Optional database session for database-backed features
            min_matches: Minimum matches required for feature extraction (default: mode default)
            min_sample_size: Minimum sample size for confidence gate (default: mode default)
            config: Service configuration (optional, auto-detects from provider if None)
        """
        self.provider = provider
        self.db_session = db_session
        self.poisson_model = poisson_model or PoissonModel(max_goals=10)

        # Configuration: auto-detect or use provided
        if config is None:
            # Development/production mode from config (explicit control).
            # Only explicitly passed thresholds override the mode defaults;
            # previously hardcoded 1/3 silently replaced production's 5/8.
            from app.config import settings
            is_dev = settings.is_development  # bool, env: FI_IS_DEVELOPMENT=true
            overrides = {}
            if min_matches is not None:
                overrides["min_matches"] = min_matches
            if min_sample_size is not None:
                overrides["min_sample_size"] = min_sample_size
            if is_dev:
                self.config = PredictionServiceConfig.for_development(**overrides)
            else:
                self.config = PredictionServiceConfig.for_production(**overrides)
        else:
            self.config = config

        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[PREDICTION_SERVICE] Initializing with db_session: {type(db_session) if db_session else None}")

        self.feature_extractor = feature_extractor or MatchFeatureExtractor(
            provider=provider,
            min_matches=self.config.min_matches,
            recent_matches=5,
            db_session=db_session  # Pass db_session for optimized queries
        )
        self.market_analyser = market_analyser or MarketAnalyser(
            value_threshold=0.03,
            is_development_data=self.config.is_development,
        )
        self.easy_match_detector = EasyMatchDetector()

        # Initialize MENSIONE components
        self.market_derivation_engine = MarketDerivationEngine(top_scorelines=20)
        from app.prediction.market_selector import SmartMarketSelector
        self.market_selector = SmartMarketSelector(
            min_confidence=0.4,
            min_probability=0.5,
            min_edge=0.0,
            max_risk_level="HIGH"
        )
        self.confidence_engine = ConfidenceEngine()

        # BUGFIX #10: Use database-backed persistence if db_session available
        if db_session:
            try:
                from app.services.prediction_persistence import PredictionPersistenceService
                persistence_service = PredictionPersistenceService(session=db_session)
                self.version_manager = PredictionVersionManager(persistence_service=persistence_service)
            except ImportError:
                logging.warning("PredictionPersistenceService not available, using in-memory version manager")
                self.version_manager = PredictionVersionManager(persistence_service=None)
        else:
            self.version_manager = PredictionVersionManager(persistence_service=None)  # In-memory for testing

        # CANONICAL PIPELINE COMPONENTS
        # ModelOrchestrator with all 7 models registered
        self.model_orchestrator = ModelOrchestrator.create_default_registry()

        # Integration layers
        # Phase 10.3: Use optimized ensemble weights with caching (Section 7 optimization)
        try:
            from app.prediction.model_cache import load_ensemble_cached
            self.ensemble_integration = load_ensemble_cached()
        except Exception as e:
            import logging
            logging.warning(f"Could not load cached ensemble, using default: {e}")
            self.ensemble_integration = EnsembleIntegration.create_default()

        # Load trained calibration if available (Phase 10.3) with caching (Section 7 optimization)
        try:
            from app.prediction.model_cache import create_calibration_integration_cached
            self.calibration_integration = create_calibration_integration_cached()
        except Exception as e:
            import logging
            logging.warning(f"Could not load cached calibration, using default: {e}")
            self.calibration_integration = CalibrationIntegration.create_default()

        self.confidence_integration = ConfidenceIntegration()

        # Data quality gate (simplified check - not full quality engine)
        self.data_quality_gate = DataQualityGate()

        # Initialize database-backed feature aggregator if session available
        self.feature_aggregator = None
        if db_session:
            try:
                from app.features.aggregator import FeatureAggregator
                self.feature_aggregator = FeatureAggregator(
                    session=db_session,
                    min_matches=3,
                    form_window=5
                )
            except ImportError:
                # Database features not available
                pass

        # NEW: FEAT-003 - Initialize shot market engine
        self.shot_market_engine = None
        if db_session:
            try:
                from app.prediction.shot_market_engine import ShotMarketEngine
                self.shot_market_engine = ShotMarketEngine(session=db_session)
            except ImportError:
                # Shot market engine not available
                pass
            except Exception as e:
                import logging
                logging.warning(f"ShotMarketEngine initialization failed: {e}")

        # Model metadata
        self.poisson_model_metadata = Model(
            id="poisson_v1",
            name="Poisson Model",
            type=ModelType.POISSON,
            version="1.0.0",
            description="Foundational Poisson-based prediction model",
            parameters={"max_goals": float(self.poisson_model.max_goals)},
            created_at=datetime.now(),
            is_active=True,
        )

    def generate_prediction(self, match: Match) -> Optional[Prediction]:
        """Generate prediction for a match.

        Args:
            match: Match to generate prediction for

        Returns:
            Prediction object or None if insufficient data
        """
        # OPTIMIZATION: Extract features once and reuse
        features = self.feature_extractor.extract_features(match)

        # Filter features to only numeric values (exclude IDs and timestamps)
        statistical_features = {
            k: v for k, v in features.items()
            if k not in ["match_id", "competition_id", "season_id", "home_team_id", "away_team_id", "scheduled_timestamp"]
            and v is not None
        }

        # Only set statistical_features if we have any numeric features
        if not statistical_features:
            statistical_features = None

        # Check if we have sufficient data for both teams
        home_attack = features.get("home_attack_strength")
        away_attack = features.get("away_attack_strength")
        home_defense = features.get("home_defense_strength")
        away_defense = features.get("away_defense_strength")

        if any(v is None for v in [home_attack, away_attack, home_defense, away_defense]):
            # PRODUCTION SAFETY: Only allow baseline fallback if explicitly configured
            # This prevents production systems from silently masking insufficient data
            if self.config.allow_dev_baseline_fallback:
                # Development mode: use neutral baseline (1.0 = league average)
                # This allows dev/testing with minimal data
                home_attack = home_attack if home_attack is not None else 1.0
                away_attack = away_attack if away_attack is not None else 1.0
                home_defense = home_defense if home_defense is not None else 1.0
                away_defense = away_defense if away_defense is not None else 1.0
            else:
                # Production mode: insufficient data → return None
                # Never mask missing data in production
                return None

        # Estimate lambda parameters
        # Home team expected goals based on home attack vs away defense
        home_lambda = self.poisson_model.estimate_lambda_from_features(
            team_attack_strength=home_attack,
            opponent_defense_strength=away_defense,
            venue_adjustment=1.0,  # Can be enhanced with home advantage
        )

        # Away team expected goals based on away attack vs home defense
        away_lambda = self.poisson_model.estimate_lambda_from_features(
            team_attack_strength=away_attack,
            opponent_defense_strength=home_defense,
            venue_adjustment=1.0,
        )

        # Run Poisson model
        poisson_result = self.poisson_model.predict_from_lambda(
            home_lambda=home_lambda,
            away_lambda=away_lambda,
        )

        # Create Prediction object
        prediction_id = f"pred_{uuid.uuid4().hex[:12]}"

        # Convert top scorelines to score distribution
        score_distribution = {
            f"{h}-{a}": prob
            for (h, a), prob in poisson_result.top_scorelines
        }

        prediction = Prediction(
            id=prediction_id,
            match_id=match.id,
            model_id=self.poisson_model_metadata.id,
            home_win_probability=poisson_result.home_win_probability,
            draw_probability=poisson_result.draw_probability,
            away_win_probability=poisson_result.away_win_probability,
            home_xg=home_lambda,
            away_xg=away_lambda,
            predicted_home_score=home_lambda,  # Expected value
            predicted_away_score=away_lambda,
            btts_probability=poisson_result.btts_yes_probability,
            score_distribution=score_distribution,
            generated_at=datetime.now(),
            confidence=None,  # Not calculated yet
        )

        return prediction

    def generate_prediction_markets(
        self,
        match: Match,
        prediction: Prediction,
        features: Optional[Dict[str, Optional[float]]] = None,
    ) -> List[PredictionMarket]:
        """Generate market-specific predictions.

        Args:
            match: Match being predicted
            prediction: Base prediction with probabilities
            features: Pre-extracted features (optional, will extract if not provided)

        Returns:
            List of PredictionMarket objects
        """
        markets = []

        # OPTIMIZATION: Reuse features if provided, else extract
        if features is None:
            features = self.feature_extractor.extract_features(match)
        home_attack = features.get("home_attack_strength")
        away_attack = features.get("away_attack_strength")
        home_defense = features.get("home_defense_strength")
        away_defense = features.get("away_defense_strength")

        if any(v is None for v in [home_attack, away_attack, home_defense, away_defense]):
            # PRODUCTION SAFETY: Only allow baseline fallback if explicitly configured
            if self.config.allow_dev_baseline_fallback:
                home_attack = home_attack if home_attack is not None else 1.0
                away_attack = away_attack if away_attack is not None else 1.0
                home_defense = home_defense if home_defense is not None else 1.0
                away_defense = away_defense if away_defense is not None else 1.0
            else:
                # Production: insufficient data → return empty markets
                return markets

        home_lambda = self.poisson_model.estimate_lambda_from_features(
            home_attack, away_defense, 1.0
        )
        away_lambda = self.poisson_model.estimate_lambda_from_features(
            away_attack, home_defense, 1.0
        )

        poisson_result = self.poisson_model.predict_from_lambda(home_lambda, away_lambda)

        # 1X2 Market
        markets.append(PredictionMarket(
            id=f"market_{uuid.uuid4().hex[:12]}",
            prediction_id=prediction.id,
            market_type=PredictionMarketType.MATCH_RESULT,
            probabilities={
                "home": poisson_result.home_win_probability,
                "draw": poisson_result.draw_probability,
                "away": poisson_result.away_win_probability,
            },
        ))

        # BTTS Market
        markets.append(PredictionMarket(
            id=f"market_{uuid.uuid4().hex[:12]}",
            prediction_id=prediction.id,
            market_type=PredictionMarketType.BTTS,
            probabilities={
                "yes": poisson_result.btts_yes_probability,
                "no": poisson_result.btts_no_probability,
            },
        ))

        # Over/Under Markets
        for line, (over_prob, under_prob) in poisson_result.over_under_probabilities.items():
            markets.append(PredictionMarket(
                id=f"market_{uuid.uuid4().hex[:12]}",
                prediction_id=prediction.id,
                market_type=PredictionMarketType.OVER_UNDER,
                line=line,
                probabilities={
                    "over": over_prob,
                    "under": under_prob,
                },
            ))

        # Correct Score Market (top 10 scorelines)
        correct_score_probs = {
            f"{h}-{a}": prob
            for (h, a), prob in poisson_result.top_scorelines[:10]
        }
        markets.append(PredictionMarket(
            id=f"market_{uuid.uuid4().hex[:12]}",
            prediction_id=prediction.id,
            market_type=PredictionMarketType.CORRECT_SCORE,
            probabilities=correct_score_probs,
        ))

        return markets

    def generate_market_analysis(
        self,
        match: Match,
        prediction: Prediction,
        bookmaker_odds: Optional[Dict] = None,
    ):
        """Generate market analysis for a match prediction.

        Args:
            match: Match being analyzed
            prediction: Base prediction with probabilities
            bookmaker_odds: Optional real bookmaker odds (never fabricated)
                Format: {
                    "1x2": {"home": 2.0, "draw": 3.5, "away": 3.8},
                    "btts": {"yes": 1.75, "no": 2.05},
                    "ou_2_5": {"over": 1.85, "under": 1.95},
                    "ou_3_5": {"over": 2.3, "under": 1.6},
                }

        Returns:
            MatchMarketAnalysis or None if prediction unavailable
        """
        if prediction is None:
            return None

        # Re-run Poisson for detailed probabilities
        features = self.feature_extractor.extract_features(match)
        home_attack = features.get("home_attack_strength")
        away_attack = features.get("away_attack_strength")
        home_defense = features.get("home_defense_strength")
        away_defense = features.get("away_defense_strength")

        if any(v is None for v in [home_attack, away_attack, home_defense, away_defense]):
            return None

        home_lambda = self.poisson_model.estimate_lambda_from_features(
            home_attack, away_defense, 1.0
        )
        away_lambda = self.poisson_model.estimate_lambda_from_features(
            away_attack, home_defense, 1.0
        )

        poisson_result = self.poisson_model.predict_from_lambda(home_lambda, away_lambda)

        # Extract bookmaker odds if provided
        bookie_1x2 = None
        bookie_btts = None
        bookie_ou25 = None
        bookie_ou35 = None

        if bookmaker_odds:
            bookie_1x2 = bookmaker_odds.get("1x2")
            bookie_btts = bookmaker_odds.get("btts")
            bookie_ou25 = bookmaker_odds.get("ou_2_5")
            bookie_ou35 = bookmaker_odds.get("ou_3_5")

        # Get over/under probabilities
        over_under_2_5 = poisson_result.over_under_probabilities.get(2.5)
        over_under_3_5 = poisson_result.over_under_probabilities.get(3.5)

        over_2_5_prob = over_under_2_5[0] if over_under_2_5 else None
        over_3_5_prob = over_under_3_5[0] if over_under_3_5 else None

        # Generate correct score probabilities dict
        correct_score_probs = {
            f"{h}-{a}": prob
            for (h, a), prob in poisson_result.top_scorelines
        }

        # Use market analyser
        market_analysis = self.market_analyser.analyse_match(
            match_id=match.id,
            home_win_prob=poisson_result.home_win_probability,
            draw_prob=poisson_result.draw_probability,
            away_win_prob=poisson_result.away_win_probability,
            btts_prob=poisson_result.btts_yes_probability,
            over_2_5_prob=over_2_5_prob,
            over_3_5_prob=over_3_5_prob,
            correct_score_probs=correct_score_probs,
            bookmaker_1x2=bookie_1x2,
            bookmaker_btts=bookie_btts,
            bookmaker_ou25=bookie_ou25,
            bookmaker_ou35=bookie_ou35,
        )

        return market_analysis

    def detect_easy_match(
        self,
        match: Match,
        prediction: Prediction,
    ):
        """Detect if a match qualifies as an Easy Match.

        Args:
            match: Match being analyzed
            prediction: Calibrated prediction with probabilities

        Returns:
            EasyMatchResult or None if prediction unavailable
        """
        if prediction is None:
            return None

        # Use calibrated probabilities from the main prediction pipeline
        # instead of recalculating with raw Poisson
        easy_match_result = self.easy_match_detector.detect(
            match_id=match.id,
            home_win_prob=prediction.home_win_probability,
            draw_prob=prediction.draw_probability,
            away_win_prob=prediction.away_win_probability,
            btts_prob=prediction.btts_probability,
            home_xg=prediction.home_xg,
            away_xg=prediction.away_xg,
            has_sufficient_historical_data=True,
        )

        return easy_match_result

    def build_analysis_context(
        self,
        match: Match,
        prediction: Optional[Prediction] = None,
        prediction_markets: Optional[List[PredictionMarket]] = None,
        match_db_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        pass_reason: Optional[str] = None,
        features: Optional[Dict[str, Optional[float]]] = None,
    ) -> AnalysisContext:
        """Build AnalysisContext for AI Analyst.

        This context contains all information available for the match.
        Missing information is explicitly represented as None.

        Args:
            match: Match to analyze
            prediction: Generated prediction (if available)
            prediction_markets: Generated markets (if available)
            match_db_id: Optional database match ID for database-backed features
            correlation_id: Optional correlation ID for logging
            features: Pre-extracted features (optional, will extract if not provided)

        Returns:
            AnalysisContext with all available information
        """
        import time
        import logging
        logger = logging.getLogger(__name__)

        if correlation_id is None:
            correlation_id = "none"

        context_start = time.time()
        logger.info(f"[{correlation_id}] build_analysis_context: Starting")

        # Get basic entities (with timeout protection)
        step_start = time.time()
        logger.info(f"[{correlation_id}] build_analysis_context: Getting teams")
        try:
            import concurrent.futures
            import logging
            logger = logging.getLogger(__name__)

            def get_teams_with_timeout():
                return self.provider.get_teams(match.competition_id, match.season_id)

            # Use ThreadPoolExecutor with 2-second timeout
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(get_teams_with_timeout)
                try:
                    teams = future.result(timeout=2.0)  # 2-second timeout
                    home_team = next((t for t in teams if t.id == match.home_team_id), None)
                    if home_team is None:
                        home_team = Team(id=match.home_team_id, name=match.home_team_id)
                except concurrent.futures.TimeoutError:
                    logger.warning(f"[{correlation_id}] Provider call for teams timed out for match {match.id}")
                    home_team = Team(id=match.home_team_id, name=match.home_team_id)
        except (NotImplementedError, StopIteration, Exception):
            home_team = Team(id=match.home_team_id, name=match.home_team_id)

        step_time = (time.time() - step_start) * 1000
        logger.info(f"[{correlation_id}] build_analysis_context: Teams lookup complete ({step_time:.1f}ms)")

        try:
            # Reuse teams if we got them above, otherwise timeout-protected call
            if 'teams' not in locals():
                def get_teams_with_timeout():
                    return self.provider.get_teams(match.competition_id, match.season_id)

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(get_teams_with_timeout)
                    try:
                        teams = future.result(timeout=2.0)
                    except concurrent.futures.TimeoutError:
                        logger.warning(f"[{correlation_id}] Provider call for teams timed out for match {match.id}")
                        teams = []

            away_team = next((t for t in teams if t.id == match.away_team_id), None)
            if away_team is None:
                away_team = Team(id=match.away_team_id, name=match.away_team_id)
        except (NotImplementedError, StopIteration, Exception):
            away_team = Team(id=match.away_team_id, name=match.away_team_id)

        # Get competitions
        step_start = time.time()
        logger.info(f"[{correlation_id}] build_analysis_context: Getting competitions")
        try:
            def get_competitions_with_timeout():
                return self.provider.get_competitions()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(get_competitions_with_timeout)
                try:
                    competitions = future.result(timeout=2.0)  # 2-second timeout
                    competition = next((c for c in competitions if c.id == match.competition_id), None)
                    if competition is None:
                        competition = Competition(
                            id=match.competition_id,
                            name=match.competition_id,
                            country="Unknown",
                            level=1,
                        )
                except concurrent.futures.TimeoutError:
                    logger.warning(f"[{correlation_id}] Provider call for competitions timed out for match {match.id}")
                    competition = Competition(
                        id=match.competition_id,
                        name=match.competition_id,
                        country="Unknown",
                        level=1,
                    )
        except (NotImplementedError, StopIteration, Exception):
            competition = Competition(
                id=match.competition_id,
                name=match.competition_id,
                country="Unknown",
                level=1,
            )

        step_time = (time.time() - step_start) * 1000
        logger.info(f"[{correlation_id}] build_analysis_context: Competitions lookup complete ({step_time:.1f}ms)")

        # Try to extract database-backed features if available
        step_start = time.time()
        logger.info(f"[{correlation_id}] build_analysis_context: Extracting database features")
        feature_set = None
        db_features_available = False
        if self.feature_aggregator and match_db_id:
            try:
                feature_set = self.feature_aggregator.extract_features_for_match(match_db_id)
                db_features_available = feature_set.features_available
            except Exception:
                # Database features extraction failed, fall back to provider-based
                pass

        step_time = (time.time() - step_start) * 1000
        logger.info(f"[{correlation_id}] build_analysis_context: Database features complete ({step_time:.1f}ms)")

        # Extract provider-based features (always as fallback)
        # OPTIMIZATION: Reuse features if provided, else extract
        step_start = time.time()
        logger.info(f"[{correlation_id}] build_analysis_context: Extracting provider features")
        if features is None:
            features = self.feature_extractor.extract_features(match)
        else:
            logger.info(f"[{correlation_id}] build_analysis_context: Reusing pre-extracted features (OPTIMIZATION)")

        step_time = (time.time() - step_start) * 1000
        logger.info(f"[{correlation_id}] build_analysis_context: Provider features complete ({step_time:.1f}ms)")

        # Filter features to exclude metadata fields (IDs and timestamps)
        # Keep None values to explicitly represent unavailable data
        statistical_features = {
            k: v for k, v in features.items()
            if k not in ["match_id", "competition_id", "season_id", "home_team_id", "away_team_id", "scheduled_timestamp"]
        }

        # Merge database features if available
        if feature_set and db_features_available:
            # Add database feature quality metrics
            if feature_set.data_quality:
                statistical_features["db_sample_size_home"] = feature_set.data_quality.get("sample_size_home")
                statistical_features["db_sample_size_away"] = feature_set.data_quality.get("sample_size_away")
                statistical_features["db_xg_available_home"] = feature_set.data_quality.get("xg_available_home")
                statistical_features["db_xg_available_away"] = feature_set.data_quality.get("xg_available_away")
                statistical_features["db_feature_confidence"] = feature_set.data_quality.get("feature_confidence")

        # Only set statistical_features if we have any feature keys
        if not statistical_features:
            statistical_features = None

        # Get recent matches for form (with timeout protection)
        step_start = time.time()
        logger.info(f"[{correlation_id}] build_analysis_context: Getting recent matches for form")
        try:
            import concurrent.futures
            import logging

            def get_comp_matches_with_timeout():
                return self.provider.get_matches(
                    competition_id=match.competition_id,
                    season_id=match.season_id,
                )

            # Use ThreadPoolExecutor with 3-second timeout to prevent blocking
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(get_comp_matches_with_timeout)
                try:
                    all_matches = future.result(timeout=3.0)  # 3-second timeout

                    # Filter to before target match (with timezone compatibility)
                    historical = []
                    for m in all_matches:
                        try:
                            # Convert both datetimes to UTC naive for comparison
                            m_dt = m.scheduled_at.replace(tzinfo=None) if hasattr(m.scheduled_at, 'tzinfo') and m.scheduled_at.tzinfo else m.scheduled_at
                            match_dt = match.scheduled_at.replace(tzinfo=None) if hasattr(match.scheduled_at, 'tzinfo') and match.scheduled_at.tzinfo else match.scheduled_at

                            if m_dt < match_dt and m.id != match.id:
                                historical.append(m)
                        except (AttributeError, TypeError):
                            # Skip problematic datetime objects
                            continue
                    historical.sort(key=lambda m: m.scheduled_at)

                    home_recent = [
                        m for m in historical
                        if m.home_team_id == match.home_team_id or m.away_team_id == match.home_team_id
                    ][-5:]

                    away_recent = [
                        m for m in historical
                        if m.home_team_id == match.away_team_id or m.away_team_id == match.away_team_id
                    ][-5:]

                except concurrent.futures.TimeoutError:
                    logger.warning(f"[{correlation_id}] Provider call for competition matches timed out after 3 seconds for match {match.id}, using no recent matches")
                    home_recent = None
                    away_recent = None

        except (NotImplementedError, Exception) as e:
            logger.warning(f"[{correlation_id}] Provider call for competition matches failed for match {match.id}: {e}, using no recent matches")
            home_recent = None
            away_recent = None

        step_time = (time.time() - step_start) * 1000
        logger.info(f"[{correlation_id}] build_analysis_context: Recent matches complete ({step_time:.1f}ms)")

        # Get head-to-head matches (from database if available)
        step_start = time.time()
        logger.info(f"[{correlation_id}] build_analysis_context: Getting H2H matches")
        h2h_matches = None
        h2h_home_wins = None
        h2h_draws = None
        h2h_away_wins = None

        if self.db_session:
            try:
                from app.database.models import Match as DBMatch

                # Query H2H matches: both home/away and away/home combinations
                h2h_query = self.db_session.query(DBMatch).filter(
                    (
                        ((DBMatch.home_team_id == match.home_team_id) & (DBMatch.away_team_id == match.away_team_id)) |
                        ((DBMatch.home_team_id == match.away_team_id) & (DBMatch.away_team_id == match.home_team_id))
                    ),
                    DBMatch.status == MatchStatus.FINISHED,
                    DBMatch.scheduled_at < match.scheduled_at
                ).order_by(DBMatch.scheduled_at.desc()).limit(10)

                h2h_matches = h2h_query.all()

                if h2h_matches:
                    # Calculate H2H stats from perspective of current match's home team
                    h2h_home_wins = 0
                    h2h_draws = 0
                    h2h_away_wins = 0

                    for h2h_match in h2h_matches:
                        # Determine outcome from current home team's perspective
                        if h2h_match.outcome:
                            if h2h_match.home_team_id == match.home_team_id:
                                # H2H match where current home team was home
                                if h2h_match.outcome == 'home_win':
                                    h2h_home_wins += 1
                                elif h2h_match.outcome == 'draw':
                                    h2h_draws += 1
                                elif h2h_match.outcome == 'away_win':
                                    h2h_away_wins += 1
                            else:
                                # H2H match where current home team was away
                                if h2h_match.outcome == 'away_win':
                                    h2h_home_wins += 1
                                elif h2h_match.outcome == 'draw':
                                    h2h_draws += 1
                                elif h2h_match.outcome == 'home_win':
                                    h2h_away_wins += 1

                    logger.info(f"[{correlation_id}] Found {len(h2h_matches)} H2H matches: {h2h_home_wins}W-{h2h_draws}D-{h2h_away_wins}L")
            except Exception as e:
                logger.warning(f"[{correlation_id}] H2H extraction failed: {e}")
                h2h_matches = None

        step_time = (time.time() - step_start) * 1000
        logger.info(f"[{correlation_id}] build_analysis_context: H2H matches complete ({step_time:.1f}ms)")

        # Get standings (with timeout protection)
        step_start = time.time()
        logger.info(f"[{correlation_id}] build_analysis_context: Getting standings")
        try:
            def get_standings_with_timeout():
                return self.provider.get_standings(
                    competition_id=match.competition_id,
                    season_id=match.season_id,
                )

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(get_standings_with_timeout)
                try:
                    standings = future.result(timeout=2.0)  # 2-second timeout
                    home_standing = next(
                        (s for s in standings if s.team_id == match.home_team_id),
                        None
                    )
                    away_standing = next(
                        (s for s in standings if s.team_id == match.away_team_id),
                        None
                    )
                except concurrent.futures.TimeoutError:
                    logger.warning(f"[{correlation_id}] Provider call for standings timed out for match {match.id}")
                    home_standing = None
                    away_standing = None
        except (NotImplementedError, StopIteration, Exception):
            home_standing = None
            away_standing = None

        step_time = (time.time() - step_start) * 1000
        logger.info(f"[{correlation_id}] build_analysis_context: Standings complete ({step_time:.1f}ms)")

        # Build team strength dictionaries from features
        step_start = time.time()
        logger.info(f"[{correlation_id}] build_analysis_context: Building team strengths")
        home_strength = None
        away_strength = None

        if any(v is not None for k, v in features.items() if k.startswith("home_") and k not in ["home_team_id"]):
            home_strength = {
                "attack_strength": features.get("home_attack_strength"),
                "defense_strength": features.get("home_defense_strength"),
                "home_venue_strength": features.get("home_home_strength"),
                "away_venue_strength": features.get("home_away_strength"),
            }
            # Filter out None values to avoid AnalysisContext validation errors
            home_strength = {k: v for k, v in home_strength.items() if v is not None}

        if any(v is not None for k, v in features.items() if k.startswith("away_") and k not in ["away_team_id"]):
            away_strength = {
                "attack_strength": features.get("away_attack_strength"),
                "defense_strength": features.get("away_defense_strength"),
                "home_venue_strength": features.get("away_home_strength"),
                "away_venue_strength": features.get("away_away_strength"),
            }
            # Filter out None values to avoid AnalysisContext validation errors
            away_strength = {k: v for k, v in away_strength.items() if v is not None}

        step_time = (time.time() - step_start) * 1000
        logger.info(f"[{correlation_id}] build_analysis_context: Team strengths complete ({step_time:.1f}ms)")

        # Determine data completeness
        step_start = time.time()
        logger.info(f"[{correlation_id}] build_analysis_context: Building data completeness")
        data_completeness = {
            "match": True,
            "teams": True,
            "competition": True,
            "features": any(v is not None for k, v in features.items() if k not in ["match_id", "home_team_id", "away_team_id", "competition_id", "season_id", "scheduled_timestamp"]),
            "database_features": db_features_available,
            "prediction": prediction is not None,
            "markets": prediction_markets is not None and len(prediction_markets) > 0,
            "form": home_recent is not None and away_recent is not None,
            "standings": home_standing is not None and away_standing is not None,
        }

        # Collect missing data notes
        missing_notes = []
        if not data_completeness["features"]:
            missing_notes.append("Insufficient historical data for feature calculation")
        if not data_completeness["prediction"]:
            missing_notes.append("Prediction not generated due to insufficient data")
        if not data_completeness["standings"]:
            missing_notes.append("League standings not available")
        if feature_set and feature_set.notes:
            missing_notes.extend(feature_set.notes)

        step_time = (time.time() - step_start) * 1000
        logger.info(f"[{correlation_id}] build_analysis_context: Data completeness complete ({step_time:.1f}ms)")

        # Build context
        step_start = time.time()
        logger.info(f"[{correlation_id}] build_analysis_context: Building final context")
        context = AnalysisContext(
            match=match,
            home_team=home_team,
            away_team=away_team,
            competition=competition,
            home_recent_matches=home_recent,
            away_recent_matches=away_recent,
            head_to_head_matches=h2h_matches,
            h2h_home_wins=h2h_home_wins,
            h2h_draws=h2h_draws,
            h2h_away_wins=h2h_away_wins,
            home_standing=home_standing,
            away_standing=away_standing,
            home_team_strength=home_strength,
            away_team_strength=away_strength,
            statistical_features=statistical_features,
            model_predictions=[prediction] if prediction else None,
            models_used=[self.poisson_model_metadata] if prediction else None,
            prediction_markets=prediction_markets,
            data_freshness=datetime.now(),
            data_completeness=data_completeness,
            missing_data_notes=missing_notes if missing_notes else None,
        )

        total_context_time = (time.time() - context_start) * 1000
        logger.info(f"[{correlation_id}] build_analysis_context: Final context complete ({step_time:.1f}ms)")
        logger.info(f"[{correlation_id}] build_analysis_context: TOTAL TIME {total_context_time:.1f}ms")

        return context

    def predict_match(self, match: Match) -> AnalysisContext:
        """Complete prediction pipeline for a match.

        This is the main entry point for generating a full prediction
        and analysis context.

        Args:
            match: Match to predict

        Returns:
            AnalysisContext with prediction and all available data
        """
        # OPTIMIZATION: Extract features once at the start
        features = self.feature_extractor.extract_features(match)

        # Generate prediction (will reuse features internally)
        prediction = self.generate_prediction(match)

        # Generate markets if prediction exists
        markets = None
        if prediction is not None:
            # OPTIMIZATION: Reuse features from previous extraction
            markets = self.generate_prediction_markets(match, prediction, features=features)

        # Build analysis context (will reuse features internally)
        context = self.build_analysis_context(
            match=match,
            prediction=prediction,
            prediction_markets=markets,
            features=features,
        )

        return context

    def _evaluate_withdrawal_conditions(
        self,
        snapshot: MatchFeatureSnapshot,
        orchestration_result: ModelOrchestrationResult,
        confidence_assessment,
        calibration_metadata: Dict[str, Any],
        correlation_id: str
    ) -> bool:
        """Evaluate whether prediction should be withdrawn (PASS decision).

        PHASE 6: Enhanced reliability checks for ensemble/calibration pipeline.

        Returns True if prediction should be withdrawn due to:
        - Insufficient data (below min_sample_size=3)
        - Poor calibration reliability
        - Low model agreement
        - High uncertainty
        """
        import logging
        logger = logging.getLogger(__name__)

        # 1. Check minimum sample size requirement
        if hasattr(snapshot, 'data_quality') and snapshot.data_quality:
            n_matches = getattr(snapshot.data_quality, 'total_matches', 0)
            if n_matches < self.config.min_sample_size:
                logger.info(f"[{correlation_id}] PASS: Insufficient data - {n_matches} < {self.config.min_sample_size}")
                return True

        # 2. Check calibration reliability
        calibration_status = calibration_metadata.get("calibration_status", "unknown")
        if calibration_status == "failed":
            logger.info(f"[{correlation_id}] PASS: Calibration failed")
            return True

        # Check if calibration has insufficient samples
        calibration_samples = calibration_metadata.get("calibration_sample_size", 0)
        if calibration_samples > 0 and calibration_samples < 30:  # MIN_SAMPLES_FOR_CALIBRATION
            logger.info(f"[{correlation_id}] PASS: Insufficient calibration data - {calibration_samples} < 30")
            return True

        # 3. Check model agreement
        n_successful_models = len(orchestration_result.successful_predictions)
        if n_successful_models < 2:
            logger.info(f"[{correlation_id}] PASS: Insufficient model agreement - only {n_successful_models} models")
            return True

        # Calculate model agreement if available
        model_agreement = getattr(confidence_assessment.components, 'model_agreement', 0.5)
        if model_agreement < 0.3:  # Low agreement threshold
            logger.info(f"[{correlation_id}] PASS: Poor model agreement - {model_agreement:.3f}")
            return True

        # 4. Check overall confidence
        overall_confidence = confidence_assessment.overall_confidence
        if overall_confidence < 0.4:  # Low confidence threshold
            logger.info(f"[{correlation_id}] PASS: Low overall confidence - {overall_confidence:.3f}")
            return True

        # 5. Check data quality component
        data_quality = getattr(confidence_assessment.components, 'data_quality', 0.5)
        if data_quality < 0.3:  # Low data quality threshold
            logger.info(f"[{correlation_id}] PASS: Poor data quality - {data_quality:.3f}")
            return True

        logger.info(f"[{correlation_id}] RELIABILITY CHECK PASSED - proceeding with prediction")
        return False

    def generate_full_prediction(
        self,
        match: Match,
        stage: PredictionStage = PredictionStage.KICKOFF,
        odds_data: Optional[Dict[str, float]] = None,
        correlation_id: Optional[str] = None
    ) -> AnalysisContext:
        """Generate complete MENSIONE prediction using canonical pipeline.

        This method implements the canonical MENSIONE Intelligence Pipeline:
        1. Extract MatchFeatureSnapshot with data quality assessment
        2. Run ModelOrchestrator → execute all compatible models
        3. Ensemble → combine predictions with reliability weighting
        4. Calibration → calibrate ensemble probabilities
        5. Confidence → assess confidence from real pipeline values
        6. Market Derivation → derive all markets from score distribution
        7. TUTAR X Pick → generate recommended pick
        8. Versioning → create immutable prediction version
        9. AnalysisContext → populate context for AI Analyst

        Args:
            match: Match to predict
            stage: Prediction stage (default: KICKOFF)
            odds_data: Optional market odds for EV calculation
                Format: {"HOME": 2.1, "DRAW": 3.5, "AWAY": 3.8, "OVER_2_5": 1.85, ...}

        Returns:
            AnalysisContext with predicted_score, mensione_pick, confidence, and version_id
        """
        import time
        import logging
        from app.prediction.profiler import get_profiler, reset_profiler

        logger = logging.getLogger(__name__)

        if correlation_id is None:
            correlation_id = "none"

        # Reset and start profiling
        reset_profiler()
        profiler = get_profiler()
        profiler.start_stage("TOTAL_PIPELINE", match_id=match.id)

        start_time = datetime.now()
        stage_timings = {}
        pipeline_start = time.time()

        logger.info(f"[{correlation_id}] generate_full_prediction: Starting pipeline")

        # STEP 1: Extract canonical feature snapshot
        profiler.start_stage("FEATURE_EXTRACTION", match_id=match.id)
        step_start = time.time()
        logger.info(f"[{correlation_id}] Step 1: Extracting feature snapshot")
        try:
            snapshot = self._extract_canonical_snapshot(match, correlation_id)
            stage_timings["1_feature_snapshot"] = (time.time() - step_start) * 1000
            logger.info(f"[{correlation_id}] Step 1 complete: {stage_timings['1_feature_snapshot']:.1f}ms")
            profiler.end_stage(success=True, duration_ms=stage_timings["1_feature_snapshot"])
        except Exception as e:
            # Feature extraction failed - return empty context
            stage_timings["1_feature_snapshot_FAILED"] = (time.time() - step_start) * 1000
            logger.error(f"[{correlation_id}] Feature snapshot extraction failed: {e}", exc_info=True)
            logger.info(f"[{correlation_id}] Pipeline stage timings: {stage_timings}")
            profiler.end_stage(success=False, error=str(e), duration_ms=stage_timings["1_feature_snapshot_FAILED"])
            profiler.end_stage()  # End total pipeline
            return self.build_analysis_context(match=match, correlation_id=correlation_id)

        # STEP 2: Run model orchestrator
        profiler.start_stage("MODEL_ORCHESTRATOR", match_id=match.id)
        step_start = time.time()
        logger.info(f"[{correlation_id}] Step 2: Running model orchestrator")
        try:
            orchestration_result = self.model_orchestrator.run_all(snapshot)
            stage_timings["2_model_orchestrator"] = (time.time() - step_start) * 1000
            logger.info(f"[{correlation_id}] Step 2 complete: {stage_timings['2_model_orchestrator']:.1f}ms")
            profiler.end_stage(success=True, models_count=len(orchestration_result.successful_predictions), duration_ms=stage_timings["2_model_orchestrator"])
        except Exception as e:
            stage_timings["2_model_orchestrator_FAILED"] = (time.time() - step_start) * 1000
            logger.error(f"[{correlation_id}] Model orchestration failed: {e}", exc_info=True)
            logger.info(f"[{correlation_id}] Pipeline stage timings: {stage_timings}")
            profiler.end_stage(success=False, error=str(e), duration_ms=stage_timings["2_model_orchestrator_FAILED"])
            profiler.end_stage()  # End total pipeline
            return self.build_analysis_context(match=match, correlation_id=correlation_id)

        # Check if any models succeeded
        if not orchestration_result.successful_predictions:
            # No models succeeded - return context without prediction
            logger.info(f"[{correlation_id}] No models succeeded")
            logger.info(f"[{correlation_id}] Pipeline stage timings: {stage_timings}")
            profiler.end_stage()  # End total pipeline
            return self.build_analysis_context(match=match, correlation_id=correlation_id)

        # STEP 3: Ensemble - combine predictions
        profiler.start_stage("ENSEMBLE", match_id=match.id)
        step_start = time.time()
        try:
            ensemble_result = self.ensemble_integration.combine_predictions(
                orchestration_result=orchestration_result,
                context=None
            )
            stage_timings["3_ensemble"] = (time.time() - step_start) * 1000
            profiler.end_stage(success=True, duration_ms=stage_timings["3_ensemble"])

            # Check if ensemble returned a prediction
            if not isinstance(ensemble_result, ModelPrediction):
                # Ensemble unavailable - check if we have any successful model predictions
                if len(orchestration_result.successful_predictions) > 0:
                    # Use first successful model as fallback
                    ensemble_result = orchestration_result.successful_predictions[0].prediction
                else:
                    # No models available - return unavailable result
                    logger.info(f"[{correlation_id}] No models available for prediction - insufficient data")
                    profiler.end_stage(success=False, error="No models available", duration_ms=stage_timings["3_ensemble"])
                    profiler.end_stage()  # End total pipeline
                    return self.build_analysis_context(match=match, correlation_id=correlation_id)
        except Exception as e:
            import logging
            logging.error(f"Ensemble failed: {e}", exc_info=True)
            stage_timings["3_ensemble_FAILED"] = (time.time() - step_start) * 1000
            profiler.end_stage(success=False, error=str(e), duration_ms=stage_timings["3_ensemble_FAILED"])
            # Fallback to first successful model
            if len(orchestration_result.successful_predictions) > 0:
                ensemble_result = orchestration_result.successful_predictions[0].prediction
            else:
                # No models available - return unavailable result
                logger.info(f"[{correlation_id}] No models available for prediction - insufficient data")
                profiler.end_stage(success=False, error="No models available", duration_ms=stage_timings["3_ensemble_FAILED"])
                profiler.end_stage()  # End total pipeline
                return self.build_analysis_context(match=match, correlation_id=correlation_id)

        # STEP 4: Calibration - calibrate ensemble probabilities
        profiler.start_stage("CALIBRATION", match_id=match.id)
        step_start = time.time()
        try:
            calibrated_prediction = self.calibration_integration.calibrate_prediction(
                prediction=ensemble_result
            )
            stage_timings["4_calibration"] = (time.time() - step_start) * 1000
            profiler.end_stage(success=True, duration_ms=stage_timings["4_calibration"])
            calibration_metadata = calibrated_prediction.metadata
        except Exception as e:
            import logging
            logging.error(f"Calibration failed: {e}", exc_info=True)
            stage_timings["4_calibration_FAILED"] = (time.time() - step_start) * 1000
            profiler.end_stage(success=False, error=str(e), duration_ms=stage_timings["4_calibration_FAILED"])
            # Fallback to uncalibrated
            calibrated_prediction = ensemble_result
            calibration_metadata = {"calibration_status": "failed"}

        # STEP 5: Confidence - assess from real pipeline values
        profiler.start_stage("CONFIDENCE", match_id=match.id)
        step_start = time.time()
        try:
            confidence_assessment = self.confidence_integration.assess_confidence(
                snapshot=snapshot,
                orchestration_result=orchestration_result,
                ensemble_prediction=ensemble_result,
                calibration_metadata=calibration_metadata
            )
            stage_timings["5_confidence"] = (time.time() - step_start) * 1000
            profiler.end_stage(success=True, duration_ms=stage_timings["5_confidence"])

            # PHASE 6: Enhanced reliability and uncertainty checks
            # Check for withdrawal conditions based on data quality and model agreement
            should_pass = self._evaluate_withdrawal_conditions(
                snapshot=snapshot,
                orchestration_result=orchestration_result,
                confidence_assessment=confidence_assessment,
                calibration_metadata=calibration_metadata,
                correlation_id=correlation_id
            )

            if should_pass:
                logger.info(f"[{correlation_id}] PASS decision triggered - insufficient reliability")
                profiler.end_stage()  # End total pipeline
                return self.build_analysis_context(
                    match=match,
                    correlation_id=correlation_id,
                    pass_reason="insufficient_reliability"
                )

        except Exception as e:
            import logging
            logging.error(f"Confidence assessment failed: {e}", exc_info=True)
            stage_timings["5_confidence_FAILED"] = (time.time() - step_start) * 1000
            profiler.end_stage(success=False, error=str(e), duration_ms=stage_timings["5_confidence_FAILED"])
            # Fallback to default confidence
            from app.prediction.confidence_engine import ConfidenceComponents, ConfidenceWeights
            confidence_assessment = ConfidenceAssessment(
                overall_confidence=0.0,
                confidence_label="INSUFFICIENT_DATA",
                components=ConfidenceComponents(
                    model_agreement=0.0,
                    data_quality=0.0,
                    sample_size_score=0.0,
                    calibration_reliability=0.0,
                    lineup_certainty=0.0,
                    feature_stability=0.0,
                ),
                weights=ConfidenceWeights(),
                component_breakdown={}
            )

        # STEP 6: Convert score distribution to tuple format for MarketDerivationEngine
        profiler.start_stage("MARKET_CONVERSION", match_id=match.id)
        step_start = time.time()
        score_dist_tuples = {}
        if calibrated_prediction.score_distribution:
            for score_key, prob in calibrated_prediction.score_distribution.items():
                try:
                    # score_key might be tuple or string
                    if isinstance(score_key, tuple):
                        score_dist_tuples[score_key] = prob
                    else:
                        h, a = str(score_key).split('-')
                        score_dist_tuples[(int(h), int(a))] = prob
                except (ValueError, AttributeError):
                    continue
        stage_timings["6_market_conversion"] = (time.time() - step_start) * 1000
        profiler.end_stage(success=True, score_count=len(score_dist_tuples), duration_ms=stage_timings["6_market_conversion"])

        # STEP 7: Derive all markets
        profiler.start_stage("MARKET_DERIVATION", match_id=match.id)
        step_start = time.time()
        market_probs = None
        if score_dist_tuples:
            try:
                market_probs = self.market_derivation_engine.derive(score_dist_tuples)
                stage_timings["7_market_derivation"] = (time.time() - step_start) * 1000
                profiler.end_stage(success=True, markets_count=8, duration_ms=stage_timings["7_market_derivation"])  # Approximate market count
            except Exception as e:
                import logging
                logging.error(f"Market derivation failed: {e}", exc_info=True)
                stage_timings["7_market_derivation_FAILED"] = (time.time() - step_start) * 1000
                profiler.end_stage(success=False, error=str(e), duration_ms=stage_timings["7_market_derivation_FAILED"])
        else:
            stage_timings["7_market_derivation_SKIPPED"] = (time.time() - step_start) * 1000
            profiler.end_stage(success=False, error="No score distribution", duration_ms=stage_timings["7_market_derivation_SKIPPED"])

        # NEW: FEAT-003 - STEP 7.5: Predict shot markets if engine available
        profiler.start_stage("SHOT_MARKETS", match_id=match.id)
        step_start = time.time()
        shot_market_predictions = None
        if self.shot_market_engine and snapshot:
            try:
                # Get raw match data for distribution fitting
                # In real implementation, this would fetch historical matches with shot data
                # For now, pass None - shot engine will handle gracefully
                home_matches = None
                away_matches = None

                # Try to get raw match data from database if available
                if self.db_session:
                    try:
                        # Get matches with statistics for shot market prediction
                        from app.features.advanced_team_intelligence import AdvancedTeamIntelligenceCalculator
                        from app.database.models import Match, MatchStatistic, Team
                        from sqlalchemy import and_

                        # Get matches before prediction timestamp
                        before_datetime = match.scheduled_at if hasattr(match, 'scheduled_at') else datetime.now()

                        # Fetch historical matches with statistics for both teams
                        def get_matches_with_stats(team_id: str, limit: int = 20):
                            matches_query = (
                                self.db_session.query(Match)
                                .filter(
                                    and_(
                                        (Match.home_team_id == team_id) | (Match.away_team_id == team_id),
                                        Match.scheduled_at < before_datetime,
                                        Match.status == 'FINISHED'
                                    )
                                )
                                .order_by(Match.scheduled_at.desc())
                                .limit(limit)
                            )

                            matches_with_stats = []
                            for m in matches_query:
                                # Get match statistics for this match
                                home_stats = self.db_session.query(MatchStatistic).filter_by(
                                    match_id=m.id, team_id=m.home_team_id
                                ).first()
                                away_stats = self.db_session.query(MatchStatistic).filter_by(
                                    match_id=m.id, team_id=m.away_team_id
                                ).first()

                                if home_stats and away_stats:
                                    from app.features.advanced_team_intelligence import MatchWithStatistics
                                    matches_with_stats.append(MatchWithStatistics(
                                        match=m,
                                        home_statistics=home_stats,
                                        away_statistics=away_stats
                                    ))

                            return matches_with_stats

                        home_matches = get_matches_with_stats(snapshot.home_team_id)
                        away_matches = get_matches_with_stats(snapshot.away_team_id)

                    except Exception as match_fetch_error:
                        import logging
                        logging.debug(f"Could not fetch match data for shot markets: {match_fetch_error}")
                        home_matches = None
                        away_matches = None

                # Predict shot markets
                shot_market_predictions = self.shot_market_engine.predict_all_shot_markets(
                    snapshot=snapshot,
                    home_matches=home_matches,
                    away_matches=away_matches,
                    before_datetime=match.scheduled_at if hasattr(match, 'scheduled_at') else None
                )
                stage_timings["7.5_shot_markets"] = (time.time() - step_start) * 1000
                profiler.end_stage(success=True, shot_markets_count=len(shot_market_predictions) if shot_market_predictions else 0, duration_ms=stage_timings["7.5_shot_markets"])
            except Exception as e:
                import logging
                logging.error(f"Shot market prediction failed: {e}", exc_info=True)
                stage_timings["7.5_shot_markets_FAILED"] = (time.time() - step_start) * 1000
                profiler.end_stage(success=False, error=str(e), duration_ms=stage_timings["7.5_shot_markets_FAILED"])
        else:
            stage_timings["7.5_shot_markets_UNAVAILABLE"] = (time.time() - step_start) * 1000
            profiler.end_stage(success=False, error="Shot engine unavailable", duration_ms=stage_timings["7.5_shot_markets_UNAVAILABLE"])

        # STEP 8: Generate TUTAR X PICK using SmartMarketSelector
        profiler.start_stage("MARKET_SELECTOR", match_id=match.id)
        step_start = time.time()
        mensione_pick = None
        pipeline_version = "1.0.0"
        if market_probs:
            try:
                from app.prediction.market_selector import BestTip, PassDecision

                # Extract team names for readable shot market labels
                home_team_name = None
                away_team_name = None
                if hasattr(match, 'home_team') and match.home_team:
                    home_team_name = match.home_team.name
                if hasattr(match, 'away_team') and match.away_team:
                    away_team_name = match.away_team.name

                # NEW: FEAT-003 - Pass shot market predictions to selector
                mensione_result = self.market_selector.evaluate_and_select(
                    market_probs=market_probs,
                    confidence_assessment=confidence_assessment,
                    odds_data=odds_data,
                    pipeline_version=pipeline_version,
                    shot_market_predictions=shot_market_predictions,  # NEW: FEAT-003
                    home_team_name=home_team_name,  # NEW: FEAT-003
                    away_team_name=away_team_name,   # NEW: FEAT-003
                    match_id=match.id  # NEW: Pass actual match ID
                )

                # Convert BestTip or PassDecision to dict for AnalysisContext
                if isinstance(mensione_result, BestTip):
                    mensione_pick = {
                        "match_id": mensione_result.match_id,
                        "market": mensione_result.market,
                        "selection": mensione_result.selection,
                        "probability": mensione_result.probability,
                        "confidence": mensione_result.confidence,
                        "model_agreement": mensione_result.model_agreement,
                        "data_quality": mensione_result.data_quality,
                        "edge": mensione_result.edge,
                        "fair_odds": mensione_result.fair_odds,
                        "bookmaker_odds": mensione_result.bookmaker_odds,
                        "odds_movement": mensione_result.odds_movement,
                        "value_classification": mensione_result.value_classification,
                        "risk_level": mensione_result.risk_level,
                        "selection_score": mensione_result.selection_score,
                        "selector_reason": mensione_result.selector_reason,
                        "timestamp": mensione_result.timestamp.isoformat(),
                        "pipeline_version": mensione_result.pipeline_version,
                        "pass_decision": False
                    }
                elif isinstance(mensione_result, PassDecision):
                    mensione_pick = {
                        "pass_decision": True,
                        "match_id": mensione_result.match_id,
                        "pass_reason": mensione_result.pass_reason,
                        "evaluated_markets_count": mensione_result.evaluated_markets_count,
                        "best_market_details": mensione_result.best_market_details,
                        "timestamp": mensione_result.timestamp.isoformat(),
                        "pipeline_version": mensione_result.pipeline_version
                    }
                stage_timings["8_market_selector"] = (time.time() - step_start) * 1000
                profiler.end_stage(success=True, pick_made=mensione_pick is not None, duration_ms=stage_timings["8_market_selector"])
            except Exception as e:
                import logging
                logging.error(f"SmartMarketSelector failed: {e}", exc_info=True)
                stage_timings["8_market_selector_FAILED"] = (time.time() - step_start) * 1000
                profiler.end_stage(success=False, error=str(e), duration_ms=stage_timings["8_market_selector_FAILED"])
        else:
            stage_timings["8_market_selector_SKIPPED"] = (time.time() - step_start) * 1000
            profiler.end_stage(success=False, error="No market probabilities", duration_ms=stage_timings["8_market_selector_SKIPPED"])

        # STEP 9: Extract predicted score (most likely scoreline)
        profiler.start_stage("PREDICTED_SCORE", match_id=match.id)
        step_start = time.time()
        predicted_score = None
        if market_probs and market_probs.exact_score_top:
            predicted_score = market_probs.exact_score_top[0][0]
        elif calibrated_prediction.score_distribution:
            # Fallback: find max probability scoreline
            max_score = max(calibrated_prediction.score_distribution.items(), key=lambda x: x[1], default=None)
            if max_score:
                score_key = max_score[0]
                if isinstance(score_key, tuple):
                    predicted_score = f"{score_key[0]}-{score_key[1]}"
                else:
                    predicted_score = str(score_key)
        stage_timings["9_predicted_score"] = (time.time() - step_start) * 1000
        profiler.end_stage(success=predicted_score is not None, score=predicted_score, duration_ms=stage_timings["9_predicted_score"])

        # STEP 10: Collect model metadata for versioning
        profiler.start_stage("VERSION_METADATA", match_id=match.id)
        step_start = time.time()
        models_used = {}
        for model_output in orchestration_result.successful_predictions:
            models_used[model_output.model_id] = model_output.model_version
        stage_timings["10_version_metadata"] = (time.time() - step_start) * 1000
        profiler.end_stage(success=True, models_count=len(models_used), duration_ms=stage_timings["10_version_metadata"])

        # STEP 11: Create versioned prediction with full pipeline metadata
        profiler.start_stage("PREDICTION_VERSIONING", match_id=match.id)
        step_start = time.time()

        # Serialize score_distribution: convert tuple keys to "h-a" string format for JSON compatibility
        serialized_score_dist = None
        if calibrated_prediction.score_distribution:
            serialized_score_dist = {}
            for score_key, prob in calibrated_prediction.score_distribution.items():
                if isinstance(score_key, tuple) and len(score_key) == 2:
                    # Format: (home_goals, away_goals) → "home_goals-away_goals"
                    key_str = f"{score_key[0]}-{score_key[1]}"
                    serialized_score_dist[key_str] = prob
                elif isinstance(score_key, str):
                    # Already string format
                    serialized_score_dist[score_key] = prob

        # Serialize markets: convert nested structures to JSON-safe format
        serialized_markets = None
        if market_probs:
            serialized_markets = {}
            for attr, value in market_probs.__dict__.items():
                if value is None:
                    serialized_markets[attr] = None
                elif isinstance(value, (int, float, str, bool)):
                    serialized_markets[attr] = value
                elif isinstance(value, dict):
                    # Convert any enum/complex keys to strings
                    serialized_markets[attr] = {str(k): v for k, v in value.items()}
                else:
                    # Other types: attempt str() conversion
                    serialized_markets[attr] = str(value)

        prediction_data = {
            "home_win_prob": calibrated_prediction.home_win_prob,
            "draw_prob": calibrated_prediction.draw_prob,
            "away_win_prob": calibrated_prediction.away_win_prob,
            "home_xg": calibrated_prediction.home_score_mean,
            "away_xg": calibrated_prediction.away_score_mean,
            "predicted_score": predicted_score,
            "btts_probability": self._calculate_btts_from_distribution(calibrated_prediction.score_distribution),
            "score_distribution": serialized_score_dist,
            "markets": serialized_markets,
            "shot_markets": self._serialize_shot_markets(shot_market_predictions) if shot_market_predictions else None,  # NEW: FEAT-003
            "mensione_pick": mensione_pick,
            "confidence": {
                "overall": confidence_assessment.overall_confidence,
                "label": confidence_assessment.confidence_label,
                "components": confidence_assessment.components.__dict__,
                "weights": confidence_assessment.weights.__dict__,
                "component_breakdown": confidence_assessment.component_breakdown
            },
            "orchestration": {
                "models_run": len(orchestration_result.successful_predictions),
                "models_unavailable": len(orchestration_result.unavailable_models),
                "models_failed": len(orchestration_result.failed_models)
            }
        }

        version = None
        try:
            version = self.version_manager.create_version(
                match_id=match.id,
                stage=stage,
                prediction_data=prediction_data,
                model_versions=models_used,
                data_quality_score=snapshot.data_quality_report.overall_score if snapshot.data_quality_report else None,
                confidence_score=confidence_assessment.overall_confidence,
                notes=[
                    f"Canonical Pipeline v1.0: {len(models_used)} models, "
                    f"ensemble agreement={ensemble_result.metadata.get('model_agreement', 0.0):.3f}, "
                    f"calibration={calibration_metadata.get('calibration_status', 'unknown')}"
                ],
                mensione_pick=mensione_pick
            )
            stage_timings["11_prediction_versioning"] = (time.time() - step_start) * 1000
            profiler.end_stage(success=True, version_id=version.version_id if version else None, duration_ms=stage_timings["11_prediction_versioning"])
        except Exception as e:
            import logging
            logging.error(f"Prediction versioning failed: {e}", exc_info=True)
            stage_timings["11_prediction_versioning_FAILED"] = (time.time() - step_start) * 1000
            profiler.end_stage(success=False, error=str(e), duration_ms=stage_timings["11_prediction_versioning_FAILED"])

        # STEP 12: Build legacy Prediction object for backward compatibility
        profiler.start_stage("LEGACY_PREDICTION", match_id=match.id)
        step_start = time.time()
        # Convert score distribution from tuple keys to string keys for legacy Prediction
        legacy_score_distribution = {}
        if calibrated_prediction.score_distribution:
            for score_key, prob in calibrated_prediction.score_distribution.items():
                if isinstance(score_key, tuple):
                    legacy_score_distribution[f"{score_key[0]}-{score_key[1]}"] = prob
                else:
                    legacy_score_distribution[str(score_key)] = prob

        legacy_prediction = Prediction(
            id=str(uuid.uuid4()),
            match_id=match.id,
            home_win_probability=calibrated_prediction.home_win_prob,
            draw_probability=calibrated_prediction.draw_prob,
            away_win_probability=calibrated_prediction.away_win_prob,
            home_xg=calibrated_prediction.home_score_mean,
            away_xg=calibrated_prediction.away_score_mean,
            predicted_home_score=None,  # Set from predicted_score
            predicted_away_score=None,
            btts_probability=market_probs.btts_yes if market_probs else 0.0,  # Derive from market derivation
            score_distribution=legacy_score_distribution,
            over_under_probabilities={},
            asian_handicap_probabilities={},
            model_id=ensemble_result.model_id,
            model_version="ensemble_v1",
            model_type=ModelType.POISSON,  # Legacy field
            confidence_score=confidence_assessment.overall_confidence,
            created_at=datetime.now(),
            generated_at=datetime.now(),  # Required field
            statistical_features=snapshot.get_feature_dict(),
        )

        # Parse predicted_score into home/away
        if predicted_score:
            try:
                h, a = predicted_score.split('-')
                legacy_prediction.predicted_home_score = int(h)
                legacy_prediction.predicted_away_score = int(a)
            except (ValueError, AttributeError):
                pass

        stage_timings["12_legacy_prediction"] = (time.time() - step_start) * 1000
        profiler.end_stage(success=True, duration_ms=stage_timings["12_legacy_prediction"])

        # STEP 13: Generate markets for AnalysisContext (reuse market_probs)
        profiler.start_stage("ANALYSIS_MARKETS", match_id=match.id)
        step_start = time.time()
        markets = None
        if market_probs:
            markets = self._convert_market_probs_to_prediction_markets(match, market_probs)
        stage_timings["13_analysis_markets"] = (time.time() - step_start) * 1000
        profiler.end_stage(success=markets is not None, markets_count=len(markets) if markets else 0, duration_ms=stage_timings["13_analysis_markets"])

        # STEP 14: Build enriched AnalysisContext
        profiler.start_stage("ANALYSIS_CONTEXT", match_id=match.id)
        step_start = time.time()
        context = self.build_analysis_context(
            match=match,
            prediction=legacy_prediction,
            prediction_markets=markets,
            correlation_id=correlation_id
        )

        # Add MENSIONE-specific fields
        context.predicted_score = predicted_score
        context.mensione_pick = mensione_pick
        context.prediction_version_id = version.version_id if version else None
        # confidence_assessment is embedded in confidence dict in prediction_version_data

        # Add form data from snapshot to context (for API response)
        if snapshot.home_form:
            context.home_form = snapshot.home_form
        if snapshot.away_form:
            context.away_form = snapshot.away_form

        # Add shot markets to context (FEAT-003)
        if shot_market_predictions:
            serialized_shot_markets = self._serialize_shot_markets(shot_market_predictions)
            context.shot_markets = serialized_shot_markets

        stage_timings["14_analysis_context"] = (time.time() - step_start) * 1000
        profiler.end_stage(success=True, duration_ms=stage_timings["14_analysis_context"])

        # Calculate execution time and finish profiling
        execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000
        total_pipeline_time = (time.time() - pipeline_start) * 1000

        # Log final timing summary
        logger.info(f"[{correlation_id}] PIPELINE COMPLETE: {total_pipeline_time:.1f}ms")
        logger.info(f"[{correlation_id}] Stage timings: {stage_timings}")

        # End total pipeline profiling
        profiler.end_stage(success=True, total_stages=len(stage_timings), duration_ms=total_pipeline_time)

        return context

    def _extract_canonical_snapshot(self, match: Match, correlation_id: Optional[str] = None) -> MatchFeatureSnapshot:
        """Extract canonical feature snapshot with data quality assessment.

        Args:
            match: Match to extract features for

        Returns:
            MatchFeatureSnapshot with data quality report
        """
        import time
        import logging
        logger = logging.getLogger(__name__)
        substep_start = time.time()

        # Extract features using existing extractor
        features = self.feature_extractor.extract_features(match)

        logger.info(f"  [snapshot] extract_features: {(time.time() - substep_start) * 1000:.2f}ms")

        # DEVELOPMENT FALLBACK: Provide baseline values for missing features
        # This preserves determinism while allowing prediction generation
        substep_start = time.time()
        # PRODUCTION SAFETY: Only allow baseline fallback if explicitly configured
        if self.config.allow_dev_baseline_fallback:
            # Development mode: provide baseline strength values if missing
            if features.get("home_attack_strength") is None:
                features["home_attack_strength"] = 1.0
            if features.get("away_attack_strength") is None:
                features["away_attack_strength"] = 1.0
            if features.get("home_defense_strength") is None:
                features["home_defense_strength"] = 1.0
            if features.get("away_defense_strength") is None:
                features["away_defense_strength"] = 1.0
        logger.info(f"  [snapshot] dev_fallback: {(time.time() - substep_start) * 1000:.2f}ms")

        # Run data quality assessment using DataQualityGate
        substep_start = time.time()
        data_quality_report = self.data_quality_gate.assess(features)
        logger.info(f"  [snapshot] data_quality_gate: {(time.time() - substep_start) * 1000:.2f}ms")

        # Extract feature_set if feature_aggregator available
        substep_start = time.time()
        feature_set = None
        if self.feature_aggregator:
            try:
                feature_set = self.feature_aggregator.extract_features_for_match(
                    match_id=match.id
                )
            except Exception as e:
                # Feature aggregation failed, continue with basic features
                import logging
                logging.error(f"[FEATURE_AGGREGATOR_EXCEPTION] {type(e).__name__}: {str(e)}", exc_info=True)
                pass
        logger.info(f"  [snapshot] feature_aggregator: {(time.time() - substep_start) * 1000:.2f}ms")

        # Build snapshot
        snapshot = extract_feature_snapshot(
            match_id=match.id,
            home_team_id=match.home_team_id,
            away_team_id=match.away_team_id,
            feature_set=feature_set,
            data_quality_report=data_quality_report,
            home_team_name=match.home_team.name if hasattr(match, 'home_team') and match.home_team else None,
            away_team_name=match.away_team.name if hasattr(match, 'away_team') and match.away_team else None,
            scheduled_at=match.scheduled_at if hasattr(match, 'scheduled_at') else None,
            market_info=None  # TODO: extract from odds_data if available
        )
        snapshot.home_lambda_rating = features.get("home_lambda_rating")
        snapshot.away_lambda_rating = features.get("away_lambda_rating")

        # Add H2H features if available (will be populated later when analysis_context is built)
        # This is a placeholder for future H2H integration

        # COMPATIBILITY: If snapshot has no strength metrics (feature_set was None),
        # populate from the flat features dict to ensure models can run
        needs_home_strength = (snapshot.home_strength is None or
                              snapshot.home_strength.goals_scored_per_match is None)
        needs_away_strength = (snapshot.away_strength is None or
                              snapshot.away_strength.goals_scored_per_match is None)

        if needs_home_strength or needs_away_strength:
            from app.prediction.feature_snapshot import TeamStrengthMetrics, FormMetrics

            # Populate home strength from features
            if needs_home_strength:
                home_goals_scored = features.get("home_recent_avg_goals_scored") or features.get("home_goals_scored_avg") or features.get("home_goal_scoring_rate")
                home_goals_conceded = features.get("home_recent_avg_goals_conceded") or features.get("home_goals_conceded_avg") or features.get("home_goal_conceding_rate")

                snapshot.home_strength = TeamStrengthMetrics(
                    goals_scored_per_match=home_goals_scored,
                    xg_per_match=features.get("home_expected_goals"),  # Monte Carlo için
                    goals_conceded_per_match=home_goals_conceded,
                    xg_against_per_match=features.get("home_xg_conceded_avg"),
                    points_per_match=features.get("home_form_points_per_match") or features.get("home_points_per_match"),
                    elo_rating=features.get("elo_home"),  # Doğru anahtar
                    attack_strength=features.get("home_attack_strength"),
                    defense_strength=features.get("home_defense_strength"),
                )

            # Populate away strength from features
            if needs_away_strength:
                away_goals_scored = features.get("away_recent_avg_goals_scored") or features.get("away_goals_scored_avg") or features.get("away_goal_scoring_rate")
                away_goals_conceded = features.get("away_recent_avg_goals_conceded") or features.get("away_goals_conceded_avg") or features.get("away_goal_conceding_rate")

                snapshot.away_strength = TeamStrengthMetrics(
                    goals_scored_per_match=away_goals_scored,
                    xg_per_match=features.get("away_expected_goals"),  # Monte Carlo için
                    goals_conceded_per_match=away_goals_conceded,
                    xg_against_per_match=features.get("away_xg_conceded_avg"),
                    points_per_match=features.get("away_form_points_per_match") or features.get("away_points_per_match"),
                    elo_rating=features.get("elo_away"),  # Doğru anahtar
                    attack_strength=features.get("away_attack_strength"),
                    defense_strength=features.get("away_defense_strength"),
                )

            # Populate form metrics if missing
            if snapshot.home_form is None:
                snapshot.home_form = FormMetrics(
                    wins=int(features.get("home_recent_wins", 0)) if features.get("home_recent_wins") is not None else None,
                    draws=int(features.get("home_recent_draws", 0)) if features.get("home_recent_draws") is not None else None,
                    losses=int(features.get("home_recent_losses", 0)) if features.get("home_recent_losses") is not None else None,
                    points=int(features.get("home_recent_points", 0)) if features.get("home_recent_points") is not None else None,
                    goals_for=int(features.get("home_recent_goals_scored", 0)) if features.get("home_recent_goals_scored") is not None else None,
                    goals_against=int(features.get("home_recent_goals_conceded", 0)) if features.get("home_recent_goals_conceded") is not None else None,
                    goal_difference=None,  # Calculate if needed
                    points_per_match=features.get("home_form_points_per_match") or features.get("home_form_score"),
                    win_rate=features.get("home_win_rate"),
                    clean_sheet_rate=features.get("home_clean_sheet_rate"),
                    matches_analyzed=int(features.get("home_match_count", 5)) if features.get("home_match_count") is not None else 5,
                )

            if snapshot.away_form is None:
                snapshot.away_form = FormMetrics(
                    wins=int(features.get("away_recent_wins", 0)) if features.get("away_recent_wins") is not None else None,
                    draws=int(features.get("away_recent_draws", 0)) if features.get("away_recent_draws") is not None else None,
                    losses=int(features.get("away_recent_losses", 0)) if features.get("away_recent_losses") is not None else None,
                    points=int(features.get("away_recent_points", 0)) if features.get("away_recent_points") is not None else None,
                    goals_for=int(features.get("away_recent_goals_scored", 0)) if features.get("away_recent_goals_scored") is not None else None,
                    goals_against=int(features.get("away_recent_goals_conceded", 0)) if features.get("away_recent_goals_conceded") is not None else None,
                    goal_difference=None,  # Calculate if needed
                    points_per_match=features.get("away_form_points_per_match") or features.get("away_form_score"),
                    win_rate=features.get("away_win_rate"),
                    clean_sheet_rate=features.get("away_clean_sheet_rate"),
                    matches_analyzed=int(features.get("away_match_count", 5)) if features.get("away_match_count") is not None else 5,
                )

        # Get features from snapshot for model input
        snapshot_features = snapshot.get_feature_dict()

        # FEAT-003: Populate shot intelligence if database session is available
        if self.db_session:
            try:
                from app.features.advanced_feature_engineering import AdvancedFeatureEngineer
                from app.features.advanced_team_intelligence import MatchWithStatistics
                from app.database.models import Match, MatchStatistic
                from sqlalchemy import and_

                # Get all matches with statistics for shot intelligence
                before_datetime = snapshot.scheduled_at

                def get_all_matches_with_stats(limit: int = 100):
                    """Get all recent matches with statistics for shot intelligence calculation."""
                    matches_query = (
                        self.db_session.query(Match)
                        .filter(
                            and_(
                                Match.scheduled_at < before_datetime,
                                Match.status == 'FINISHED'
                            )
                        )
                        .order_by(Match.scheduled_at.desc())
                        .limit(limit)
                    )

                    matches_with_stats = []
                    for m in matches_query:
                        home_stats = self.db_session.query(MatchStatistic).filter_by(
                            match_id=m.id, team_id=m.home_team_id
                        ).first()
                        away_stats = self.db_session.query(MatchStatistic).filter_by(
                            match_id=m.id, team_id=m.away_team_id
                        ).first()

                        if home_stats and away_stats:
                            matches_with_stats.append(MatchWithStatistics(
                                match=m,
                                home_statistics=home_stats,
                                away_statistics=away_stats
                            ))

                    return matches_with_stats

                # Get historical matches
                all_matches = get_all_matches_with_stats()

                advanced_engineer = AdvancedFeatureEngineer()
                advanced_engineer.populate_shot_intelligence(
                    snapshot=snapshot,
                    home_team_id=snapshot.home_team_id,
                    away_team_id=snapshot.away_team_id,
                    matches_with_stats=all_matches,
                    before_datetime=before_datetime
                )
            except Exception as e:
                import logging
                logging.warning(f"Shot intelligence population failed: {e}")

        return snapshot

    def _convert_market_probs_to_prediction_markets(
        self,
        match: Match,
        market_probs: Any
    ) -> List[PredictionMarket]:
        """Convert MarketProbabilities to list of PredictionMarket objects.

        Args:
            match: Match object
            market_probs: MarketProbabilities from MarketDerivationEngine

        Returns:
            List of PredictionMarket objects for backward compatibility
        """
        markets = []

        # 1X2 Market (MATCH_RESULT)
        if hasattr(market_probs, 'home_win') and hasattr(market_probs, 'draw') and hasattr(market_probs, 'away_win'):
            # Validate probabilities
            if all(0.0 <= p <= 1.0 for p in [market_probs.home_win, market_probs.draw, market_probs.away_win]):
                markets.append(PredictionMarket(
                    id=str(uuid.uuid4()),
                    prediction_id="",  # Set by caller
                    market_type=PredictionMarketType.MATCH_RESULT,
                    probabilities={
                        "home": market_probs.home_win,
                        "draw": market_probs.draw,
                        "away": market_probs.away_win,
                    },
                    line=None,
                ))

        # Over/Under Markets
        if hasattr(market_probs, 'over_under') and market_probs.over_under:
            for line, (over_prob, under_prob) in market_probs.over_under.items():
                # Validate probabilities
                if 0.0 <= over_prob <= 1.0 and 0.0 <= under_prob <= 1.0:
                    markets.append(PredictionMarket(
                        id=str(uuid.uuid4()),
                        prediction_id="",
                        market_type=PredictionMarketType.OVER_UNDER,
                        line=line,
                        probabilities={
                            "over": over_prob,
                            "under": under_prob,
                        },
                    ))

        # BTTS Market
        if hasattr(market_probs, 'btts_yes') and hasattr(market_probs, 'btts_no'):
            # Validate probabilities
            if 0.0 <= market_probs.btts_yes <= 1.0 and 0.0 <= market_probs.btts_no <= 1.0:
                markets.append(PredictionMarket(
                    id=str(uuid.uuid4()),
                    prediction_id="",
                    market_type=PredictionMarketType.BTTS,
                    probabilities={
                        "yes": market_probs.btts_yes,
                        "no": market_probs.btts_no,
                    },
                    line=None,
                ))

        # Combined Market: Over 2.5 + BTTS Yes
        if hasattr(market_probs, 'over_2_5_and_btts_yes'):
            # Validate probability
            if 0.0 <= market_probs.over_2_5_and_btts_yes <= 1.0:
                markets.append(PredictionMarket(
                    id=str(uuid.uuid4()),
                    prediction_id="",
                    market_type=PredictionMarketType.OVER_2_5_AND_BTTS,
                    probabilities={
                        "yes": market_probs.over_2_5_and_btts_yes,
                        "no": 1.0 - market_probs.over_2_5_and_btts_yes,
                    },
                    line=2.5,  # Reference line for the "over" part
                ))

        # Exact Score Market (top 10 scorelines)
        if hasattr(market_probs, 'exact_score_top') and market_probs.exact_score_top:
            top_scores = {}
            for score_str, prob in market_probs.exact_score_top[:10]:
                if 0.0 <= prob <= 1.0:
                    top_scores[score_str] = prob

            if top_scores:
                markets.append(PredictionMarket(
                    id=str(uuid.uuid4()),
                    prediction_id="",
                    market_type=PredictionMarketType.CORRECT_SCORE,
                    probabilities=top_scores,
                    line=None,
                ))

        return markets

    def _calculate_btts_from_distribution(self, score_distribution: Dict[Tuple[int, int], float]) -> Optional[float]:
        """Calculate Both Teams To Score probability from score distribution.

        BTTS Yes = sum of probabilities where both home >= 1 and away >= 1.

        Args:
            score_distribution: Score distribution {(home, away): probability}

        Returns:
            BTTS probability [0, 1], or None if distribution is empty
        """
        if not score_distribution:
            return None

        btts_prob = sum(
            prob for (home_goals, away_goals), prob in score_distribution.items()
            if home_goals >= 1 and away_goals >= 1
        )

        return btts_prob

    def _serialize_shot_markets(
        self,
        shot_market_predictions: Dict
    ) -> Dict[str, Any]:
        """Serialize shot market predictions for storage in prediction_data.

        Args:
            shot_market_predictions: Dict[ShotMarketType, List[ShotMarketPrediction]]

        Returns:
            Serialized dict with shot market data
        """
        if not shot_market_predictions:
            return {}

        serialized = {}

        for market_type, predictions in shot_market_predictions.items():
            market_key = market_type.value if hasattr(market_type, 'value') else str(market_type)
            serialized[market_key] = []

            for prediction in predictions:
                pred_dict = {
                    "team_id": prediction.team_id,
                    "market_type": prediction.market_type.value if hasattr(prediction.market_type, 'value') else str(prediction.market_type),
                    "available": prediction.available,
                    "unavailability_reason": prediction.unavailability_reason,
                    "distribution_model": prediction.distribution_model.value if hasattr(prediction.distribution_model, 'value') else str(prediction.distribution_model),
                    "expected_value": prediction.expected_value,
                    "variance": prediction.variance,
                    "sample_size": prediction.sample_size,
                    "data_quality_score": prediction.data_quality_score,
                    "thresholds": []
                }

                for threshold in prediction.thresholds:
                    threshold_dict = {
                        "threshold": threshold.threshold,
                        "over_probability": threshold.over_probability,
                        "distribution_model": threshold.distribution_model.value if hasattr(threshold.distribution_model, 'value') else str(threshold.distribution_model),
                        "expected_value": threshold.expected_value,
                        "variance": threshold.variance,
                        "data_quality": threshold.data_quality
                    }
                    pred_dict["thresholds"].append(threshold_dict)

                serialized[market_key].append(pred_dict)

        return serialized
