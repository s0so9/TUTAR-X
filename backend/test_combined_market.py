#!/usr/bin/env python3
"""
Test 2.5 Üst + KG Var (Over 2.5 + BTTS Yes) combined market implementation.

This script validates:
1. Combined market calculation is mathematically correct
2. Combined probability matches manual calculation from score distribution
3. Combined market probability <= min(Over 2.5, BTTS Yes) (logical constraint)
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.prediction.market_derivation import MarketDerivationEngine


def test_combined_market_manual_verification():
    """Test combined market against manual calculation."""
    print("Testing Over 2.5 + BTTS Yes combined market...")

    engine = MarketDerivationEngine()

    # Test case with known score distribution
    score_dist = {
        # Winning combined market scores (total >= 3 AND both score)
        (2, 1): 0.15,  # ✅ Combined: total=3, both score
        (1, 2): 0.15,  # ✅ Combined: total=3, both score
        (2, 2): 0.10,  # ✅ Combined: total=4, both score
        (3, 1): 0.08,  # ✅ Combined: total=4, both score
        (1, 3): 0.08,  # ✅ Combined: total=4, both score

        # Losing combined market scores
        (0, 0): 0.05,  # ❌ Combined: total=0, neither score
        (1, 0): 0.10,  # ❌ Combined: total=1, only home scores
        (0, 1): 0.10,  # ❌ Combined: total=1, only away scores
        (1, 1): 0.12,  # ❌ Combined: total=2 < 3
        (2, 0): 0.04,  # ❌ Combined: total=2 < 3
        (0, 2): 0.03,  # ❌ Combined: total=2 < 3
    }

    print(f"Score distribution: {score_dist}")
    print(f"Distribution sum: {sum(score_dist.values()):.6f}")

    # Manual calculations
    combined_manual = score_dist[(2,1)] + score_dist[(1,2)] + score_dist[(2,2)] + score_dist[(3,1)] + score_dist[(1,3)]

    over_2_5_manual = sum(prob for (h, a), prob in score_dist.items() if h + a >= 3)
    btts_yes_manual = sum(prob for (h, a), prob in score_dist.items() if h > 0 and a > 0)

    print(f"\nManual calculations:")
    print(f"Combined (Over 2.5 + BTTS): {combined_manual:.6f}")
    print(f"Over 2.5: {over_2_5_manual:.6f}")
    print(f"BTTS Yes: {btts_yes_manual:.6f}")

    # Engine calculations
    try:
        markets = engine.derive(score_dist)

        print(f"\nEngine calculations:")
        print(f"Combined (Over 2.5 + BTTS): {markets.over_2_5_and_btts_yes:.6f}")
        print(f"Over 2.5: {markets.over_under[2.5][0]:.6f}")  # over_prob
        print(f"BTTS Yes: {markets.btts_yes:.6f}")

        # Validation checks
        tolerance = 1e-6

        # 1. Combined matches manual calculation
        if abs(markets.over_2_5_and_btts_yes - combined_manual) > tolerance:
            print(f"❌ FAIL: Combined market {markets.over_2_5_and_btts_yes:.6f} ≠ Manual {combined_manual:.6f}")
            return False

        # 2. Combined <= Over 2.5 (logical constraint)
        if markets.over_2_5_and_btts_yes > markets.over_under[2.5][0] + tolerance:
            print(f"❌ FAIL: Combined {markets.over_2_5_and_btts_yes:.6f} > Over 2.5 {markets.over_under[2.5][0]:.6f}")
            return False

        # 3. Combined <= BTTS Yes (logical constraint)
        if markets.over_2_5_and_btts_yes > markets.btts_yes + tolerance:
            print(f"❌ FAIL: Combined {markets.over_2_5_and_btts_yes:.6f} > BTTS Yes {markets.btts_yes:.6f}")
            return False

        print("✅ PASS: All combined market validations successful")

        # Show the relationships
        print(f"\nLogical constraints verified:")
        print(f"Combined ≤ Over 2.5: {markets.over_2_5_and_btts_yes:.6f} ≤ {markets.over_under[2.5][0]:.6f} ✓")
        print(f"Combined ≤ BTTS Yes: {markets.over_2_5_and_btts_yes:.6f} ≤ {markets.btts_yes:.6f} ✓")

        return True

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


def test_combined_market_edge_cases():
    """Test combined market with edge case distributions."""
    print("\n" + "="*60)
    print("Testing combined market edge cases...")

    engine = MarketDerivationEngine()

    test_cases = [
        # All probability on non-combined outcome
        ("All 1-1", {(1, 1): 1.0}),  # Total < 3, combined = 0

        # All probability on combined outcome
        ("All 2-1", {(2, 1): 1.0}),  # Total >= 3 AND both score, combined = 1

        # Mixed case
        ("Mixed", {(0, 0): 0.2, (1, 1): 0.3, (2, 1): 0.25, (1, 2): 0.25}),
    ]

    all_passed = True

    for name, score_dist in test_cases:
        print(f"\nTesting {name}: {score_dist}")

        try:
            markets = engine.derive(score_dist)

            # Manual calculation
            combined_manual = sum(
                prob for (h, a), prob in score_dist.items()
                if h + a >= 3 and h > 0 and a > 0
            )

            if abs(markets.over_2_5_and_btts_yes - combined_manual) > 1e-6:
                print(f"❌ FAIL {name}: Engine {markets.over_2_5_and_btts_yes:.6f} ≠ Manual {combined_manual:.6f}")
                all_passed = False
            else:
                print(f"✅ PASS {name}: Combined = {markets.over_2_5_and_btts_yes:.6f}")

        except Exception as e:
            print(f"❌ ERROR in {name}: {e}")
            all_passed = False

    return all_passed


def test_combined_market_mathematical_relationships():
    """Test mathematical relationships of combined market."""
    print("\n" + "="*60)
    print("Testing combined market mathematical relationships...")

    engine = MarketDerivationEngine()

    # Realistic football score distribution
    score_dist = {
        (0, 0): 0.08, (1, 0): 0.12, (0, 1): 0.10, (2, 0): 0.06, (0, 2): 0.05,
        (1, 1): 0.15, (2, 1): 0.12, (1, 2): 0.10, (3, 0): 0.03, (0, 3): 0.02,
        (2, 2): 0.08, (3, 1): 0.04, (1, 3): 0.03, (3, 2): 0.02, (2, 3): 0.02
    }

    print(f"Realistic distribution sum: {sum(score_dist.values()):.3f}")

    try:
        markets = engine.derive(score_dist)

        print(f"\nMarket probabilities:")
        print(f"Over 2.5: {markets.over_under[2.5][0]:.4f}")
        print(f"BTTS Yes: {markets.btts_yes:.4f}")
        print(f"Combined (Over 2.5 + BTTS): {markets.over_2_5_and_btts_yes:.4f}")

        # Mathematical relationships
        over_2_5_prob = markets.over_under[2.5][0]
        btts_yes_prob = markets.btts_yes
        combined_prob = markets.over_2_5_and_btts_yes

        # Test: Combined = P(Over 2.5 AND BTTS Yes)
        # P(A ∩ B) ≤ min(P(A), P(B))
        min_individual = min(over_2_5_prob, btts_yes_prob)

        print(f"\nMathematical relationships:")
        print(f"Combined ≤ min(Over 2.5, BTTS): {combined_prob:.4f} ≤ {min_individual:.4f} = {combined_prob <= min_individual + 1e-6}")

        # If we assume independence: P(A ∩ B) = P(A) × P(B)
        # But Over 2.5 and BTTS are NOT independent, so this is just for comparison
        independence_prob = over_2_5_prob * btts_yes_prob
        print(f"Independence assumption (≠ reality): {independence_prob:.4f}")
        print(f"Actual combined: {combined_prob:.4f}")
        print(f"Dependency factor: {combined_prob / independence_prob:.2f}x independence" if independence_prob > 0 else "N/A")

        if combined_prob <= min_individual + 1e-6:
            print("✅ PASS: Mathematical relationships are valid")
            return True
        else:
            print("❌ FAIL: Combined probability exceeds logical maximum")
            return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


def main():
    """Run all combined market tests."""
    print("Over 2.5 + BTTS Yes Combined Market Tests")
    print("=" * 60)

    tests = [
        ("Manual Verification", test_combined_market_manual_verification),
        ("Edge Cases", test_combined_market_edge_cases),
        ("Mathematical Relationships", test_combined_market_mathematical_relationships),
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
        print("🎉 All combined market tests PASSED!")
        print("✅ Over 2.5 + BTTS Yes market is ready for production!")
        return True
    else:
        print("⚠️  Some tests FAILED - combined market needs fixes!")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
