#!/usr/bin/env python3
"""Final prediction test with known match."""

import requests
import time

def main():
    """Test prediction with Boca Juniors vs Rosario Central match."""
    
    port = 8004
    match_id = "f5182fe2-baee-442e-8d7b-f8fafc6660b0"  # Boca Juniors vs Rosario Central
    
    print(f"=== FINAL PREDICTION TEST ===")
    print(f"Port: {port}")
    print(f"Match ID: {match_id}")
    print(f"Match: Boca Juniors vs Rosario Central")
    print(f"Date: 2024-09-01 (we confirmed this has no historical matches before this date)")
    
    url = f"http://127.0.0.1:{port}/api/v1/matches/{match_id}/prediction"
    print(f"URL: {url}")
    
    try:
        print(f"\nSending prediction request...")
        start_time = time.time()
        
        response = requests.get(url, timeout=25)
        elapsed = time.time() - start_time
        
        print(f"Response time: {elapsed:.2f}s")
        print(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n*** PREDICTION SUCCESS ***")
            print(f"Home win: {data.get('home_win_probability')}")
            print(f"Draw: {data.get('draw_probability')}")  
            print(f"Away win: {data.get('away_win_probability')}")
            print(f"Home xG: {data.get('home_xg')}")
            print(f"Away xG: {data.get('away_xg')}")
            
        elif response.status_code == 400:
            error_detail = response.json().get('detail', response.text)
            print(f"\n*** INSUFFICIENT DATA (Expected) ***")
            print(f"Error: {error_detail}")
            
            if "insufficient data" in error_detail.lower():
                print(f"\n✅ This is the EXPECTED result because:")
                print(f"   - Both teams' earliest match is exactly 2024-09-01 00:00:00")
                print(f"   - Query uses 'scheduled_at < 2024-09-01 00:00:00'") 
                print(f"   - No matches exist BEFORE this date for either team")
                print(f"   - Prediction engine correctly requires historical data")
                print(f"   - This is NOT a bug - it's legitimate data scarcity")
            
        elif response.status_code == 404:
            print(f"\n*** MATCH NOT FOUND ***")
            print(f"Error: {response.text}")
            
        else:
            print(f"\n*** ERROR {response.status_code} ***")
            print(f"Response: {response.text}")
            
    except requests.exceptions.Timeout:
        print(f"\n*** TIMEOUT ***")
        print(f"Request took longer than 25 seconds")
        
    except Exception as e:
        print(f"\n*** ERROR ***")
        print(f"Exception: {str(e)}")

if __name__ == "__main__":
    main()