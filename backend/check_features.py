#!/usr/bin/env python3
"""Feature snapshot verilerini kontrol et."""

import sys
import os
sys.path.append(os.path.abspath('.'))
from app.prediction.service import PredictionService
from app.database import get_db
from app.providers.fotmob import FotMobFootballProvider
from app.database.models import Match

def check_features():
    """Arsenal-Leeds maçı için feature snapshot'ı kontrol et."""

    match_id = '849f5743-1f96-4ade-be4c-af1c5d3da039'

    session = next(get_db())
    provider = FotMobFootballProvider(base_url='https://www.fotmob.com')
    prediction_service = PredictionService(provider=provider, db_session=session)

    try:
        match = session.query(Match).filter_by(id=match_id).first()

        # Feature snapshot al
        snapshot = prediction_service._extract_canonical_snapshot(match)

        print('=== FEATURE SNAPSHOT KONTROL ===')

        # Form verileri
        print(f'\nForm Metrics:')
        if snapshot.home_form:
            points = snapshot.home_form.points if hasattr(snapshot.home_form, "points") else "N/A"
            matches = snapshot.home_form.matches_analyzed if hasattr(snapshot.home_form, "matches_analyzed") else "N/A"
            print(f'  Arsenal form points: {points}')
            print(f'  Arsenal form matches: {matches}')
        else:
            print(f'  Arsenal form: None')

        if snapshot.away_form:
            points = snapshot.away_form.points if hasattr(snapshot.away_form, "points") else "N/A"
            matches = snapshot.away_form.matches_analyzed if hasattr(snapshot.away_form, "matches_analyzed") else "N/A"
            print(f'  Leeds form points: {points}')
            print(f'  Leeds form matches: {matches}')
        else:
            print(f'  Leeds form: None')

        # Team strength
        print(f'\nTeam Strength:')
        if snapshot.home_strength:
            print(f'  Arsenal attack: {snapshot.home_strength.attack if hasattr(snapshot.home_strength, "attack") else "N/A"}')
            print(f'  Arsenal defense: {snapshot.home_strength.defense if hasattr(snapshot.home_strength, "defense") else "N/A"}')
        else:
            print(f'  Arsenal strength: None')

        if snapshot.away_strength:
            print(f'  Leeds attack: {snapshot.away_strength.attack if hasattr(snapshot.away_strength, "attack") else "N/A"}')
            print(f'  Leeds defense: {snapshot.away_strength.defense if hasattr(snapshot.away_strength, "defense") else "N/A"}')
        else:
            print(f'  Leeds strength: None')

        # Data quality report
        print(f'\n=== DATA QUALITY ===')
        quality_report = snapshot.data_quality_report
        print(f'Overall score: {quality_report.overall_score}')
        print(f'Has sufficient data: {quality_report.has_sufficient_data}')
        print(f'Missing critical features: {quality_report.missing_critical_features}')

    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    check_features()
