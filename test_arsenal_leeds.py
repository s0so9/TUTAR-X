#!/usr/bin/env python3
import requests
import time

print('Starting Arsenal-Leeds prediction test...')
start = time.time()

try:
    response = requests.get('http://localhost:8003/api/v1/matches/849f5743-1f96-4ade-be4c-af1c5d3da039/prediction', timeout=45)
    duration = time.time() - start

    print(f'Duration: {duration:.2f} seconds')
    print(f'Status: {response.status_code}')

    if response.status_code == 400:
        data = response.json()
        print(f'Error: {data.get("detail", "Unknown error")}')
    elif response.status_code == 200:
        print('Success: Prediction returned')
    else:
        print(f'Unexpected status: {response.status_code}')

except Exception as e:
    duration = time.time() - start
    print(f'Duration: {duration:.2f} seconds')
    print(f'Error: {e}')
