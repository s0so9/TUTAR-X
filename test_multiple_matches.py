#!/usr/bin/env python3
import requests
import sqlite3

# Get a few different match IDs to test
conn = sqlite3.connect('backend/football_intelligence.db')
cursor = conn.cursor()
cursor.execute('SELECT id FROM matches LIMIT 5')
match_ids = [row[0] for row in cursor.fetchall()]
conn.close()

print('Testing data quality metadata with different matches...')
for match_id in match_ids[:3]:  # Test first 3 matches
    try:
        url = f'http://localhost:8003/api/v1/matches/{match_id}/prediction'
        response = requests.get(url, timeout=10)
        print(f'\nMatch {match_id}: Status {response.status_code}')

        if response.status_code == 200:
            data = response.json()
            # Check for data quality indicators
            quality_indicators = []

            if 'is_development_data' in data:
                quality_indicators.append(f'is_development_data={data["is_development_data"]}')

            if 'mensione_pick' in data and data['mensione_pick']:
                pick = data['mensione_pick']
                if 'confidence' in pick:
                    quality_indicators.append(f'confidence={pick["confidence"]}')
                if 'data_quality' in pick:
                    quality_indicators.append(f'data_quality={pick["data_quality"]}')

            if quality_indicators:
                print('  ✅ Quality metadata:', ', '.join(quality_indicators))
            else:
                print('  ⚠️  No explicit quality metadata')

        elif response.status_code == 400:
            error = response.json()
            print(f'  ✅ Insufficient data rejection: {error.get("detail", "Unknown")}')

    except Exception as e:
        print(f'  ❌ Error: {e}')
