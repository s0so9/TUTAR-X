#!/usr/bin/env python3
"""
Analyze statistics display mapping from backend to frontend.
Check if Over/Under lines are correctly mapped and displayed.
"""

import sys
import os
import requests
import json
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from app.database import get_db
from app.database.models import Match
from app.prediction.service import PredictionService
from app.providers.fotmob import FotMobFootballProvider

def check_backend_prediction_output(match_id):
    """Check backend prediction output structure"""

    print("🔍 BACKEND PREDICTION OUTPUT ANALYSIS")
    print(f"   Match ID: {match_id}")
    print()

    session = next(get_db())
    try:
        match = session.query(Match).filter_by(id=match_id).first()
        if not match:
            print("❌ Match not found")
            return None

        provider = FotMobFootballProvider(base_url="https://www.fotmob.com")
        prediction_service = PredictionService(provider=provider, db_session=session)

        # Generate prediction
        print("   Generating prediction...")
        prediction_result = prediction_service.predict(match_id)

        if not prediction_result:
            print("❌ Prediction failed")
            return None

        print("✅ Prediction generated successfully")
        print()

        # Analyze prediction structure
        print("📊 PREDICTION STRUCTURE:")
        print(f"   Type: {type(prediction_result)}")

        if hasattr(prediction_result, '__dict__'):
            for key, value in prediction_result.__dict__.items():
                if key.startswith('_'):
                    continue
                print(f"   {key}: {type(value)} = {value}")

        print()

        # Check Over/Under markets specifically
        print("🎯 OVER/UNDER MARKETS:")
        if hasattr(prediction_result, 'markets') and prediction_result.markets:
            for market in prediction_result.markets:
                if hasattr(market, 'market_type') and 'over_under' in market.market_type.lower():
                    print(f"   Market: {market.market_type}")
                    if hasattr(market, 'line'):
                        print(f"     Line: {market.line}")
                    if hasattr(market, 'selections'):
                        for selection in market.selections:
                            print(f"     {selection.selection_type}: {selection.probability:.4f} ({selection.probability*100:.2f}%)")

        # Check if there's a poisson_result attribute
        if hasattr(prediction_result, 'poisson_result'):
            print()
            print("⚽ POISSON RESULT:")
            poisson = prediction_result.poisson_result
            if hasattr(poisson, 'over_under_probabilities'):
                print("   Over/Under probabilities:")
                for line, (over_prob, under_prob) in poisson.over_under_probabilities.items():
                    print(f"     Line {line}: Over={over_prob:.4f} ({over_prob*100:.2f}%), Under={under_prob:.4f} ({under_prob*100:.2f}%)")

        return prediction_result

    except Exception as e:
        print(f"❌ Error in backend prediction: {e}")
        return None
    finally:
        session.close()

def check_api_endpoint_response(match_id, port=8000):
    """Check API endpoint response for the same match"""

    print()
    print("🌐 API ENDPOINT RESPONSE ANALYSIS")
    print(f"   Match ID: {match_id}")
    print(f"   Port: {port}")
    print()

    try:
        # Test prediction endpoint
        url = f"http://localhost:{port}/api/v1/matches/{match_id}/prediction"
        print(f"   Requesting: {url}")

        response = requests.get(url, timeout=30)
        print(f"   Status: {response.status_code}")

        if response.status_code != 200:
            print(f"❌ API request failed: {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            return None

        prediction_data = response.json()
        print("✅ API response received")
        print()

        # Analyze API response structure
        print("📊 API RESPONSE STRUCTURE:")
        def analyze_dict(data, indent=0):
            prefix = "   " + "  " * indent
            for key, value in data.items():
                if isinstance(value, dict):
                    print(f"{prefix}{key}: (dict)")
                    analyze_dict(value, indent + 1)
                elif isinstance(value, list):
                    print(f"{prefix}{key}: (list, {len(value)} items)")
                    if len(value) > 0 and isinstance(value[0], dict):
                        print(f"{prefix}  Sample item:")
                        analyze_dict(value[0], indent + 2)
                else:
                    if isinstance(value, float):
                        print(f"{prefix}{key}: {value:.4f}")
                    else:
                        print(f"{prefix}{key}: {value}")

        analyze_dict(prediction_data)

        # Check Over/Under markets in API response
        print()
        print("🎯 OVER/UNDER IN API RESPONSE:")
        if 'markets' in prediction_data:
            over_under_found = False
            for market in prediction_data['markets']:
                if 'over_under' in market.get('market_type', '').lower():
                    over_under_found = True
                    print(f"   Market: {market.get('market_type')}")
                    print(f"     Line: {market.get('line')}")
                    if 'selections' in market:
                        for selection in market['selections']:
                            prob = selection.get('probability', 0)
                            print(f"     {selection.get('selection_type')}: {prob:.4f} ({prob*100:.2f}%)")

            if not over_under_found:
                print("   ❌ No Over/Under markets found in API response")
        else:
            print("   ❌ No 'markets' field in API response")

        return prediction_data

    except requests.exceptions.ConnectionError:
        print(f"❌ Connection failed to localhost:{port}")
        print("   Backend server may not be running")
        return None
    except Exception as e:
        print(f"❌ Error in API request: {e}")
        return None

def check_frontend_market_display():
    """Check frontend market display logic"""

    print()
    print("🎨 FRONTEND MARKET DISPLAY ANALYSIS")
    print()

    # Check if frontend files exist and analyze market display logic
    frontend_files = [
        'frontend/src/pages/MatchDetail.tsx',
        'frontend/src/components/PredictionDisplay.tsx',
        'frontend/src/utils/formatters.ts'
    ]

    for file_path in frontend_files:
        if os.path.exists(file_path):
            print(f"📄 Analyzing {file_path}:")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Look for Over/Under related code
                lines = content.split('\n')
                relevant_lines = []

                for i, line in enumerate(lines):
                    if any(keyword in line.lower() for keyword in ['over', 'under', 'line', 'market']):
                        relevant_lines.append((i+1, line.strip()))

                if relevant_lines:
                    print("   Over/Under related code:")
                    for line_num, line in relevant_lines[:10]:  # Show first 10 matches
                        print(f"     L{line_num}: {line[:80]}{'...' if len(line) > 80 else ''}")
                else:
                    print("   No Over/Under related code found")

            except Exception as e:
                print(f"   ❌ Error reading file: {e}")
        else:
            print(f"📄 {file_path}: Not found")
        print()

def compare_backend_vs_api(backend_result, api_result):
    """Compare backend prediction with API response"""

    print()
    print("🔍 BACKEND VS API COMPARISON")
    print()

    if not backend_result or not api_result:
        print("❌ Cannot compare - missing data")
        return

    # Compare Over/Under data specifically
    print("🎯 Over/Under Comparison:")

    # Extract from backend (poisson_result)
    backend_over_under = {}
    if hasattr(backend_result, 'poisson_result') and hasattr(backend_result.poisson_result, 'over_under_probabilities'):
        backend_over_under = backend_result.poisson_result.over_under_probabilities

    # Extract from API response
    api_over_under = {}
    if 'markets' in api_result:
        for market in api_result['markets']:
            if 'over_under' in market.get('market_type', '').lower():
                line = market.get('line')
                if line is not None and 'selections' in market:
                    over_prob = under_prob = None
                    for selection in market['selections']:
                        if 'over' in selection.get('selection_type', '').lower():
                            over_prob = selection.get('probability')
                        elif 'under' in selection.get('selection_type', '').lower():
                            under_prob = selection.get('probability')

                    if over_prob is not None and under_prob is not None:
                        api_over_under[line] = (over_prob, under_prob)

    # Compare the data
    print(f"   Backend Over/Under lines: {list(backend_over_under.keys())}")
    print(f"   API Over/Under lines: {list(api_over_under.keys())}")

    common_lines = set(backend_over_under.keys()) & set(api_over_under.keys())
    print(f"   Common lines: {list(common_lines)}")

    for line in sorted(common_lines):
        backend_over, backend_under = backend_over_under[line]
        api_over, api_under = api_over_under[line]

        over_diff = abs(backend_over - api_over)
        under_diff = abs(backend_under - api_under)

        print(f"   Line {line}:")
        print(f"     Backend: Over={backend_over:.4f}, Under={backend_under:.4f}")
        print(f"     API:     Over={api_over:.4f}, Under={api_under:.4f}")
        print(f"     Diff:    Over={over_diff:.6f}, Under={under_diff:.6f}")

        if over_diff > 0.001 or under_diff > 0.001:
            print(f"     ⚠️  Significant difference detected!")
        else:
            print(f"     ✅ Values match")

def main():
    print("=" * 70)
    print("STATISTICS DISPLAY MAPPING ANALYSIS")
    print("=" * 70)

    match_id = '849f5743-1f96-4ade-be4c-af1c5d3da039'

    # Check backend prediction output
    backend_result = check_backend_prediction_output(match_id)

    # Check API endpoint response
    api_result = check_api_endpoint_response(match_id)

    # Check frontend display logic
    check_frontend_market_display()

    # Compare backend vs API
    compare_backend_vs_api(backend_result, api_result)

    print()
    print("=" * 50)
    print("SUMMARY")
    print("=" * 50)

    if backend_result:
        print("✅ Backend prediction generation: SUCCESS")
    else:
        print("❌ Backend prediction generation: FAILED")

    if api_result:
        print("✅ API endpoint response: SUCCESS")
    else:
        print("❌ API endpoint response: FAILED")

    print()
    print("🔍 Key findings will be displayed above in the detailed analysis.")

if __name__ == "__main__":
    main()
