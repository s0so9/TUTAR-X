"""Application-level model artifact cache.

OPTIMIZATION (Section 7): Load immutable model artifacts once per worker
instead of loading on every request. Thread-safe singleton pattern.
"""

import logging
import threading
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class ModelArtifactCache:
    """Thread-safe cache for immutable model artifacts.
    
    Models, calibrators, and other trained artifacts are loaded once
    and reused across requests within the same worker process.
    """
    
    def __init__(self):
        self._artifacts: Dict[str, Any] = {}
        self._lock = threading.Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached artifact.
        
        Args:
            key: Artifact identifier
            
        Returns:
            Cached artifact or None
        """
        with self._lock:
            return self._artifacts.get(key)
    
    def set(self, key: str, artifact: Any) -> None:
        """Cache an artifact.
        
        Args:
            key: Artifact identifier
            artifact: Artifact to cache (should be immutable)
        """
        with self._lock:
            self._artifacts[key] = artifact
            logger.info(f"Cached model artifact: {key}")
    
    def clear(self) -> None:
        """Clear all cached artifacts."""
        with self._lock:
            self._artifacts.clear()
            logger.info("Cleared model artifact cache")
    
    def size(self) -> int:
        """Get number of cached artifacts."""
        with self._lock:
            return len(self._artifacts)


# Global application-level cache
_model_artifact_cache: Optional[ModelArtifactCache] = None
_cache_lock = threading.Lock()


def get_model_artifact_cache() -> ModelArtifactCache:
    """Get or create application-level model artifact cache singleton."""
    global _model_artifact_cache
    
    with _cache_lock:
        if _model_artifact_cache is None:
            _model_artifact_cache = ModelArtifactCache()
            logger.info("✓ Initialized model artifact cache")
        return _model_artifact_cache


def load_calibrator_cached():
    """Load calibrator with application-level caching.
    
    Returns:
        Calibrator instance or None
    """
    cache = get_model_artifact_cache()
    
    # Check cache first
    CACHE_KEY = "calibrator_1x2_v1"
    calibrator = cache.get(CACHE_KEY)
    
    if calibrator is not None:
        logger.debug(f"Using cached calibrator: {CACHE_KEY}")
        return calibrator
    
    # Load from disk
    from app.prediction.calibration_loader import load_trained_calibrator
    
    calibrator = load_trained_calibrator()
    
    # Cache for future requests
    if calibrator is not None:
        cache.set(CACHE_KEY, calibrator)
    
    return calibrator


def create_calibration_integration_cached():
    """Create CalibrationIntegration with cached calibrator.
    
    OPTIMIZATION: Reuses loaded calibrator instead of loading from disk on every request.
    """
    from app.prediction.model_orchestrator import CalibrationIntegration
    
    calibrator = load_calibrator_cached()
    
    if calibrator is None:
        logger.warning("No trained calibrator available, using default untrained calibrator")
        return CalibrationIntegration.create_default()
    
    if not calibrator.is_fitted:
        logger.warning("Loaded calibrator is not fitted, predictions will be uncalibrated")
    
    return CalibrationIntegration(calibrator=calibrator)


def load_ensemble_cached():
    """Load ensemble engine with application-level caching.
    
    Returns:
        Optimized ensemble engine or default
    """
    cache = get_model_artifact_cache()
    
    # Check cache first
    CACHE_KEY = "ensemble_optimized_v1"
    ensemble = cache.get(CACHE_KEY)
    
    if ensemble is not None:
        logger.debug(f"Using cached ensemble: {CACHE_KEY}")
        return ensemble
    
    # Load/create ensemble
    from app.prediction.ensemble_optimizer import create_optimized_ensemble
    from app.prediction.model_orchestrator import EnsembleIntegration
    
    try:
        optimized_engine = create_optimized_ensemble()
        ensemble_integration = EnsembleIntegration(engine=optimized_engine)
        
        # Cache for future requests
        cache.set(CACHE_KEY, ensemble_integration)
        
        return ensemble_integration
    except Exception as e:
        logger.warning(f"Could not load optimized ensemble, using default: {e}")
        return EnsembleIntegration.create_default()
