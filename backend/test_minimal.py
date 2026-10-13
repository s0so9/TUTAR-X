"""Minimal test to identify blocking import."""

import sys
print("Starting minimal test...")

print("Importing app.config...")
from app.config import settings
print(f"✓ Config loaded. use_real_providers={settings.use_real_providers}")

print("Importing app.main...")
from app.main import app
print("✓ App created")

print("Testing health endpoint synchronously...")
from fastapi.testclient import TestClient
client = TestClient(app)

print("Sending request to /health...")
response = client.get("/health")
print(f"✓ Response: {response.status_code} - {response.json()}")

print("\n✓ ALL TESTS PASSED - Server is working!")
