#!/usr/bin/env python
"""Debug TeamStrengthCalculator directly with minimal context."""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.database import get_db
from app.api.dependencies import get_data_provider
from app.features.team_strength import TeamStrengthCalculator
from app.features.form import FormCalculator
from app.features.base import TeamHistoricalData, MatchContext

def main():
    print("=== TEAM STRENGTH DEBUG ===")

    # Create minimal context (empty matches)
    home_history = TeamHistoricalData(
        team_id="9d09f9ec-8208-4dcb-88c7-8520ab51c9b5",
        matches=[],  # Empty - should trigger fallback
        standings=None
    )

    away_history = TeamHistoricalData(
        team_id="b3bd533f-69df-49e9-89fd-133e022ad65f",
        matches=[],  # Empty - should trigger fallback
        standings=None
    )

    context = MatchContext(
        match_id="a57adb1d-c6f8-404f-b085-98bfc584e3ee",
        home_team_id="9d09f9ec-8208-4dcb-88c7-8520ab51c9b5",
        away_team_id="b3bd533f-69df-49e9-89fd-133e022ad65f",
        scheduled_at=None,
        competition_id="c2744bd9-5915-440c-98db-97167177a9bb",
        season_id="unknown",
        home_team_history=home_history,
        away_team_history=away_history
    )

    # Test TeamStrengthCalculator
    print("\n--- TeamStrengthCalculator ---")
    strength_calc = TeamStrengthCalculator(min_matches=1)
    strength_features = strength_calc.calculate(context)

    print("Strength features:")
    for key, value in strength_features.items():
        print(f"  {key}: {value}")

    # Test FormCalculator
    print("\n--- FormCalculator ---")
    form_calc = FormCalculator(recent_matches=5, min_matches=1)  # Same min_matches as PredictionService
    form_features = form_calc.calculate(context)

    print("Form features:")
    for key, value in form_features.items():
        print(f"  {key}: {value}")

    # Combine features (same as MatchFeatureExtractor)
    print("\n--- Combined Features ---")
    combined_features = {}
    combined_features.update(strength_features)
    combined_features.update(form_features)

    target_features = [
        'home_goals_scored_avg', 'away_goals_scored_avg',
        'home_goals_conceded_avg', 'away_goals_conceded_avg'
    ]

    print("Target features:")
    for feat in target_features:
        value = combined_features.get(feat)
        print(f"  {feat}: {value}")

    print("\n--- Analysis ---")
    print(f"Total strength features: {len(strength_features)}")
    print(f"Total form features: {len(form_features)}")
    print(f"Total combined features: {len(combined_features)}")

    # Check if FormCalculator overwrites TeamStrengthCalculator
    strength_goals_scored = strength_features.get('home_goals_scored_avg')
    form_goals_scored = form_features.get('home_goals_scored_avg')
    final_goals_scored = combined_features.get('home_goals_scored_avg')

    print(f"Home goals scored avg:")
    print(f"  From TeamStrengthCalculator: {strength_goals_scored}")
    print(f"  From FormCalculator: {form_goals_scored}")
    print(f"  Final combined value: {final_goals_scored}")

if __name__ == "__main__":
    main()
