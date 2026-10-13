#!/usr/bin/env python3
"""
Test Over/Under market mathematical consistency and monotonicity.

This script validates:
1. Over + Under probabilities sum to 1.0 (with tolerance)
2. Monotonicity: P(Over X) >= P(Over Y) when X < Y
3. Consistency across different score distributions
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.prediction.market_derivation import MarketDerivationEngine
from typing import Dict, Tuple
import math


def test_probability_sum_consistency():
    """Test that Over + Under probabilities sum to 1.0 for each line."""
    print("Testing Over/Under probability sum consistency...")

    engine = MarketDerivationEngine()

    # Test with various score distributions
    test_cases = [
        # Low scoring game
        {(0, 0): 0.15, (1, 0): 0.25, (0, 1): 0.20, (1, 1): 0.30, (2, 0): 0.05, (0, 2): 0.05},

        # High scoring game
        {(2, 2): 0.20, (3, 1): 0.15, (1, 3): 0.15, (2, 3): 0.12, (3, 2): 0.12, (4, 1): 0.08, (1, 4): 0.08, (3, 3): 0.10},

        # Balanced game
        {(1, 1): 0.20, (2, 1): 0.15, (1, 2): 0.15, (0, 1): 0.10, (1, 0): 0.10, (2, 0): 0.08, (0, 2): 0.08, (2, 2): 0.14}
    ]

    tolerance = 1e-6
    all_passed = True

    for i, score_dist in enumerate(test_cases):
        print(f"\nTest case {i+1}: {score_dist}")

        try:
            markets = engine.derive(score_dist)

            for line, (over_prob, under_prob) in markets.over_under.items():
                prob_sum = over_prob + under_prob

                if abs(prob_sum - 1.0) > tolerance:
                    print(f"❌ FAIL: Line {line}: Over={over_prob:.6f} + Under={under_prob:.6f} = {prob_sum:.6f} (≠ 1.0)")
                    all_passed = False
                else:
                    print(f"✅ PASS: Line {line}: Over={over_prob:.6f} + Under={under_prob:.6f} = {prob_sum:.6f}")

        except Exception as e:
            print(f"❌ ERROR in test case {i+1}: {e}")
            all_passed = False

    return all_passed


def test_monotonicity():
    """Test that Over probabilities are monotonically decreasing as line increases."""
    print("\n" + "="*60)
    print("Testing Over/Under monotonicity...")

    engine = MarketDerivationEngine()

    # Test cases with different distributions
    test_cases = [
        # Even distribution
        {(0, 0): 0.1, (1, 0): 0.1, (0, 1): 0.1, (1, 1): 0.15, (2, 0): 0.1, (0, 2): 0.1,
         (2, 1): 0.1, (1, 2): 0.1, (2, 2): 0.1, (3, 0): 0.05},

        # High scoring tendency
        {(2, 2): 0.25, (3, 1): 0.15, (1, 3): 0.15, (3, 2): 0.12, (2, 3): 0.12, (4, 1): 0.10, (1, 4): 0.11}
    ]

    all_passed = True

    for i, score_dist in enumerate(test_cases):
        print(f"\nTest case {i+1}:")

        try:
            markets = engine.derive(score_dist)

            # Extract Over probabilities for each line
            lines = [0.5, 1.5, 2.5, 3.5]
            over_probs = [markets.over_under[line][0] for line in lines]

            print(f"Over probabilities: {[f'{p:.4f}' for p in over_probs]}")

            # Check monotonicity: Over(X) >= Over(Y) when X < Y
            monotonic = True
            for j in range(len(lines) - 1):
                if over_probs[j] < over_probs[j + 1]:
                    print(f"❌ FAIL: Over({lines[j]})={over_probs[j]:.4f} < Over({lines[j+1]})={over_probs[j+1]:.4f}")
                    monotonic = False
                    all_passed = False

            if monotonic:
                print("✅ PASS: Over probabilities are monotonically decreasing")

        except Exception as e:
            print(f"❌ ERROR: {e}")
            all_passed = False

    return all_passed


def test_btts_consistency():
    """Test BTTS probability consistency."""
    print("\n" + "="*60)
    print("Testing BTTS consistency...")

    engine = MarketDerivationEngine()

    # Test case where we can manually verify BTTS (normalized distribution)
    score_dist = {
        (0, 0): 0.10,  # BTTS No
        (1, 0): 0.15,  # BTTS No
        (0, 1): 0.15,  # BTTS No
        (1, 1): 0.20,  # BTTS Yes
        (2, 0): 0.10,  # BTTS No
        (0, 2): 0.10,  # BTTS No
        (2, 1): 0.10,  # BTTS Yes
        (1, 2): 0.10,  # BTTS Yes
    }
    # Total: 0.10+0.15+0.15+0.20+0.10+0.10+0.10+0.10 = 1.0
    # BTTS Yes: 0.20+0.10+0.10 = 0.40
    # BTTS No: 0.10+0.15+0.15+0.10+0.10 = 0.60

    print(f"Score distribution: {score_dist}")

    # Manual calculation
    btts_yes_manual = score_dist[(1,1)] + score_dist[(2,1)] + score_dist[(1,2)]  # 0.20+0.10+0.10 = 0.40
    btts_no_manual = 1.0 - btts_yes_manual  # 0.60

    print(f"Manual BTTS Yes: {btts_yes_manual:.3f}")
    print(f"Manual BTTS No: {btts_no_manual:.3f}")

    # Check if distribution sums to 1.0
    total_prob = sum(score_dist.values())
    print(f"Input distribution sum: {total_prob:.6f}")

    try:
        markets = engine.derive(score_dist)

        btts_sum = markets.btts_yes + markets.btts_no

        print(f"Engine BTTS Yes: {markets.btts_yes:.6f}")
        print(f"Engine BTTS No: {markets.btts_no:.6f}")
        print(f"Engine BTTS Sum: {btts_sum:.6f}")

        # Debug: check raw calculation before normalization
        print("\nDebug - Raw BTTS calculation:")
        btts_yes_raw = sum(prob for (h, a), prob in score_dist.items() if h > 0 and a > 0)
        btts_no_raw = sum(prob for (h, a), prob in score_dist.items() if h == 0 or a == 0)
        print(f"Raw BTTS Yes: {btts_yes_raw:.6f}")
        print(f"Raw BTTS No: {btts_no_raw:.6f}")
        print(f"Raw BTTS Sum: {btts_yes_raw + btts_no_raw:.6f}")

        tolerance = 1e-6

        # Check sum equals 1
        if abs(btts_sum - 1.0) > tolerance:
            print(f"❌ FAIL: BTTS probabilities sum to {btts_sum:.6f} (≠ 1.0)")
            return False

        # Check against manual calculation (should match raw calculation)
        if abs(markets.btts_yes - btts_yes_manual) > tolerance:
            print(f"❌ FAIL: Engine BTTS Yes {markets.btts_yes:.6f} ≠ Manual {btts_yes_manual:.6f}")
            print("ℹ️  This suggests normalization issue - engine doing extra normalization")
            return False

        print("✅ PASS: BTTS probabilities are consistent")
        return True

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


def test_edge_cases():
    """Test edge cases and boundary conditions."""
    print("\n" + "="*60)
    print("Testing edge cases...")

    engine = MarketDerivationEngine()

    test_cases = [
        # All probability on 0-0
        ("All 0-0", {(0, 0): 1.0}),

        # All probability on high score
        ("All 5-5", {(5, 5): 1.0}),

        # Exact boundary cases
        ("Boundary 1.5", {(0, 1): 0.3, (1, 0): 0.3, (1, 1): 0.4}),
    ]

    all_passed = True

    for name, score_dist in test_cases:
        print(f"\nTesting {name}: {score_dist}")

        try:
            markets = engine.derive(score_dist)

            # Check basic consistency
            for line, (over_prob, under_prob) in markets.over_under.items():
                if abs(over_prob + under_prob - 1.0) > 1e-6:
                    print(f"❌ FAIL {name}: Line {line} sum = {over_prob + under_prob:.6f}")
                    all_passed = False
                else:
                    print(f"✅ Line {line}: Over={over_prob:.3f}, Under={under_prob:.3f}")

        except Exception as e:
            print(f"❌ ERROR in {name}: {e}")
            all_passed = False

    return all_passed


def main():
    """Run all mathematical consistency tests."""
    print("Over/Under Market Mathematical Consistency Tests")
    print("=" * 60)

    tests = [
        ("Probability Sum", test_probability_sum_consistency),
        ("Monotonicity", test_monotonicity),
        ("BTTS Consistency", test_btts_consistency),
        ("Edge Cases", test_edge_cases),
    ]

    results = []

    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ CRITICAL ERROR in {test_name}: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All mathematical consistency tests PASSED!")
        return True
    else:
        print("⚠️  Some tests FAILED - market consistency issues detected!")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
