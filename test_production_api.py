#!/usr/bin/env python3
"""Production API test."""
import requests
import json

BASE_URL = "https://tutar-x-api.vercel.app/api/v1"

print("=" * 70)
print("PRODUCTION API TEST")
print("=" * 70)

# Test 1: Filtresiz
print("\n1. Filtresiz maçlar (limit=3)")
r1 = requests.get(f"{BASE_URL}/matches?limit=3")
d1 = r1.json()
print(f"   Status: {r1.status_code}")
print(f"   Count: {d1.get('count')}")
print(f"   is_development_data: {d1.get('is_development_data')}")
if d1.get('matches'):
    for i, m in enumerate(d1['matches'][:3], 1):
        print(f"   Match {i}: {m.get('scheduled_at')} - {m.get('status')}")

# Test 2: Sadece status filtresi
print("\n2. Sadece status=SCHEDULED (limit=3)")
r2 = requests.get(f"{BASE_URL}/matches?status=SCHEDULED&limit=3")
d2 = r2.json()
print(f"   Status: {r2.status_code}")
print(f"   Count: {d2.get('count')}")
if d2.get('matches'):
    for i, m in enumerate(d2['matches'][:3], 1):
        print(f"   Match {i}: {m.get('scheduled_at')} - {m.get('status')}")
else:
    print("   ❌ No matches returned")

# Test 3: Tarih + status filtresi
print("\n3. Tarih + status filtresi")
print("   from_date=2026-10-10, to_date=2026-10-17, status=SCHEDULED")
r3 = requests.get(
    f"{BASE_URL}/matches",
    params={
        "from_date": "2026-10-10",
        "to_date": "2026-10-17",
        "status": "SCHEDULED",
        "limit": 3
    }
)
d3 = r3.json()
print(f"   Status: {r3.status_code}")
print(f"   Count: {d3.get('count')}")
if d3.get('matches'):
    for i, m in enumerate(d3['matches'][:3], 1):
        print(f"   Match {i}: {m.get('scheduled_at')} - {m.get('status')}")
else:
    print("   ❌ No matches returned")

# Test 4: Sadece tarih filtresi (status yok)
print("\n4. Sadece tarih filtresi (status yok)")
print("   from_date=2026-10-10, to_date=2026-10-17")
r4 = requests.get(
    f"{BASE_URL}/matches",
    params={
        "from_date": "2026-10-10",
        "to_date": "2026-10-17",
        "limit": 3
    }
)
d4 = r4.json()
print(f"   Status: {r4.status_code}")
print(f"   Count: {d4.get('count')}")
if d4.get('matches'):
    for i, m in enumerate(d4['matches'][:3], 1):
        print(f"   Match {i}: {m.get('scheduled_at')} - {m.get('status')}")
else:
    print("   ❌ No matches returned")

print("\n" + "=" * 70)
print("SONUÇ ANALİZİ")
print("=" * 70)

if d1.get('count', 0) > 0:
    print(f"✅ Filtresiz endpoint çalışıyor: {d1['count']} maç")
else:
    print("❌ Filtresiz endpoint de boş dönüyor")

if d2.get('count', 0) > 0:
    print(f"✅ Status filtresi çalışıyor: {d2['count']} maç")
else:
    print("❌ Status filtresi çalışmıyor")

if d3.get('count', 0) > 0:
    print(f"✅ Tarih+Status filtresi çalışıyor: {d3['count']} maç")
else:
    print("❌ Tarih+Status filtresi çalışmıyor (BUG)")

if d4.get('count', 0) > 0:
    print(f"✅ Sadece tarih filtresi çalışıyor: {d4['count']} maç")
else:
    print("❌ Sadece tarih filtresi çalışmıyor")
