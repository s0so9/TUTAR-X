"""Centralized model artifact path configuration.

All model file paths and artifact locations should be resolved through this module
to avoid hardcoded paths and CWD dependencies.
"""

from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def get_backend_root() -> Path:
    """Get the backend/ directory root.
    
    Returns:
        Absolute path to backend/ directory
    """
    # This file is in backend/app/prediction/
    # Go up 2 levels to reach backend/
    return Path(__file__).resolve().parents[2]


def get_model_dir() -> Path:
    """Get the model artifacts directory.
    
    Returns:
        Absolute path to backend/config/ (model storage location)
    """
    return get_backend_root() / 'config'


def get_logistic_model_path() -> Path:
    """Get path to trained logistic regression model.
    
    Returns:
        Absolute path to logistic_model.pkl
    """
    return get_model_dir() / 'logistic_model.pkl'


def get_calibration_model_path() -> Path:
    """Get path to trained calibration model.
    
    Returns:
        Absolute path to calibration_config.pkl
    """
    return get_model_dir() / 'calibration_config.pkl'


def get_calibration_config_path() -> Path:
    """Get path to calibration configuration JSON.
    
    Returns:
        Absolute path to calibration_config.json
    """
    return get_model_dir() / 'calibration_config.json'


def ensure_model_dir_exists() -> None:
    """Ensure model artifact directory exists."""
    model_dir = get_model_dir()
    model_dir.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Model directory ensured: {model_dir}")


def validate_model_file(path: Path, model_name: str) -> bool:
    """Validate that a model file exists and is readable.
    
    Args:
        path: Path to model file
        model_name: Human-readable model name for logging
        
    Returns:
        True if file exists and is readable, False otherwise
    """
    if not path.exists():
        logger.info(f"{model_name} not found at {path}")
        logger.info(f"This model has not been trained yet.")
        return False
    
    if not path.is_file():
        logger.warning(f"{model_name} path is not a file: {path}")
        return False
    
    return True


# Convenience functions that combine path resolution and validation

def get_trained_logistic_model_path() -> Optional[Path]:
    """Get path to trained logistic model if it exists.
    
    Returns:
        Path if model exists and is valid, None otherwise
    """
    path = get_logistic_model_path()
    if validate_model_file(path, "Logistic regression model"):
        return path
    return None


def get_trained_calibration_model_path() -> Optional[Path]:
    """Get path to trained calibration model if it exists.
    
    Returns:
        Path if model exists and is valid, None otherwise
    """
    path = get_calibration_model_path()
    if validate_model_file(path, "Calibration model"):
        return path
    return None
