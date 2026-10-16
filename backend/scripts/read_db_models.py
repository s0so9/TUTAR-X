"""Veritabanındaki son prediction'dan model listesini oku."""
import sys
sys.path.insert(0, '.')
import sqlite3
import json

conn = sqlite3.connect('football_intelligence.db')
cursor = conn.cursor()

# Son prediction version'ı al
cursor.execute('SELECT version_metadata FROM prediction_versions ORDER BY created_at DESC LIMIT 1')
row = cursor.fetchone()

if row:
    metadata = json.loads(row[0])
    models = metadata.get('participating_models', [])
    
    print("="*80)
    print("7-MODEL VALIDATION - Database Analysis")
    print("="*80)
    print()
    print(f"Participating Models in Latest Prediction: {len(models)}")
    print()
    
    for model in models:
        print(f"  ✓ {model['model_id']} v{model['version']}")
    
    print()
    print("="*80)
    print(f"CONFIRMED: {len(models)} models are EXECUTING and contributing to ensemble")
    print("="*80)
    
    # Hangi 3 model eksik?
    all_expected = [
        'poisson_v1',
        'dixon_coles_v1',
        'elo_v1',
        'monte_carlo_v1',
        'negative_binomial_v1',
        'form_adjusted_v1',
        'logistic_regression_v1'
    ]
    
    executing = [m['model_id'] for m in models]
    missing = [m for m in all_expected if m not in executing]
    
    if missing:
        print()
        print(f"NOT EXECUTING: {len(missing)} models")
        for m in missing:
            print(f"  ✗ {m}")
    
else:
    print('No prediction versions found in database')

conn.close()
