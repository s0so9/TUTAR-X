"""Basit ve doğrudan 7-model kontrolü."""
import sys
sys.path.insert(0, '.')

from app.database.session import get_db
from app.database.models import Match
from app.features.match_features import MatchFeatureExtractor
from app.prediction.model_orchestrator import ModelOrchestrator

# Silence warnings
import warnings
warnings.filterwarnings('ignore')

db = next(get_db())
match = db.query(Match).first()

print("Extracting features...")
extractor = MatchFeatureExtractor(db)
snapshot = extractor.extract_features(match)

print("Running orchestrator...")
orchestrator = ModelOrchestrator.create_default_registry()
result = orchestrator.run_all(snapshot)

print("\n" + "="*80)
print("7-MODEL ARCHITECTURE VALIDATION")
print("="*80)
print(f"\nRegistered: 7 models")
print(f"Successful: {len(result.successful_predictions)} models")
print(f"Unavailable: {len(result.unavailable_models)} models")
print(f"Failed: {len(result.failed_models)} models")

print("\n" + "="*80)
print("SUCCESSFUL MODELS (Executing & Contributing to Ensemble):")
print("="*80)
for o in result.successful_predictions:
    print(f"  ✓ {o.model_id}")

print("\n" + "="*80)
print("UNAVAILABLE MODELS (Missing Required Data):")
print("="*80)
for o in result.unavailable_models:
    print(f"  ✗ {o.model_id}")
    if o.availability and o.availability.missing_features:
        for feat in o.availability.missing_features:
            print(f"      Missing: {feat}")

if result.failed_models:
    print("\n" + "="*80)
    print("FAILED MODELS (Execution Errors):")
    print("="*80)
    for o in result.failed_models:
        print(f"  ✗ {o.model_id}: {o.error_message}")

print("\n" + "="*80)
print("SUMMARY")
print("="*80)
print(f"✓ {len(result.successful_predictions)}/7 models executing successfully")
print(f"✗ {len(result.unavailable_models)}/7 models unavailable (missing data)")
if result.failed_models:
    print(f"✗ {len(result.failed_models)}/7 models failed (errors)")
