#!/usr/bin/env python3
"""Test hybrid provider fallback functionality."""
import requests
import json

BASE_URL = "http://localhost:8000/api/v1"

print("=" * 70)
print("HYBRID PROVIDER FALLBACK TEST")
print("=" * 70)

def test_endpoint(description, params=None):
    print(f"\n{description}")
    print("-" * 50)

    url = f"{BASE_URL}/matches"
    if params:
        param_str = "&".join([f"{k}={v}" for k, v in params.items()])
        url += f"?{param_str}"

    try:
        response = requests.get(url, timeout=30)
        data = response.json()

        print(f"Status: {response.status_code}")
        print(f"Count: {data.get('count', 0)}")
        print(f"is_development_data: {data.get('is_development_data', False)}")

        if data.get('matches'):
            for i, match in enumerate(data['matches'][:3], 1):
                print(f"  {i}. {match.get('scheduled_at')} - {match.get('status')}")
        else:
            print("  ❌ No matches returned")

        return data.get('count', 0)

    except Exception as e:
        print(f"❌ Error: {e}")
        return 0

# Test scenarios
print("Testing fallback scenarios...")

# 1. Filtresiz (baseline)
count1 = test_endpoint("1. Filtresiz maçlar (baseline)", {"limit": "3"})

# 2. Status filtresi
count2 = test_endpoint("2. Status=SCHEDULED filtresi", {"status": "SCHEDULED", "limit": "3"})

# 3. Tarih + status filtresi (problem case)
count3 = test_endpoint("3. Tarih + Status filtresi (problem case)", {
    "from_date": "2026-10-10",
    "to_date": "2026-10-17",
    "status": "SCHEDULED",
    "limit": "3"
})

# 4. Sadece tarih filtresi
count4 = test_endpoint("4. Sadece tarih filtresi", {
    "from_date": "2026-10-10",
    "to_date": "2026-10-17",
    "limit": "3"
})

print("\n" + "=" * 70)
print("TEST RESULTS")
print("=" * 70)

print(f"✅ Filtresiz: {count1} maç")
print(f"{'✅' if count2 > 0 else '❌'} Status filtresi: {count2} maç")
print(f"{'✅' if count3 > 0 else '❌'} Tarih+Status filtresi: {count3} maç")
print(f"✅ Tarih filtresi: {count4} maç")

if count2 > 0 and count3 > 0:
    print("\n🎉 FALLBACK ÇALIŞIYOR!")
    print("Hybrid provider database boş olduğunda external provider'a fallback yapıyor.")
else:
    print("\n❌ FALLBACK SORUNLU!")
    print("Status filtresi external provider'a fallback yapmıyor.")
