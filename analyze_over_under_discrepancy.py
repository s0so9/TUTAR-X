#!/usr/bin/env python3
"""
Investigate Over/Under calculation discrepancies for Arsenal-Leeds match.
Check why model Over 2.5: 84.16% vs manual: 78.04% (6.12% difference)
"""

import numpy as np
from scipy.stats import poisson
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def calculate_over_under_detailed(home_lambda, away_lambda, line, max_goals=15):
    """Calculate Over/Under probabilities with detailed breakdown"""

    print(f"🎯 OVER/UNDER {line} ANALYSIS")
    print(f"   Home Lambda: {home_lambda}")
    print(f"   Away Lambda: {away_lambda}")
    print()

    over_prob = 0.0
    under_prob = 0.0
    exact_prob = 0.0

    # Store all score probabilities for analysis
    scores_under = []
    scores_over = []
    scores_exact = []

    total_probability = 0.0

    for home_goals in range(max_goals + 1):
        for away_goals in range(max_goals + 1):
            home_prob = poisson.pmf(home_goals, home_lambda)
            away_prob = poisson.pmf(away_goals, away_lambda)
            score_prob = home_prob * away_prob
            total_goals = home_goals + away_goals

            total_probability += score_prob

            if total_goals > line:
                over_prob += score_prob
                if score_prob > 0.001:  # Only store significant probabilities
                    scores_over.append((home_goals, away_goals, score_prob))
            elif total_goals < line:
                under_prob += score_prob
                if score_prob > 0.001:
                    scores_under.append((home_goals, away_goals, score_prob))
            else:
                exact_prob += score_prob
                if score_prob > 0.001:
                    scores_exact.append((home_goals, away_goals, score_prob))

    print(f"📊 DETAILED BREAKDOWN:")
    print(f"   Total probability calculated: {total_probability:.6f}")
    print()

    print(f"📈 UNDER {line} scores (showing > 0.1%):")
    under_sum = 0.0
    for home, away, prob in sorted(scores_under, key=lambda x: x[2], reverse=True):
        if prob > 0.001:
            print(f"   {home}-{away}: {prob:.4f} ({prob*100:.2f}%) [Total: {home+away}]")
            under_sum += prob
    print(f"   Under {line} subtotal: {under_sum:.6f} ({under_sum*100:.2f}%)")
    print()

    if scores_exact:
        print(f"📊 EXACTLY {line} scores:")
        exact_sum = 0.0
        for home, away, prob in sorted(scores_exact, key=lambda x: x[2], reverse=True):
            print(f"   {home}-{away}: {prob:.4f} ({prob*100:.2f}%) [Total: {home+away}]")
            exact_sum += prob
        print(f"   Exactly {line} subtotal: {exact_sum:.6f} ({exact_sum*100:.2f}%)")
        print()

    print(f"📈 OVER {line} scores (showing > 0.1%):")
    over_sum = 0.0
    for home, away, prob in sorted(scores_over, key=lambda x: x[2], reverse=True):
        if prob > 0.001:
            print(f"   {home}-{away}: {prob:.4f} ({prob*100:.2f}%) [Total: {home+away}]")
            over_sum += prob
    print(f"   Over {line} subtotal: {over_sum:.6f} ({over_sum*100:.2f}%)")
    print()

    print(f"🧮 FINAL CALCULATION:")
    print(f"   Over {line}:     {over_prob:.6f} ({over_prob*100:.2f}%)")
    print(f"   Exactly {line}: {exact_prob:.6f} ({exact_prob*100:.2f}%)")
    print(f"   Under {line}:    {under_prob:.6f} ({under_prob*100:.2f}%)")
    print(f"   Total:          {over_prob + exact_prob + under_prob:.6f}")

    return over_prob, under_prob, exact_prob

def compare_with_model_output():
    """Compare with the model's reported values"""

    print("=" * 70)
    print("COMPARISON WITH MODEL OUTPUT")
    print("=" * 70)

    # Model reported values from baseline test
    model_over_2_5 = 0.841610
    model_under_2_5 = 0.158326

    # Manual calculation from baseline test (incomplete)
    manual_over_2_5 = 0.780446
    manual_under_2_5 = 0.158326
    manual_total = 0.938772

    print(f"Model values:")
    print(f"   Over 2.5:  {model_over_2_5:.6f} ({model_over_2_5*100:.2f}%)")
    print(f"   Under 2.5: {model_under_2_5:.6f} ({model_under_2_5*100:.2f}%)")
    print(f"   Total:     {model_over_2_5 + model_under_2_5:.6f}")
    print()

    print(f"Manual calculation (from baseline test):")
    print(f"   Over 2.5:  {manual_over_2_5:.6f} ({manual_over_2_5*100:.2f}%)")
    print(f"   Under 2.5: {manual_under_2_5:.6f} ({manual_under_2_5*100:.2f}%)")
    print(f"   Total:     {manual_total:.6f} ({manual_total*100:.2f}%)")
    print(f"   Missing:   {1.0 - manual_total:.6f} ({(1.0 - manual_total)*100:.2f}%)")
    print()

def main():
    print("=" * 70)
    print("ARSENAL-LEEDS OVER/UNDER DISCREPANCY ANALYSIS")
    print("=" * 70)

    # Values from baseline test
    arsenal_lambda = 2.308
    leeds_lambda = 2.333

    compare_with_model_output()

    print()
    print("🔍 RECALCULATING WITH HIGHER PRECISION...")
    print()

    # Calculate Over/Under 2.5 with detailed breakdown
    over_prob, under_prob, exact_prob = calculate_over_under_detailed(
        arsenal_lambda, leeds_lambda, 2.5, max_goals=20
    )

    print()
    print("=" * 50)
    print("DISCREPANCY ANALYSIS")
    print("=" * 50)

    model_over_2_5 = 0.841610
    model_under_2_5 = 0.158326

    over_diff = abs(model_over_2_5 - over_prob)
    under_diff = abs(model_under_2_5 - under_prob)

    print(f"Comparison with model:")
    print(f"   Over difference:  {over_diff:.6f} ({over_diff*100:.3f}%)")
    print(f"   Under difference: {under_diff:.6f} ({under_diff*100:.3f}%)")
    print()

    if over_diff < 0.001 and under_diff < 0.001:
        print("✅ CONCLUSION: Calculations are consistent (< 0.1%)")
        print("   The original manual calculation was incomplete.")
    elif over_diff < 0.01 and under_diff < 0.01:
        print("⚠️  CONCLUSION: Minor discrepancies (< 1.0%)")
        print("   Likely due to precision or incomplete calculation.")
    else:
        print("❌ CONCLUSION: Significant discrepancies found")
        print("   Need to investigate calculation methodology.")

if __name__ == "__main__":
    main()
