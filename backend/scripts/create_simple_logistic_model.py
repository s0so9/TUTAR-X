"""Create a simple trained logistic regression model for testing."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pickle
from app.prediction.logistic_regression import LogisticRegressionModel

# Create and fit a simple model with synthetic data
print("Creating simple logistic regression model...")

model = LogisticRegressionModel()

# Create minimal synthetic training data
samples = []
for i in range(50):
    # Synthetic features
    features = {
        'home_goals_scored_avg': 1.5 + (i % 10) * 0.1,
        'away_goals_scored_avg': 1.2 + (i % 8) * 0.1,
        'home_form_score': 0.5 + (i % 6) * 0.2,
        'away_form_score': 0.4 + (i % 7) * 0.2,
    }
    
    # Simple synthetic labels
    if i % 3 == 0:
        label = "home_win"
    elif i % 3 == 1:
        label = "draw"  
    else:
        label = "away_win"
    
    samples.append((features, label))

# Train model
print("Training model with synthetic data...")
model.fit(samples)

# Save model
cache_path = Path("backend/app/config/logistic_model.pkl")
cache_path.parent.mkdir(parents=True, exist_ok=True)

model_data = {
    'weights': model._weights,
    'training_stats': model._training_stats,
    'is_fitted': model._is_fitted,
    'feature_keys': model.feature_keys,
    'note': 'Simple synthetic model for testing - not for production use'
}

with open(cache_path, 'wb') as f:
    pickle.dump(model_data, f)

print(f"Saved simple trained model to {cache_path}")
print("This is a synthetic model for testing purposes only")