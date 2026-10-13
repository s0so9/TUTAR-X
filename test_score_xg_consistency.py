#!/usr/bin/env python3
"""
Test skor ve xG tutarlılığı
"""

import requests
import json
import time

def main():
    # Wait for backend to be ready
    time.sleep(2)

    test_match_id = '006507ad-340d-41f6-a1d1-0dddd592297d'

    try:
        r = requests.get(f'http://127.0.0.1:8000/api/v1/matches/{test_match_id}/prediction', timeout=30)
        print('Status:', r.status_code)

        if r.status_code == 200:
            data = r.json()

            # Extract key values for skor/xG consistency analysis
            print('\n=== SKOR/xG CONSISTENCY ANALYSIS ===')
            print('Match ID:', data.get('match_id'))
            print('Predicted Score:', data.get('predicted_score'))
            print('Home xG:', data.get('home_xg'))
            print('Away xG:', data.get('away_xg'))
            print('Home Win Prob:', f"{data.get('home_win_probability', 0)*100:.1f}%")
            print('Away Win Prob:', f"{data.get('away_win_probability', 0)*100:.1f}%")

            # Check mensione pick
            mensione = data.get('mensione_pick', {})
            print('\n=== MENSIONE PICK ===')
            print('Market:', mensione.get('market'))
            print('Selection:', mensione.get('selection'))
            print('Probability:', f"{mensione.get('probability', 0)*100:.1f}%")

            # Check if score aligns with xG
            home_xg = data.get('home_xg', 0)
            away_xg = data.get('away_xg', 0)
            predicted_score = data.get('predicted_score', '')

            print('\n=== CONSISTENCY CHECK ===')
            if predicted_score and '-' in predicted_score:
                try:
                    home_score, away_score = map(int, predicted_score.split('-'))
                    print(f'Predicted Goals: Home {home_score}, Away {away_score}')
                    print(f'Expected Goals (xG): Home {home_xg:.2f}, Away {away_xg:.2f}')

                    # Basic consistency check
                    home_diff = abs(home_score - home_xg)
                    away_diff = abs(away_score - away_xg)
                    print(f'Differences: Home {home_diff:.2f}, Away {away_diff:.2f}')

                    # Check which team is favored
                    if home_score > away_score:
                        score_favors = 'Home'
                    elif away_score > home_score:
                        score_favors = 'Away'
                    else:
                        score_favors = 'Draw'

                    if home_xg > away_xg:
                        xg_favors = 'Home'
                    elif away_xg > home_xg:
                        xg_favors = 'Away'
                    else:
                        xg_favors = 'Equal'

                    print(f'Score favors: {score_favors}')
                    print(f'xG favors: {xg_favors}')

                    # Consistency assessment
                    if score_favors == xg_favors or (score_favors == 'Draw' and abs(home_xg - away_xg) < 0.5):
                        print('✅ Score and xG direction are consistent')
                    else:
                        print('⚠️  Score and xG favor different teams')

                    if home_diff > 1.5 or away_diff > 1.5:
                        print('⚠️  Large numerical difference between score and xG')
                    else:
                        print('✅ Score and xG values are reasonably close')

                except ValueError as e:
                    print('Could not parse predicted score:', e)
            else:
                print('No valid predicted score found')

        else:
            print('Error:', r.text[:200])

    except Exception as e:
        print('Exception:', e)

if __name__ == '__main__':
    main()
