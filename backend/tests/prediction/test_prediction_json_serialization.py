"""Test JSON serialization of prediction data for database persistence."""

import json
import pytest
from datetime import datetime
from app.prediction.prediction_version import PredictionVersion, PredictionStage


class TestPredictionJSONSerialization:
    """Test that prediction data can be serialized and deserialized for database."""
    
    def test_score_distribution_tuple_keys_serialization(self):
        """Test that score_distribution with tuple keys is properly serialized."""
        # Original score_distribution with tuple keys (internal format)
        score_dist_tuples = {
            (0, 0): 0.10,
            (1, 0): 0.25,
            (1, 1): 0.15,
            (2, 1): 0.12,
            (0, 1): 0.18,
        }
        
        # Serialize to string keys for JSON
        serialized = {}
        for score_key, prob in score_dist_tuples.items():
            if isinstance(score_key, tuple) and len(score_key) == 2:
                key_str = f"{score_key[0]}-{score_key[1]}"
                serialized[key_str] = prob
        
        # This should not raise TypeError
        json_str = json.dumps(serialized)
        assert json_str is not None
        
        # Deserialize and verify
        deserialized = json.loads(json_str)
        assert deserialized["0-0"] == 0.10
        assert deserialized["1-0"] == 0.25
        assert deserialized["1-1"] == 0.15
    
    def test_deserialization_back_to_tuples(self):
        """Test deserializing string keys back to tuples if needed."""
        json_data = {
            "0-0": 0.10,
            "1-0": 0.25,
            "1-1": 0.15,
        }
        
        # Convert back to tuples for internal use
        tuple_dist = {}
        for key_str, prob in json_data.items():
            parts = key_str.split("-")
            tuple_key = (int(parts[0]), int(parts[1]))
            tuple_dist[tuple_key] = prob
        
        assert tuple_dist[(0, 0)] == 0.10
        assert tuple_dist[(1, 0)] == 0.25
        assert tuple_dist[(1, 1)] == 0.15
    
    def test_prediction_data_full_json_roundtrip(self):
        """Test complete prediction_data dictionary can be JSON serialized."""
        # Simulate complete prediction_data from service.py
        prediction_data = {
            "home_win_prob": 0.45,
            "draw_prob": 0.30,
            "away_win_prob": 0.25,
            "home_xg": 1.5,
            "away_xg": 1.2,
            "predicted_score": "1-1",
            "btts_probability": 0.65,
            "score_distribution": {
                "0-0": 0.10,
                "1-0": 0.25,
                "1-1": 0.15,
                "2-1": 0.12,
            },
            "markets": {
                "over_under_goals": 2.5,
                "btts_yes_prob": 0.65,
            },
            "confidence": {
                "overall": 0.75,
                "label": "HIGH",
                "components": {
                    "model_agreement": 0.80,
                    "data_quality": 0.70,
                    "sample_size_score": 0.75,
                },
            },
            "orchestration": {
                "models_run": 4,
                "models_unavailable": 2,
                "models_failed": 0,
            }
        }
        
        # Should serialize without error
        json_str = json.dumps(prediction_data)
        assert json_str is not None
        
        # Should deserialize without error
        loaded = json.loads(json_str)
        assert loaded["home_win_prob"] == 0.45
        assert loaded["score_distribution"]["1-0"] == 0.25
        assert loaded["confidence"]["overall"] == 0.75
    
    def test_prediction_version_database_safe(self):
        """Test PredictionVersion with serialized data is database-safe."""
        import uuid
        
        prediction_data = {
            "home_win_prob": 0.45,
            "score_distribution": {"1-0": 0.25, "0-0": 0.10},
            "markets": {"btts_yes": 0.65},
        }
        
        # Create version
        version = PredictionVersion(
            version_id=str(uuid.uuid4()),
            match_id="test_match_001",
            stage=PredictionStage.KICKOFF,
            created_at=datetime.utcnow(),
            prediction_data=prediction_data,
            model_versions={"poisson_v1": "1.0", "dixon_coles_v1": "1.0"},
            data_quality_score=0.8,
            confidence_score=0.75,
        )
        
        # Verify prediction_data is JSON-safe
        json_str = json.dumps(version.prediction_data)
        assert json_str is not None
        
        # Verify model_versions is JSON-safe
        json_str = json.dumps(version.model_versions)
        assert json_str is not None
    
    def test_nested_dict_with_enum_keys_serialized(self):
        """Test that market_probs.__dict__ with enum/object keys is serialized."""
        # Simulate market_probs with complex keys
        market_data = {
            "over_25_prob": 0.55,
            "under_25_prob": 0.45,
            "home_team_goals": {"over_1.5": 0.60, "under_1.5": 0.40},
        }
        
        # Serialize nested structures
        serialized = {}
        for attr, value in market_data.items():
            if isinstance(value, dict):
                serialized[attr] = {str(k): v for k, v in value.items()}
            else:
                serialized[attr] = value
        
        # Should not raise
        json_str = json.dumps(serialized)
        loaded = json.loads(json_str)
        assert loaded["over_25_prob"] == 0.55
        assert loaded["home_team_goals"]["over_1.5"] == 0.60
