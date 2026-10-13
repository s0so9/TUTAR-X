#!/usr/bin/env python3

import requests

r = requests.get('http://127.0.0.1:8003/api/v1/competitions')
print(f'Status: {r.status_code}')
data = r.json()
print(f'First comp: "{data["competitions"][0]["name"]}"')

# Check backend logs for debug output
print('\nDebug loglarını kontrol et backend terminalinde:')