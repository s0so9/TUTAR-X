#!/usr/bin/env python3
"""Test prediction with suitable match that has historical data."""

import requests
import time

def main():
    """Test prediction with Chicago Fire FC vs Vancouver Whitecaps."""
    
    port = 8004
    match_id = "47cea9fe-85e0-4c71-9614-ab18f60ce356"  # Chicago Fire FC vs Vancouver Whitecaps
    
    print(f"=== SUITABLE MATCH PREDICTION TEST ===")
    print(f"Port: {port}")
    print(f"Match ID: {match_id}")
    print(f"Teams: Chicago Fire FC vs Vancouver Whitecaps")
    print(f"Date: 2026-10-07 (future match)")
    print(f"Historical data: 3 vs 3 matches (meets minimum requirement)")
    
    url = f"http://127.0.0.1:{port}/api/v1/matches/{match_id}/prediction"
    print(f"URL: {url}")
    
    try:
        print(f"\nSending prediction request...")
        start_time = time.time()
        
        response = requests.get(url, timeout=35)
        elapsed = time.time() - start_time
        
        print(f"Response time: {elapsed:.2f}s")
        print(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n🎉 *** PREDICTION SUCCESS *** 🎉")
            print(f"Home win probability: {data.get('home_win_probability'):.3f}")
            print(f"Draw probability: {data.get('draw_probability'):.3f}")  
            print(f"Away win probability: {data.get('away_win_probability'):.3f}")
            print(f"Home xG: {data.get('home_xg'):.2f}")
            print(f"Away xG: {data.get('away_xg'):.2f}")
            print(f"BTTS probability: {data.get('btts_probability'):.3f}")
            
            if 'mensione_pick' in data and data['mensione_pick']:
                pick = data['mensione_pick']
                print(f"\nMensione Pick:")
                print(f"  Market: {pick.get('market_type')}")
                print(f"  Selection: {pick.get('selection')}")
                print(f"  Confidence: {pick.get('confidence')}")
                print(f"  Reasoning: {pick.get('reasoning', 'N/A')}")
            
            print(f"\n✅ PREDICTION SYSTEM IS WORKING!")
            print(f"✅ Response time: {elapsed:.2f}s")
            return True
            
        elif response.status_code == 400:
            error_detail = response.json().get('detail', response.text)
            print(f"\n❌ INSUFFICIENT DATA")
            print(f"Error: {error_detail}")
            print(f"This indicates the data quality check failed despite meeting minimum count")
            return False
            
        elif response.status_code == 404:
            print(f"\n❌ MATCH NOT FOUND")
            print(f"Error: {response.text}")
            print(f"Match may not be accessible via API despite being in database")
            return False
            
        else:
            print(f"\n❌ ERROR {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"\n⏱️ TIMEOUT")
        print(f"Request took longer than 35 seconds")
        return False
        
    except Exception as e:
        print(f"\n❌ ERROR")
        print(f"Exception: {str(e)}")
        return False

if __name__ == "__main__":
    main()