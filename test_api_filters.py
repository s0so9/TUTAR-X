#!/usr/bin/env python3
"""API filtre testleri."""
import requests
import json

BASE_URL = "https://football-intelligence-eight.vercel.app/api/v1"

print("Test 1: Filtresiz maçlar")
print("=" * 60)
r = requests.get(f"{BASE_URL}/matches?limit=5")
print(f"Status: {r.status_code}")
print(f"Content-Type: {r.headers.get('content-type')}")
if r.status_code != 200:
    print(f"Response: {r.text[:500]}")
else:
    try:
        data = r.json()
        print(f"Count: {data.get('count')}")
        if data.get('matches'):
            print(f"First match date: {data['matches'][0].get('scheduled_at')}")
            print(f"First match status: {data['matches'][0].get('status')}")
    except Exception as e:
        print(f"JSON parse error: {e}")
        print(f"Response: {r.text[:200]}")

print("\n\nTest 2: Tarih + Status filtreleri")
print("=" * 60)
r = requests.get(
    f"{BASE_URL}/matches",
    params={
        "from_date": "2026-10-10",
        "to_date": "2026-10-17",
        "status": "SCHEDULED",
        "limit": 5
    }
)
data = r.json()
print(f"Status: {r.status_code}")
print(f"Count: {data.get('count')}")
if data.get('matches'):
    for i, match in enumerate(data['matches'][:3]):
        print(f"Match {i+1}: {match.get('scheduled_at')} - {match.get('status')}")
else:
    print("No matches returned")

print("\n\nTest 3: Sadece tarih filtreleri (status yok)")
print("=" * 60)
r = requests.get(
    f"{BASE_URL}/matches",
    params={
        "from_date": "2026-10-10",
        "to_date": "2026-10-17",
        "limit": 5
    }
)
data = r.json()
print(f"Status: {r.status_code}")
print(f"Count: {data.get('count')}")
if data.get('matches'):
    for i, match in enumerate(data['matches'][:3]):
        print(f"Match {i+1}: {match.get('scheduled_at')} - {match.get('status')}")

print("\n\nTest 4: Sadece status filtresi")
print("=" * 60)
r = requests.get(
    f"{BASE_URL}/matches",
    params={
        "status": "SCHEDULED",
        "limit": 5
    }
)
data = r.json()
print(f"Status: {r.status_code}")
print(f"Count: {data.get('count')}")
if data.get('matches'):
    for i, match in enumerate(data['matches'][:3]):
        print(f"Match {i+1}: {match.get('scheduled_at')} - {match.get('status')}")
