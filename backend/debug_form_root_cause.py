#!/usr/bin/env python3
"""Form verilerinin None olma kök nedenini izle."""

import sys
import os
sys.path.append(os.path.abspath('.'))
from app.prediction.service import PredictionService
from app.database import get_db
from app.providers.fotmob import FotMobFootballProvider
from app.database.models import Match

def debug_form_root_cause():
    """Arsenal-Leeds için form verilerinin kök nedenini izle."""

    match_id = '849f5743-1f96-4ade-be4c-af1c5d3da039'

    session = next(get_db())
    provider = FotMobFootballProvider(base_url='https://www.fotmob.com')
    prediction_service = PredictionService(provider=provider, db_session=session)

    try:
        match = session.query(Match).filter_by(id=match_id).first()

        print('=== FORM KOK NEDEN ANALIZI ===')
        print(f'Match ID: {match.id}')
        print(f'Arsenal ID: {match.home_team_id}')
        print(f'Leeds ID: {match.away_team_id}')

        # 1. feature_aggregator var mı?
        print(f'\n1. feature_aggregator exists: {prediction_service.feature_aggregator is not None}')

        if prediction_service.feature_aggregator:
            # 2. feature_set başarıyla extract ediliyor mu?
            print(f'\n2. Extracting feature_set...')
            try:
                feature_set = prediction_service.feature_aggregator.extract_features_for_match(
                    match_id=match.id
                )
                print(f'   feature_set extracted: {feature_set is not None}')

                if feature_set:
                    # 3. home_form var mı?
                    has_home_form = hasattr(feature_set, 'home_form')
                    print(f'\n3. feature_set.home_form exists: {has_home_form}')

                    if has_home_form:
                        home_form_value = feature_set.home_form
                        print(f'   feature_set.home_form value: {home_form_value}')

                        if home_form_value:
                            print(f'   home_form type: {type(home_form_value)}')
                            if isinstance(home_form_value, dict):
                                print(f'   home_form keys: {list(home_form_value.keys())}')
                                print(f'   wins: {home_form_value.get("wins")}')
                                print(f'   points: {home_form_value.get("points")}')
                                print(f'   sample_size: {home_form_value.get("sample_size")}')

                    # 4. away_form var mı?
                    has_away_form = hasattr(feature_set, 'away_form')
                    print(f'\n4. feature_set.away_form exists: {has_away_form}')

                    if has_away_form:
                        away_form_value = feature_set.away_form
                        print(f'   feature_set.away_form value: {away_form_value}')

                        if away_form_value:
                            print(f'   away_form type: {type(away_form_value)}')
                            if isinstance(away_form_value, dict):
                                print(f'   away_form keys: {list(away_form_value.keys())}')
                                print(f'   wins: {away_form_value.get("wins")}')
                                print(f'   points: {away_form_value.get("points")}')
                                print(f'   sample_size: {away_form_value.get("sample_size")}')
                else:
                    print('   ❌ feature_set is None!')

            except Exception as e:
                print(f'   ❌ feature_set extraction FAILED: {e}')
                import traceback
                traceback.print_exc()
        else:
            print('   ❌ feature_aggregator is None!')

        # 5. Geçmiş maçlar DB'de var mı kontrol et
        print(f'\n5. Checking historical matches in DB...')
        from app.database.models import Match as MatchModel

        arsenal_id = match.home_team_id
        leeds_id = match.away_team_id

        # Arsenal'in geçmiş maçları
        arsenal_matches = session.query(MatchModel).filter(
            ((MatchModel.home_team_id == arsenal_id) | (MatchModel.away_team_id == arsenal_id)) &
            (MatchModel.status == 'FINISHED') &
            (MatchModel.scheduled_at < match.scheduled_at)
        ).count()

        print(f'   Arsenal finished matches before this match: {arsenal_matches}')

        # Leeds'in geçmiş maçları
        leeds_matches = session.query(MatchModel).filter(
            ((MatchModel.home_team_id == leeds_id) | (MatchModel.away_team_id == leeds_id)) &
            (MatchModel.status == 'FINISHED') &
            (MatchModel.scheduled_at < match.scheduled_at)
        ).count()

        print(f'   Leeds finished matches before this match: {leeds_matches}')

        # 6. min_sample_size kontrolü
        print(f'\n6. Minimum sample size requirement check...')
        print(f'   Current min_sample_size setting: Check DataQualityGate or FeatureAggregator config')

        if arsenal_matches < 3:
            print(f'   ⚠️  Arsenal has only {arsenal_matches} finished matches (< 3)')
        if leeds_matches < 3:
            print(f'   ⚠️  Leeds has only {leeds_matches} finished matches (< 3)')

    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    debug_form_root_cause()
