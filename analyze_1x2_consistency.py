#!/usr/bin/env python3
"""
Analyze 1X2 vs predicted score consistency for Arsenal-Leeds match.
Check if Poisson distribution calculations are mathematically correct.
"""

import numpy as np
from scipy.stats import poisson
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def calculate_1x2_from_lambdas(home_lambda, away_lambda, max_goals=10):
    """Calculate 1X2 probabilities from Poisson lambdas"""

    print(f"📊 CALCULATING 1X2 FROM LAMBDAS")
    print(f"   Home Lambda: {home_lambda}")
    print(f"   Away Lambda: {away_lambda}")
    print()

    home_win_prob = 0.0
    draw_prob = 0.0
    away_win_prob = 0.0

    print("Score probabilities:")
    for home_goals in range(max_goals + 1):
        for away_goals in range(max_goals + 1):
            home_prob = poisson.pmf(home_goals, home_lambda)
            away_prob = poisson.pmf(away_goals, away_lambda)
            score_prob = home_prob * away_prob

            if score_prob > 0.005:  # Only show significant probabilities
                print(f"   {home_goals}-{away_goals}: {score_prob:.4f} ({score_prob*100:.2f}%)")

            if home_goals > away_goals:
                home_win_prob += score_prob
            elif home_goals == away_goals:
                draw_prob += score_prob
            else:
                away_win_prob += score_prob

    print()
    print(f"📈 CALCULATED 1X2:")
    print(f"   Home Win: {home_win_prob:.6f} ({home_win_prob*100:.2f}%)")
    print(f"   Draw:     {draw_prob:.6f} ({draw_prob*100:.2f}%)")
    print(f"   Away Win: {away_win_prob:.6f} ({away_win_prob*100:.2f}%)")
    print(f"   Total:    {home_win_prob + draw_prob + away_win_prob:.6f}")

    return home_win_prob, draw_prob, away_win_prob

def calculate_expected_score(home_lambda, away_lambda):
    """Calculate most likely exact score and expected total goals"""

    print(f"⚽ EXPECTED SCORE ANALYSIS:")

    # Most likely exact score
    most_likely_home = int(round(home_lambda))
    most_likely_away = int(round(away_lambda))

    home_prob = poisson.pmf(most_likely_home, home_lambda)
    away_prob = poisson.pmf(most_likely_away, away_lambda)
    most_likely_prob = home_prob * away_prob

    print(f"   Most likely score: {most_likely_home}-{most_likely_away}")
    print(f"   Probability: {most_likely_prob:.4f} ({most_likely_prob*100:.2f}%)")
    print()

    # Expected total goals
    expected_total = home_lambda + away_lambda
    print(f"   Expected total goals: {expected_total:.3f}")
    print(f"   Home expected: {home_lambda:.3f}")
    print(f"   Away expected: {away_lambda:.3f}")

    return most_likely_home, most_likely_away, expected_total

def main():
    print("=" * 70)
    print("ARSENAL-LEEDS 1X2 CONSISTENCY ANALYSIS")
    print("=" * 70)

    # Values from the baseline test
    arsenal_lambda = 2.308
    leeds_lambda = 2.333

    # Model's reported 1X2 values
    model_home = 0.400
    model_draw = 0.191
    model_away = 0.409

    print(f"🔍 MODEL REPORTED VALUES:")
    print(f"   1X2: H={model_home:.3f}, D={model_draw:.3f}, A={model_away:.3f}")
    print(f"   Total: {model_home + model_draw + model_away:.3f}")
    print()

    # Calculate 1X2 from scratch
    calc_home, calc_draw, calc_away = calculate_1x2_from_lambdas(arsenal_lambda, leeds_lambda)

    print()
    print("=" * 50)
    print("CONSISTENCY CHECK")
    print("=" * 50)

    # Compare values
    home_diff = abs(model_home - calc_home)
    draw_diff = abs(model_draw - calc_draw)
    away_diff = abs(model_away - calc_away)

    print(f"Differences (Model vs Calculated):")
    print(f"   Home: {home_diff:.6f} ({home_diff*100:.3f}%)")
    print(f"   Draw: {draw_diff:.6f} ({draw_diff*100:.3f}%)")
    print(f"   Away: {away_diff:.6f} ({away_diff*100:.3f}%)")

    max_diff = max(home_diff, draw_diff, away_diff)
    print(f"   Max difference: {max_diff:.6f} ({max_diff*100:.3f}%)")

    if max_diff < 0.001:
        print("✅ CONSISTENCY: Excellent (< 0.1%)")
    elif max_diff < 0.01:
        print("⚠️  CONSISTENCY: Good (< 1.0%)")
    elif max_diff < 0.05:
        print("⚠️  CONSISTENCY: Moderate (< 5.0%)")
    else:
        print("❌ CONSISTENCY: Poor (> 5.0%)")

    print()
    calculate_expected_score(arsenal_lambda, leeds_lambda)

if __name__ == "__main__":
    main()
