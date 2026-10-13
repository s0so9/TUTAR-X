# Logistic Regression Model Status

## Current Status: UNAVAILABLE (By Design)

The Logistic Regression model (`logistic_regression_v1`) is currently unavailable and this is **not a bug** - it's an architectural limitation that requires future work.

## Why It's Unavailable

The model has two architectural requirements that are not yet satisfied:

### 1. Model Must Be Fitted

The Logistic Regression model uses supervised learning and requires training on historical match data with known outcomes before it can make predictions.

**Current State:** `_is_fitted = False`

**What's Needed:**
- Historical match data with outcomes (home_win, draw, away_win)
- Feature extraction for those historical matches
- Training infrastructure to call `model.fit(samples)`
- Model persistence to save/load trained weights

### 2. Feature Requirements Not Satisfied

The model expects the following features (from `DEFAULT_FEATURE_KEYS`):

**Expected Features:**
- `home_attack_strength` ✓ (available from TeamStrengthMetrics)
- `home_defense_strength` ✓ (available from TeamStrengthMetrics)
- `home_home_strength` ❌ (NOT AVAILABLE - needs home-only performance calculation)
- `home_away_strength` ❌ (NOT AVAILABLE - needs away-only performance calculation)
- `home_recent_wins` ❌ (available but not in snapshot.get_feature_dict())
- `home_recent_draws` ❌ (available but not in snapshot.get_feature_dict())
- `home_recent_losses` ❌ (available but not in snapshot.get_feature_dict())
- `home_form_points_per_match` ✓ (available from FormMetrics)
- `away_attack_strength` ✓ (available from TeamStrengthMetrics)
- `away_defense_strength` ✓ (available from TeamStrengthMetrics)
- `away_home_strength` ❌ (NOT AVAILABLE - needs home-only performance calculation)
- `away_away_strength` ❌ (NOT AVAILABLE - needs away-only performance calculation)
- `away_recent_wins` ❌ (available but not in snapshot.get_feature_dict())
- `away_recent_draws` ❌ (available but not in snapshot.get_feature_dict())
- `away_recent_losses` ❌ (available but not in snapshot.get_feature_dict())
- `away_form_points_per_match` ✓ (available from FormMetrics)

## Missing Feature Semantics

### `home_home_strength` vs `away_away_strength`

These features represent:
- `home_home_strength`: Performance of home team when playing AT HOME (points per match at home)
- `away_away_strength`: Performance of away team when playing AWAY (points per match away)
- `home_away_strength`: Performance of home team when playing AWAY (historical)
- `away_home_strength`: Performance of away team when playing AT HOME (historical)

**Current State:**
- `TeamStrengthCalculator._calculate_venue_strength()` calculates these values
- They are stored in the features dict as `home_strength` and `away_strength`
- But the Logistic Regression model expects them with different naming

**What They Mean:**
- These capture home advantage effects at the team level
- A team might have 2.5 PPM at home but only 1.2 PPM away
- Logistic Regression uses these to model home/away performance differences

### Recent Form Counts

The model expects integer counts of recent wins/draws/losses, not just aggregated form scores.

**Current State:**
- `FormMetrics` contains `wins`, `draws`, `losses` fields ✓
- These are available in the feature extraction layer ✓
- BUT they are not exposed in `MatchFeatureSnapshot.get_feature_dict()` ❌

## How to Enable Logistic Regression (Future Work)

### Phase 1: Feature Engineering Alignment

1. **Add venue-specific strength features to snapshot:**
   ```python
   # In MatchFeatureSnapshot.get_feature_dict()
   if self.home_team_home_record:
       features["home_home_strength"] = self.home_team_home_record.points_per_match
   if self.away_team_away_record:
       features["away_away_strength"] = self.away_team_away_record.points_per_match
   # Cross-venue for completeness
   if self.home_team_away_record:
       features["home_away_strength"] = self.home_team_away_record.points_per_match
   if self.away_team_home_record:
       features["away_home_strength"] = self.away_team_home_record.points_per_match
   ```

2. **Add recent form counts to snapshot:**
   ```python
   # In MatchFeatureSnapshot.get_feature_dict()
   if self.home_form:
       features["home_recent_wins"] = float(self.home_form.wins) if self.home_form.wins is not None else None
       features["home_recent_draws"] = float(self.home_form.draws) if self.home_form.draws is not None else None
       features["home_recent_losses"] = float(self.home_form.losses) if self.home_form.losses is not None else None
   ```

### Phase 2: Training Infrastructure

1. **Create training script:**
   ```python
   # backend/scripts/train_logistic_regression.py
   from app.prediction.logistic_regression import LogisticRegressionModel
   from app.database.session import get_session
   from app.database.models import Match

   def extract_training_samples():
       # Query finished matches from database
       # Extract features for each match
       # Label with actual outcome
       pass

   def train_model():
       samples = extract_training_samples()
       model = LogisticRegressionModel()
       model.fit(samples)
       # Save model weights
       pass
   ```

2. **Create model persistence:**
   ```python
   # Save trained weights to config file
   import pickle
   with open("backend/config/logistic_regression_weights.pkl", "wb") as f:
       pickle.dump(model._weights, f)
   ```

3. **Load trained model in orchestrator:**
   ```python
   # In model_orchestrator.py
   lr_model = LogisticRegressionModel()
   if os.path.exists("config/logistic_regression_weights.pkl"):
       with open("config/logistic_regression_weights.pkl", "rb") as f:
           lr_model._weights = pickle.load(f)
           lr_model._is_fitted = True
   ```

### Phase 3: Validation

1. Run backtesting to validate model performance
2. Compare with other models (Poisson, Dixon-Coles, etc.)
3. Tune hyperparameters (learning_rate, n_epochs, l2_lambda)
4. Integrate into production ensemble if performance justifies it

## Current Workaround

The model is correctly excluded from predictions when unavailable:

```python
result = orchestrator.run_all(snapshot)
# Logistic Regression appears in result.unavailable_models
# Ensemble correctly excludes it and uses the 6 available models
```

This is the **correct behavior** per AGENTS.md rules:
- Never fabricate data
- Never force incomplete models to run
- Document limitations explicitly
- Only mark as "working" when actually verified

## Recommendation

**Option 1: Complete the work (recommended for future phase)**
- Implement venue-specific features
- Build training infrastructure
- Train and validate model
- Integrate into production

**Option 2: Remove from default registry (current state is acceptable)**
- Keep the model code for future use
- Don't register it in `create_default_registry()` until trained
- Document as "experimental" or "requires training"

**Current Decision: Keep as unavailable**
The model remains registered but returns `ModelAvailability.available=False` which is correct and transparent behavior. The ensemble works with the 6 available models.

## Test Coverage

The model's unavailability is **correctly tested**:

```python
# From test_all_models_integration.py
def test_logistic_regression_not_fitted(self, minimal_snapshot):
    lr = LogisticRegressionModel()
    result = orchestrator.run_all(minimal_snapshot)

    # Should be unavailable since model is not fitted ✓
    assert len(result.unavailable_models) == 1
    assert "model_not_fitted" in str(unavail.availability.reason) ✓
```

## Summary

✅ Logistic Regression model code is correct and complete
✅ Unavailability is properly detected and handled
✅ Ensemble works correctly without it
❌ Model is not fitted (requires training infrastructure)
❌ Some required features don't exist in snapshot (requires feature engineering)

**Status:** Working as designed - unavailable until training infrastructure is built.
