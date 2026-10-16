"""Train calibration models using historical match data.

This script:
1. Loads settled predictions with actual outcomes from PredictionVersionRepository
2. Extracts raw ensemble probabilities and actual 1X2 outcomes
3. Trains calibration models (isotonic regression)
4. Saves calibration configuration for production use

Temporal Safety:
- Uses only settled predictions with known outcomes
- Chronological ordering with temporal cutoff
- No future data leakage

Data Requirements:
- Minimum 30 settled predictions for training
- Each prediction must have raw ensemble probabilities
- Actual outcomes must be settled (HOME_WIN/DRAW/AWAY_WIN)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Optional
import pickle
import json

from sqlalchemy import text, func
from app.database import SessionLocal, engine
from app.database.prediction_repository import PredictionVersionRepository
from app.prediction.calibration_engine import (
    CalibrationData,
    CalibrationEngine,
    IsotonicCalibration,
    CalibrationStatus
)
from app.prediction.model_orchestrator import Calibrator1X2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_settled_predictions_with_outcomes(
    db,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> Tuple[
    List[float], List[float], List[float],  # Raw ensemble probs (home, draw, away)
    List[float], List[float], List[float],  # Actual outcomes (home, draw, away)
    List[datetime]  # Timestamps
]:
    """Load settled predictions with actual 1X2 outcomes from database.
    
    Args:
        db: Database session
        start_date: Optional start date filter
        end_date: Optional end date filter
        
    Returns:
        Tuple of (home_probs, draw_probs, away_probs, 
                  home_outcomes, draw_outcomes, away_outcomes, timestamps)
        
    Raises:
        ValueError: If insufficient data for calibration training
    """
    logger.info("Loading settled predictions from database...")
    
    # Query: Join predictions with matches to get actual outcomes
    # Use PredictionVersion table which stores prediction snapshots
    query = text("""
        SELECT 
            pv.id,
            pv.match_id,
            pv.predicted_at,
            pv.ensemble_home_win_prob,
            pv.ensemble_draw_prob,
            pv.ensemble_away_win_prob,
            m.home_score,
            m.away_score,
            m.scheduled_at
        FROM prediction_versions pv
        INNER JOIN matches m ON pv.match_id = m.id
        WHERE m.home_score IS NOT NULL
        AND m.away_score IS NOT NULL
        AND pv.ensemble_home_win_prob IS NOT NULL
        AND pv.ensemble_draw_prob IS NOT NULL
        AND pv.ensemble_away_win_prob IS NOT NULL
        AND pv.predicted_at IS NOT NULL
        ORDER BY pv.predicted_at ASC
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query)
        rows = result.fetchall()
    
    if not rows:
        logger.error("No settled predictions found with ensemble probabilities")
        raise ValueError(
            "Cannot train calibration: no settled predictions with ensemble probabilities. "
            "Ensure predictions are stored with raw ensemble outputs before calibration."
        )
    
    logger.info(f"Found {len(rows)} settled predictions")
    
    home_probs = []
    draw_probs = []
    away_probs = []
    home_outcomes = []
    draw_outcomes = []
    away_outcomes = []
    timestamps = []
    
    skipped_no_prediction = 0
    skipped_invalid_prob = 0
    
    for row in rows:
        pred_id, match_id, predicted_at, h_prob, d_prob, a_prob, h_score, a_score, scheduled_at = row
        
        # Validate probabilities
        if h_prob is None or d_prob is None or a_prob is None:
            skipped_no_prediction += 1
            continue
        
        # Check for valid probability values
        if not (0.0 <= h_prob <= 1.0 and 0.0 <= d_prob <= 1.0 and 0.0 <= a_prob <= 1.0):
            skipped_invalid_prob += 1
            continue
        
        # Check predicted_at is valid
        if predicted_at is None:
            logger.warning(f"Prediction {pred_id} missing predicted_at timestamp, skipping")
            continue
        
        # Determine actual 1X2 outcome from scores
        if h_score > a_score:
            h_out, d_out, a_out = 1.0, 0.0, 0.0  # HOME_WIN
        elif h_score == a_score:
            h_out, d_out, a_out = 0.0, 1.0, 0.0  # DRAW
        else:
            h_out, d_out, a_out = 0.0, 0.0, 1.0  # AWAY_WIN
        
        home_probs.append(float(h_prob))
        draw_probs.append(float(d_prob))
        away_probs.append(float(a_prob))
        home_outcomes.append(h_out)
        draw_outcomes.append(d_out)
        away_outcomes.append(a_out)
        
        # Use predicted_at as timestamp
        if isinstance(predicted_at, str):
            predicted_at = datetime.fromisoformat(predicted_at)
        timestamps.append(predicted_at)
    
    if skipped_no_prediction > 0:
        logger.warning(f"Skipped {skipped_no_prediction} predictions with missing probabilities")
    if skipped_invalid_prob > 0:
        logger.warning(f"Skipped {skipped_invalid_prob} predictions with invalid probability values")
    
    MIN_SAMPLES = 30
    if len(home_probs) < MIN_SAMPLES:
        logger.error(f"Insufficient valid samples: {len(home_probs)} < {MIN_SAMPLES}")
        raise ValueError(
            f"Cannot train calibration: {len(home_probs)} valid samples < {MIN_SAMPLES} minimum. "
            "Generate and store more predictions with ensemble outputs."
        )
    
    logger.info(f"Loaded {len(home_probs)} valid prediction-outcome pairs")
    return (home_probs, draw_probs, away_probs,
            home_outcomes, draw_outcomes, away_outcomes,
            timestamps)


def train_calibration_models(
    home_probs: List[float],
    draw_probs: List[float],
    away_probs: List[float],
    home_outcomes: List[float],
    draw_outcomes: List[float],
    away_outcomes: List[float],
    timestamps: List[datetime],
    cutoff_date: datetime = None
) -> Calibrator1X2:
    """Train calibration models for 1X2 outcomes.
    
    Args:
        home_probs: Predicted home win probabilities
        draw_probs: Predicted draw probabilities
        away_probs: Predicted away win probabilities
        home_outcomes: Actual home win outcomes (0 or 1)
        draw_outcomes: Actual draw outcomes (0 or 1)
        away_outcomes: Actual away win outcomes (0 or 1)
        timestamps: Timestamps of predictions
        cutoff_date: Optional temporal cutoff for training
        
    Returns:
        Trained Calibrator1X2 instance
        
    Raises:
        ValueError: If insufficient samples (< 30)
    """
    MIN_SAMPLES = 30
    if len(home_probs) < MIN_SAMPLES:
        raise ValueError(
            f"Insufficient samples for calibration training: {len(home_probs)} < {MIN_SAMPLES}"
        )
    
    logger.info(f"Training calibration models on {len(home_probs)} samples...")
    
    # Create calibration data for each outcome
    home_data = CalibrationData(
        predicted_probs=home_probs,
        actual_outcomes=home_outcomes,
        timestamps=timestamps
    )
    
    draw_data = CalibrationData(
        predicted_probs=draw_probs,
        actual_outcomes=draw_outcomes,
        timestamps=timestamps
    )
    
    away_data = CalibrationData(
        predicted_probs=away_probs,
        actual_outcomes=away_outcomes,
        timestamps=timestamps
    )
    
    # Create and fit calibrator
    calibrator = Calibrator1X2()
    
    # Fit each outcome's calibrator
    home_engine = CalibrationEngine(method="isotonic")
    home_engine.fit(home_data, cutoff_date=cutoff_date)
    calibrator.home_calibrator = home_engine.calibrator
    
    draw_engine = CalibrationEngine(method="isotonic")
    draw_engine.fit(draw_data, cutoff_date=cutoff_date)
    calibrator.draw_calibrator = draw_engine.calibrator
    
    away_engine = CalibrationEngine(method="isotonic")
    away_engine.fit(away_data, cutoff_date=cutoff_date)
    calibrator.away_calibrator = away_engine.calibrator
    
    logger.info(f"Calibration training complete:")
    logger.info(f"  Home: fitted={calibrator.home_calibrator.is_fitted}, n={home_engine.calibration_sample_size}")
    logger.info(f"  Draw: fitted={calibrator.draw_calibrator.is_fitted}, n={draw_engine.calibration_sample_size}")
    logger.info(f"  Away: fitted={calibrator.away_calibrator.is_fitted}, n={away_engine.calibration_sample_size}")
    
    # Calculate and log calibration metrics
    from app.prediction.calibration import brier_score, calibration_error
    
    # Brier scores (uncalibrated)
    brier_uncal = brier_score(home_probs, home_outcomes)
    logger.info(f"  Brier score (uncalibrated home_win): {brier_uncal:.4f}")
    
    # Calibration error
    cal_error = calibration_error(home_probs, home_outcomes, n_bins=10)
    logger.info(f"  Expected Calibration Error (home_win): {cal_error.ece:.4f}")
    
    return calibrator


def save_calibration_config(calibrator: Calibrator1X2, output_path: str, metadata: Dict):
    """Save trained calibration configuration with metadata.
    
    Args:
        calibrator: Trained Calibrator1X2 instance
        output_path: Path to save configuration
        metadata: Training metadata (sample count, date range, metrics)
    """
    config = {
        'trained_at': datetime.utcnow().isoformat(),
        'home_fitted': calibrator.home_calibrator.is_fitted,
        'draw_fitted': calibrator.draw_calibrator.is_fitted,
        'away_fitted': calibrator.away_calibrator.is_fitted,
        'method': 'isotonic',
        'calibrator_path': output_path.replace('.json', '.pkl'),
        'metadata': metadata
    }
    
    # Save config
    with open(output_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    # Save calibrator (pickle)
    pkl_path = output_path.replace('.json', '.pkl')
    with open(pkl_path, 'wb') as f:
        pickle.dump(calibrator, f)
    
    logger.info(f"Calibration configuration saved to {output_path}")
    logger.info(f"Calibrator saved to {pkl_path}")


def main():
    """Main calibration training workflow."""
    logger.info("=== Phase 10.3 Calibration Training (Real Pipeline) ===")
    
    # Load actual predictions and outcomes from database
    db = SessionLocal()
    try:
        (home_probs, draw_probs, away_probs,
         home_outcomes, draw_outcomes, away_outcomes,
         timestamps) = load_settled_predictions_with_outcomes(db)
    except ValueError as e:
        logger.error(f"Failed to load prediction data: {e}")
        logger.error("To train calibration:")
        logger.error("  1. Generate predictions on historical matches using production pipeline")
        logger.error("  2. Store predictions in PredictionVersion table with ensemble probabilities")
        logger.error("  3. Ensure matches have settled outcomes (home_score, away_score)")
        logger.error("  4. Re-run this script")
        return
    finally:
        db.close()
    
    # Training metadata
    metadata = {
        'n_samples': len(home_probs),
        'date_range': {
            'first': min(timestamps).isoformat() if timestamps else None,
            'last': max(timestamps).isoformat() if timestamps else None,
        },
        'data_source': 'prediction_versions table (raw ensemble probabilities)',
        'market': '1X2',
        'schema_version': '1.0',
        'feature_groups': 'production_pipeline',
        'model_versions': 'ensemble_v1'
    }
    
    # Train calibration with temporal cutoff
    # Cutoff = first timestamp in fold (chronological train/validation split)
    # For initial training, use all data up to most recent timestamp
    cutoff = max(timestamps) if timestamps else None
    
    logger.info(f"Training calibration with cutoff: {cutoff}")
    
    calibrator = train_calibration_models(
        home_probs, draw_probs, away_probs,
        home_outcomes, draw_outcomes, away_outcomes,
        timestamps,
        cutoff_date=cutoff
    )
    
    # Calculate holdout metrics (split last 20% as validation)
    split_idx = int(len(home_probs) * 0.8)
    
    if split_idx >= 30 and len(home_probs) - split_idx >= 10:
        logger.info(f"\nComputing holdout validation metrics (n={len(home_probs) - split_idx})...")
        
        # Calibrate validation set
        val_h_probs = home_probs[split_idx:]
        val_d_probs = draw_probs[split_idx:]
        val_a_probs = away_probs[split_idx:]
        val_h_outcomes = home_outcomes[split_idx:]
        val_d_outcomes = draw_outcomes[split_idx:]
        val_a_outcomes = away_outcomes[split_idx:]
        
        from app.prediction.calibration import brier_score, log_loss_multiclass
        
        # Uncalibrated metrics
        brier_uncal = sum(
            ((h - h_o)**2 + (d - d_o)**2 + (a - a_o)**2) / 3.0
            for h, d, a, h_o, d_o, a_o in zip(
                val_h_probs, val_d_probs, val_a_probs,
                val_h_outcomes, val_d_outcomes, val_a_outcomes
            )
        ) / len(val_h_probs)
        
        # Calibrated metrics
        cal_probs = [
            calibrator.calibrate_1x2(h, d, a)
            for h, d, a in zip(val_h_probs, val_d_probs, val_a_probs)
        ]
        
        brier_cal = sum(
            ((h - h_o)**2 + (d - d_o)**2 + (a - a_o)**2) / 3.0
            for (h, d, a), (h_o, d_o, a_o) in zip(cal_probs, zip(val_h_outcomes, val_d_outcomes, val_a_outcomes))
        ) / len(cal_probs)
        
        logger.info(f"  Holdout Brier (uncalibrated): {brier_uncal:.4f}")
        logger.info(f"  Holdout Brier (calibrated): {brier_cal:.4f}")
        logger.info(f"  Improvement: {brier_uncal - brier_cal:.4f}")
        
        metadata['holdout_metrics'] = {
            'n_holdout': len(val_h_probs),
            'brier_uncalibrated': brier_uncal,
            'brier_calibrated': brier_cal,
            'improvement': brier_uncal - brier_cal
        }
    else:
        logger.warning("Insufficient data for holdout validation")
        metadata['holdout_metrics'] = None
    
    # Save configuration with metadata
    config_dir = os.path.join(os.path.dirname(__file__), '..', 'config')
    os.makedirs(config_dir, exist_ok=True)
    
    config_path = os.path.join(config_dir, 'calibration_config.json')
    save_calibration_config(calibrator, config_path, metadata)
    
    logger.info("=== Calibration Training Complete ===")
    logger.info(f"Metadata: {json.dumps(metadata, indent=2)}")
    
    # Test calibration
    logger.info("\nTesting calibration:")
    test_probs = [0.3, 0.5, 0.7]
    for prob in test_probs:
        cal_home, cal_draw, cal_away = calibrator.calibrate_1x2(prob, 0.25, 1.0-prob-0.25)
        logger.info(f"  Input: H={prob:.2f}, D=0.25, A={1.0-prob-0.25:.2f}")
        logger.info(f"  Calibrated: H={cal_home:.2f}, D={cal_draw:.2f}, A={cal_away:.2f}")


if __name__ == "__main__":
    main()
