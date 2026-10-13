#!/usr/bin/env python3
"""Arsenal-Leeds maç analizini yapacak script."""

import requests
import json

def analyze_arsenal_leeds():
    """Arsenal-Leeds maçının detaylı analizini yap."""

    # Önceki testlerde çalışan match ID (Arsenal vs Leeds)
    # Arsenal: d749d5ee-b8e6-4042-92b1-b5d8f2a3910f
    # Leeds: e12af9d8-f085-4525-a381-dc990fc4ee61
    match_id = '849f5743-1f96-4ade-be4c-af1c5d3da039'
    url = f'http://localhost:8000/api/v1/matches/{match_id}/prediction'

    try:
        response = requests.get(url, timeout=30)
        print(f'HTTP Status: {response.status_code}')

        if response.status_code == 200:
            data = response.json()

            print('=== TEMEL TAHMIN DEGERLERI ===')
            home_xg = data.get('home_xg', 'N/A')
            away_xg = data.get('away_xg', 'N/A')
            predicted_score = data.get('predicted_score', 'N/A')

            print(f'xG -> Arsenal: {home_xg:.2f}, Leeds: {away_xg:.2f}')
            print(f'Tahmini Skor: {predicted_score}')

            home_prob = data.get('home_win_probability', 0) * 100
            draw_prob = data.get('draw_probability', 0) * 100
            away_prob = data.get('away_win_probability', 0) * 100
            btts_prob = data.get('btts_probability', 0) * 100

            print(f'Maç Sonucu -> H: {home_prob:.1f}%, D: {draw_prob:.1f}%, A: {away_prob:.1f}%')
            print(f'BTTS: {btts_prob:.1f}%')

            # TUTAR X Pick analizi
            mensione_pick = data.get('mensione_pick', {})
            if mensione_pick:
                print(f'\n=== TUTAR X PICK ===')
                print(f'Market: {mensione_pick.get("market", "N/A")}')
                print(f'Selection: {mensione_pick.get("selection", "N/A")}')

                prob = mensione_pick.get('probability', 'N/A')
                conf = mensione_pick.get('confidence', 'N/A')
                agreement = mensione_pick.get('model_agreement', 'N/A')

                print(f'Probability: {prob}')
                print(f'Confidence: {conf}')
                print(f'Model Agreement: {agreement}')
                print(f'Risk Level: {mensione_pick.get("risk_level", "N/A")}')
                print(f'Value Classification: {mensione_pick.get("value_classification", "N/A")}')

            # Market analysis - Under 3.5 kontrolü
            market_analysis = data.get('market_analysis', [])
            print(f'\n=== MARKET ANALYSIS ===')
            print(f'Toplam market: {len(market_analysis)}')

            under_3_5_found = False
            for market in market_analysis:
                market_type = market.get('market_type', '')
                line = market.get('line')

                if market_type == 'OVER_UNDER_3_5' and line == 3.5:
                    under_3_5_found = True
                    outcomes = market.get('outcomes', [])
                    for outcome in outcomes:
                        label = outcome.get('label', '')
                        if 'Under' in label:
                            model_prob = outcome.get('model_probability', 'N/A')
                            fair_odds = outcome.get('fair_odds', 'N/A')
                            print(f'Under 3.5 Market Probability: {model_prob:.3f}')
                            print(f'Fair Odds: {fair_odds:.2f}')

                            # TUTAR X pick ile karşılaştır
                            if mensione_pick and prob != 'N/A':
                                print(f'TUTAR X probability vs Market probability: {prob} vs {model_prob:.3f}')
                                if abs(float(prob) - model_prob) > 0.01:
                                    print('⚠️  TUTARSIZLIK: TUTAR X ve market probabilities farklı!')

            if not under_3_5_found:
                print('❌ Under 3.5 market bulunamadı!')
                print('Mevcut marketler:')
                for market in market_analysis:
                    print(f'  - {market.get("market_type")}, line: {market.get("line")}')

            # Matematik tutarlılık kontrolleri
            print(f'\n=== TUTARLILIK KONTROLLERI ===')

            # 1X2 toplamı
            total_1x2 = home_prob + draw_prob + away_prob
            print(f'1X2 Toplam: {total_1x2:.1f}% (100%\'e yakın olmalı)')

            # BTTS evet/hayır toplamı
            btts_no = 100 - btts_prob
            print(f'BTTS toplam: Yes {btts_prob:.1f}% + No {btts_no:.1f}% = {btts_prob + btts_no:.1f}%')

            # xG ve tahmini skor tutarlılığı
            if predicted_score != 'N/A' and '-' in str(predicted_score):
                try:
                    pred_home, pred_away = map(int, str(predicted_score).split('-'))
                    print(f'Predicted Score ({pred_home}-{pred_away}) vs xG ({home_xg:.2f}-{away_xg:.2f})')

                    # Basit tutarlılık: tahmini skor en yüksek olasılıklı skora eşit mi?
                    if home_xg > away_xg and pred_home <= pred_away:
                        print('⚠️  TUTARSIZLIK: Arsenal xG yüksek ama tahmini skorda Leeds önde!')
                    elif away_xg > home_xg and pred_away <= pred_home:
                        print('⚠️  TUTARSIZLIK: Leeds xG yüksek ama tahmini skorda Arsenal önde!')
                    else:
                        print('✅ xG ve tahmini skor genel olarak tutarlı')
                except:
                    print('Tahmini skor formatı analiz edilemedi')

        else:
            print(f'API Error: {response.status_code} - {response.text}')

    except Exception as e:
        print(f'Request error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    analyze_arsenal_leeds()
