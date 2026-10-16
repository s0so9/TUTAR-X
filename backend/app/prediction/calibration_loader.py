"""Load trained calibration models into production.

This module provides functions to load pre-trained calibration models
and integrate them into the prediction pipeline.
"""

import logging
from pathlib import Path
from typing import Optional
import pickle
import json

from app.prediction.model_orchestrator import Calibrator1X2
from app.prediction.model_paths import (
    get_calibration_config_path,
    get_calibration_model_path,
    get_trained_calibration_model_path
)

logger = logging.getLogger(__name__)


def load_calibration_config(config_path: Optional[str] = None) -> Optional[dict]:
    """Load calibration configuration.
    
    Args:
        config_path: Path to calibration config JSON file.
                    If None, uses default path in backend/config/
    
    Returns:
        Configuration dictionary or None if not found
    """
    if config_path is None:
        config_path = get_calibration_config_path()
    else:
        config_path = Path(config_path)
    
    if not config_path.exists():
        logger.warning(f"Calibration config not found at {config_path}")
        return None
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        logger.info(f"Loaded calibration config from {config_path}")
        return config
    except Exception as e:
        logger.error(f"Failed to load calibration config: {e}")
        return None


def load_trained_calibrator(calibrator_path: Optional[str] = None) -> Optional[Calibrator1X2]:
    """Load trained calibrator from pickle file.
    
    Args:
        calibrator_path: Path to calibrator pickle file.
                        If None, uses path from config
    
    Returns:
        Trained Calibrator1X2 instance or None if not found/invalid
    """
    if calibrator_path is None:
        # Production loading requires an explicit opt-in in the config. The
        # shipped calibrator was fitted on simulated predictions and is
        # degenerate, so nothing is loaded unless "enabled": true is set after
        # retraining on real out-of-sample predictions.
        config = load_calibration_config()
        if not config or config.get("enabled") is not True:
            logger.warning(
                "Trained calibrator disabled (calibration_config.json 'enabled' is not true); "
                "predictions stay uncalibrated"
            )
            return None
        if config.get('calibrator_path'):
            calibrator_path = Path(config['calibrator_path'])
            if not calibrator_path.is_absolute():
                calibrator_path = get_calibration_config_path().parent / calibrator_path
        else:
            calibrator_path = get_calibration_model_path()
    else:
        calibrator_path = Path(calibrator_path)
    
    if not calibrator_path.exists():
        logger.warning(f"Calibrator not found at {calibrator_path}")
        logger.info("Calibration model has not been trained yet.")
        logger.info("To train: run backend/scripts/train_calibration.py after implementing production prediction pipeline")
        return None
    
    try:
        with open(calibrator_path, 'rb') as f:
            calibrator = pickle.load(f)
    except ImportError as e:
        logger.error(f"Failed to load calibrator: missing dependency {e}")
        logger.error("Calibration requires scikit-learn. Install with: pip install scikit-learn")
        return None
    except Exception as e:
        logger.error(f"Failed to load calibrator: {e}")
        return None
    
    if not isinstance(calibrator, Calibrator1X2):
        logger.error(f"Loaded object is not a Calibrator1X2: {type(calibrator)}")
        return None
    
    logger.info(f"Loaded trained calibrator from {calibrator_path}")
    logger.info(f"  Home fitted: {calibrator.home_calibrator.is_fitted}")
    logger.info(f"  Draw fitted: {calibrator.draw_calibrator.is_fitted}")
    logger.info(f"  Away fitted: {calibrator.away_calibrator.is_fitted}")
    logger.info(f"  Overall fitted: {calibrator.is_fitted}")
    
    return calibrator


def create_calibration_integration_with_trained_model():
    """Create CalibrationIntegration with trained calibrator.
    
    Returns:
        CalibrationIntegration instance with trained calibrator if available,
        otherwise default untrained instance
    """
    from app.prediction.model_orchestrator import CalibrationIntegration
    
    calibrator = load_trained_calibrator()
    
    if calibrator is None:
        logger.warning("No trained calibrator available, using default untrained calibrator")
        return CalibrationIntegration.create_default()
    
    if not calibrator.is_fitted:
        logger.warning("Loaded calibrator is not fitted, predictions will be uncalibrated")
    
    return CalibrationIntegration(calibrator=calibrator)
