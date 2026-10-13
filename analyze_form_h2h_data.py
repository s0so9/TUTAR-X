#!/usr/bin/env python3
"""
Analyze form and head-to-head data accuracy for Arsenal-Leeds match.
Check data quality and min_sample_size=3 requirement compliance.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from app.database import get_db
from app.database.models import Match, Team
from app.providers.fotmob import FotMobFootballProvider
from app.prediction.service import PredictionService
from sqlalchemy.orm import sessionmaker
from sqlalchemy import desc
from datetime import datetime

def analyze_team_historical_data(session, team_id, team_name, reference_date, min_sample_size=3):
    """Analyze historical match data for a team"""

    print(f"📊 ANALYZING {team_name.upper()} HISTORICAL DATA")
    print(f"   Team ID: {team_id}")
    print(f"   Reference Date: {reference_date}")
    print(f"   Min Sample Size Required: {min_sample_size}")
    print()

    # Get all finished matches for this team before reference date
    all_matches = session.query(Match).filter(
        (Match.home_team_id == team_id) | (Match.away_team_id == team_id),
        Match.scheduled_at < reference_date,
        Match.status == 'FINISHED'
    ).order_by(desc(Match.scheduled_at)).all()

    print(f"   Total finished matches found: {len(all_matches)}")

    if len(all_matches) == 0:
        print("   ❌ No historical data available")
        return None

    # Show recent matches
    print(f"   Recent matches (last 10):")
    recent_matches = all_matches[:10]

    for i, match in enumerate(recent_matches):
        # Get opponent info more safely
        try:
            home_team = session.query(Team).filter_by(id=match.home_team_id).first()
            away_team = session.query(Team).filter_by(id=match.away_team_id).first()

            if match.home_team_id == team_id:
                opponent = away_team.name if away_team else f"Team-{match.away_team_id[:8]}"
                result = f"{match.home_score}-{match.away_score}" if match.home_score is not None else "N/A"
                venue = "H"
            else:
                opponent = home_team.name if home_team else f"Team-{match.home_team_id[:8]}"
                result = f"{match.away_score}-{match.home_score}" if match.away_score is not None else "N/A"
                venue = "A"
        except Exception:
            opponent = "Unknown"
            result = "N/A"
            venue = "?"

        print(f"     {i+1:2d}. {match.scheduled_at.strftime('%Y-%m-%d')} vs {opponent:<20} ({venue}) {result}")

    print()

    # Check min_sample_size compliance
    meets_requirement = len(all_matches) >= min_sample_size
    status = "✅" if meets_requirement else "❌"
    print(f"   {status} Min sample size ({min_sample_size}): {'MET' if meets_requirement else 'NOT MET'}")
    print(f"   Available: {len(all_matches)} matches")

    if not meets_requirement:
        print(f"   ⚠️  INSUFFICIENT DATA: Need {min_sample_size - len(all_matches)} more matches")

    return {
        'team_id': team_id,
        'team_name': team_name,
        'total_matches': len(all_matches),
        'meets_min_sample': meets_requirement,
        'recent_matches': recent_matches
    }

def analyze_head_to_head_data(session, home_team_id, away_team_id, home_name, away_name, reference_date):
    """Analyze head-to-head historical data"""

    print(f"🤝 HEAD-TO-HEAD ANALYSIS: {home_name} vs {away_name}")
    print(f"   Home Team ID: {home_team_id}")
    print(f"   Away Team ID: {away_team_id}")
    print(f"   Reference Date: {reference_date}")
    print()

    # Get head-to-head matches
    h2h_matches = session.query(Match).filter(
        ((Match.home_team_id == home_team_id) & (Match.away_team_id == away_team_id)) |
        ((Match.home_team_id == away_team_id) & (Match.away_team_id == home_team_id)),
        Match.scheduled_at < reference_date,
        Match.status == 'FINISHED'
    ).order_by(desc(Match.scheduled_at)).all()

    print(f"   Total H2H matches found: {len(h2h_matches)}")

    if len(h2h_matches) == 0:
        print("   ❌ No head-to-head data available")
        return None

    # Analyze H2H results
    home_wins = 0
    away_wins = 0
    draws = 0

    print(f"   Recent H2H matches:")
    for i, match in enumerate(h2h_matches):
        if match.home_team_id == home_team_id:
            # Home team is the same as our reference home team
            result_display = f"{match.home_score}-{match.away_score}"
            if match.home_score > match.away_score:
                result = f"{home_name} Win"
                home_wins += 1
            elif match.home_score < match.away_score:
                result = f"{away_name} Win"
                away_wins += 1
            else:
                result = "Draw"
                draws += 1
        else:
            # Teams are swapped
            result_display = f"{match.away_score}-{match.home_score}"
            if match.away_score > match.home_score:
                result = f"{home_name} Win"
                home_wins += 1
            elif match.away_score < match.home_score:
                result = f"{away_name} Win"
                away_wins += 1
            else:
                result = "Draw"
                draws += 1

        print(f"     {i+1:2d}. {match.scheduled_at.strftime('%Y-%m-%d')} {result_display} - {result}")

    print()
    print(f"   H2H Summary:")
    print(f"     {home_name} wins: {home_wins}")
    print(f"     {away_name} wins: {away_wins}")
    print(f"     Draws: {draws}")
    print(f"     Total: {len(h2h_matches)} matches")

    return {
        'total_h2h_matches': len(h2h_matches),
        'home_wins': home_wins,
        'away_wins': away_wins,
        'draws': draws,
        'recent_matches': h2h_matches
    }

def check_feature_extraction_quality(session, match_id):
    """Check the quality of feature extraction with current data"""

    print(f"🔍 FEATURE EXTRACTION QUALITY CHECK")
    print(f"   Match ID: {match_id}")
    print()

    # Get the match
    match = session.query(Match).filter_by(id=match_id).first()
    if not match:
        print("❌ Match not found")
        return None

    # Initialize prediction service
    provider = FotMobFootballProvider(base_url="https://www.fotmob.com")
    prediction_service = PredictionService(provider=provider, db_session=session)

    try:
        # Extract features
        features = prediction_service.feature_extractor.extract_features(match)

        print("   Extracted features:")
        key_features = [
            'home_attack_strength', 'away_attack_strength',
            'home_defense_strength', 'away_defense_strength',
            'home_form_score', 'away_form_score',
            'h2h_home_advantage', 'home_recent_goals_scored',
            'away_recent_goals_scored', 'home_recent_goals_conceded',
            'away_recent_goals_conceded'
        ]

        missing_features = []
        for feature_name in key_features:
            value = features.get(feature_name)
            if value is not None:
                print(f"     ✅ {feature_name}: {value}")
            else:
                print(f"     ❌ {feature_name}: MISSING")
                missing_features.append(feature_name)

        print()
        if missing_features:
            print(f"   ⚠️  Missing {len(missing_features)} key features:")
            for feature in missing_features:
                print(f"     - {feature}")
        else:
            print("   ✅ All key features available")

        return {
            'total_features': len(features),
            'key_features_available': len(key_features) - len(missing_features),
            'key_features_total': len(key_features),
            'missing_features': missing_features,
            'features': features
        }

    except Exception as e:
        print(f"   ❌ Feature extraction failed: {e}")
        return None

def main():
    print("=" * 70)
    print("ARSENAL-LEEDS FORM/H2H DATA ACCURACY ANALYSIS")
    print("=" * 70)

    # Arsenal-Leeds match details
    match_id = '849f5743-1f96-4ade-be4c-af1c5d3da039'
    arsenal_team_id = 'd749d5ee-b8e6-4042-92b1-b5d8f2a3910f'
    leeds_team_id = 'e12af9d8-f085-4525-a381-dc990fc4ee61'
    reference_date = datetime(2026, 10, 10, 11, 30, 0)

    session = next(get_db())
    try:
        # Get team names
        try:
            arsenal = session.query(Team).filter_by(id=arsenal_team_id).first()
            leeds = session.query(Team).filter_by(id=leeds_team_id).first()

            arsenal_name = arsenal.name if arsenal else "Arsenal"
            leeds_name = leeds.name if leeds else "Leeds"
        except Exception as e:
            print(f"⚠️  Could not fetch team names from database: {e}")
            arsenal_name = "Arsenal"
            leeds_name = "Leeds"

        print(f"🏟️  Match: {arsenal_name} vs {leeds_name}")
        print(f"   Date: {reference_date}")
        print(f"   Match ID: {match_id}")
        print()

        # Analyze individual team data
        arsenal_data = analyze_team_historical_data(
            session, arsenal_team_id, arsenal_name, reference_date
        )
        print()

        leeds_data = analyze_team_historical_data(
            session, leeds_team_id, leeds_name, reference_date
        )
        print()

        # Analyze head-to-head data
        h2h_data = analyze_head_to_head_data(
            session, arsenal_team_id, leeds_team_id,
            arsenal_name, leeds_name, reference_date
        )
        print()

        # Check feature extraction quality
        feature_quality = check_feature_extraction_quality(session, match_id)
        print()

        # Summary
        print("=" * 50)
        print("SUMMARY")
        print("=" * 50)

        if arsenal_data and leeds_data:
            print(f"📊 Individual Team Data:")
            print(f"   {arsenal_name}: {arsenal_data['total_matches']} matches ({'✅' if arsenal_data['meets_min_sample'] else '❌'})")
            print(f"   {leeds_name}: {leeds_data['total_matches']} matches ({'✅' if leeds_data['meets_min_sample'] else '❌'})")

            both_meet_requirement = arsenal_data['meets_min_sample'] and leeds_data['meets_min_sample']
            print(f"   Min sample requirement: {'✅ MET' if both_meet_requirement else '❌ NOT MET'}")

        if h2h_data:
            print(f"\n🤝 Head-to-Head Data:")
            print(f"   Available H2H matches: {h2h_data['total_h2h_matches']}")

        if feature_quality:
            completion_rate = (feature_quality['key_features_available'] / feature_quality['key_features_total']) * 100
            print(f"\n🔍 Feature Extraction:")
            print(f"   Key features available: {feature_quality['key_features_available']}/{feature_quality['key_features_total']} ({completion_rate:.1f}%)")

            if completion_rate >= 90:
                print("   ✅ Excellent data quality")
            elif completion_rate >= 70:
                print("   ⚠️  Good data quality")
            elif completion_rate >= 50:
                print("   ⚠️  Moderate data quality")
            else:
                print("   ❌ Poor data quality")

    finally:
        session.close()

if __name__ == "__main__":
    main()
