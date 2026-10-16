"""Final 7-model architecture validation - check_requirements ile."""
import sys
sys.path.insert(0, '.')

# Sample features - tipik bir maç için temel feature'lar
sample_features = {
    "home_goals_scored_avg": 1.5,
    "away_goals_scored_avg": 1.2,
    "home_goals_conceded_avg": 1.1,
    "away_goals_conceded_avg": 1.4,
    "home_form_score": 0.6,
    "away_form_score": 0.4,
    # Elo ratings - genelde mevcut değil
    "elo_home": None,
    "elo_away": None,
    # xG data - genelde mevcut değil  
    "home_expected_goals": None,
    "away_expected_goals": None,
}

from app.prediction.poisson import PoissonModel
from app.prediction.dixon_coles import DixonColesModel
from app.prediction.elo import EloModel
from app.prediction.monte_carlo import MonteCarloSimulation
from app.prediction.negative_binomial import NegativeBinomialModel
from app.prediction.form_adjusted import FormAdjustedModel
from app.prediction.logistic_regression import LogisticRegressionModel

print("="*80)
print("7-MODEL ARCHITECTURE VALIDATION")
print("="*80)
print()

models = [
    ("Poisson", "poisson_v1", PoissonModel()),
    ("Dixon-Coles", "dixon_coles_v1", DixonColesModel(poisson_model=PoissonModel())),
    ("Elo", "elo_v1", EloModel()),
    ("Monte Carlo", "monte_carlo_v1", MonteCarloSimulation()),
    ("Negative Binomial", "negative_binomial_v1", NegativeBinomialModel()),
    ("Form Adjusted", "form_adjusted_v1", FormAdjustedModel(base_model=PoissonModel())),
    ("Logistic Regression", "logistic_regression_v1", LogisticRegressionModel()),
]

print("Sample Features Available:")
for k, v in sample_features.items():
    status = "AVAILABLE" if v is not None else "MISSING"
    print(f"  {k:30s}: {status}")
print()

print("="*80)
print("MODEL REQUIREMENTS CHECK")
print("="*80)
print()

can_execute = []
cannot_execute = []

for name, model_id, model in models:
    try:
        requirements_met, missing = model.check_requirements(sample_features)
        
        if requirements_met:
            can_execute.append((name, model_id))
            print(f"✓ {name:25s} ({model_id:25s}): CAN EXECUTE")
        else:
            cannot_execute.append((name, model_id, missing))
            print(f"✗ {name:25s} ({model_id:25s}): MISSING DATA")
            for feat in missing:
                print(f"    - {feat}")
    except Exception as e:
        cannot_execute.append((name, model_id, [str(e)]))
        print(f"✗ {name:25s} ({model_id:25s}): ERROR - {e}")

print()
print("="*80)
print("SUMMARY")
print("="*80)
print()
print(f"Can Execute: {len(can_execute)}/7 models")
print(f"Cannot Execute: {len(cannot_execute)}/7 models")
print()

print("EXECUTING MODELS:")
for name, model_id in can_execute:
    print(f"  ✓ {model_id}")

print()
print("NOT EXECUTING (Missing Data):")
for name, model_id, missing in cannot_execute:
    print(f"  ✗ {model_id}")
    if isinstance(missing, list) and missing:
        print(f"      Reason: {', '.join(missing)}")

print()
print("="*80)
print("INTERPRETATION")
print("="*80)
print()
print(f"With typical feature availability, {len(can_execute)} models can execute.")
print(f"These {len(can_execute)} models contribute to the ensemble prediction.")
print()

if len(can_execute) == 4:
    print("✓ This matches the observed '4 models successful' from profiler!")
    print()
    print("The 3 unavailable models likely require:")
    for name, model_id, missing in cannot_execute:
        print(f"  - {name}: {', '.join(missing) if isinstance(missing, list) else missing}")
