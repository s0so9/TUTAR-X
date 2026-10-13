#!/usr/bin/env python3
"""Debug why team strengths are 0.0 despite sufficient historical data."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.api.dependencies import get_data_provider, get_db
from app.features.match_features import MatchFeatureExtractor

def debug_team_strengths():
    """Debug team strength calculation."""
    print("=== TEAM STRENGTH DEBUG ===\n")

    # Get provider and database
    provider_gen = get_data_provider()
    provider = next(provider_gen)

    db_gen = get_db()
    db_session = next(db_gen)

    try:
        # Get the target match
        target_match_id = "849f5743-1f96-4ade-be4c-af1c5d3da039"
        match = provider.get_match(target_match_id)

        # Create feature extractor
        extractor = MatchFeatureExtractor(
            provider=provider,
            db_session=db_session,
            min_matches=3
        )

        # Build context and check team strengths
        context = extractor._build_match_context(match)

        # Get historical matches
        home_matches = context.home_team_history.get_finished_matches()
        away_matches = context.away_team_history.get_finished_matches()

        print(f"Historical match counts:")
        print(f"  Home: {len(home_matches)} matches")
        print(f"  Away: {len(away_matches)} matches")

        # Check individual match scores and statuses
        print(f"\nDetailed home team match analysis:")
        goals_scored = []
        goals_conceded = []

        for i, match in enumerate(home_matches[:5]):
            is_home = (match.home_team_id == "9825")  # Arsenal's provider ID

            if match.home_score is not None and match.away_score is not None:
                if is_home:
                    scored = match.home_score
                    conceded = match.away_score
                else:
                    scored = match.away_score
                    conceded = match.home_score

                goals_scored.append(scored)
                goals_conceded.append(conceded)

                print(f"  {i+1}. {match.scheduled_at} | Status: {match.status}")
                print(f"      Arsenal {'home' if is_home else 'away'}: Scored {scored}, Conceded {conceded}")
                print(f"      Full score: {match.home_score}-{match.away_score}")
            else:
                print(f"  {i+1}. {match.scheduled_at} | Status: {match.status}")
                print(f"      NO SCORE DATA: home_score={match.home_score}, away_score={match.away_score}")

        if goals_scored:
            avg_scored = sum(goals_scored) / len(goals_scored)
            avg_conceded = sum(goals_conceded) / len(goals_conceded)
            print(f"\nCalculated averages (manual):")
            print(f"  Goals scored per match: {avg_scored:.2f}")
            print(f"  Goals conceded per match: {avg_conceded:.2f}")

        # Test strength calculator directly
        print(f"\nTesting strength calculator...")
        strength_features = extractor.strength_calculator.calculate(context)

        print(f"Strength calculator results:")
        print(f"  home_attack_strength: {strength_features.get('home_attack_strength')}")
        print(f"  home_defense_strength: {strength_features.get('home_defense_strength')}")
        print(f"  away_attack_strength: {strength_features.get('away_attack_strength')}")
        print(f"  away_defense_strength: {strength_features.get('away_defense_strength')}")

        # Check if matches have proper status
        finished_home = [m for m in home_matches if str(m.status) == 'MatchStatus.FINISHED']
        print(f"\nStatus verification:")
        print(f"  Total home matches: {len(home_matches)}")
        print(f"  Properly finished home matches: {len(finished_home)}")

        if finished_home:
            print(f"  Sample finished match: {finished_home[0].id} | {finished_home[0].status}")

        return {
            'home_matches': len(home_matches),
            'away_matches': len(away_matches),
            'finished_home': len(finished_home),
            'goals_data_available': bool(goals_scored),
            'avg_goals_scored': avg_scored if goals_scored else None,
            'strength_features': strength_features
        }

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        db_session.close()
        try:
            next(provider_gen)
        except StopIteration:
            pass

if __name__ == "__main__":
    debug_team_strengths()
