#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect('backend/football_intelligence.db')
cursor = conn.cursor()

# Get tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Available tables:")
for table in tables:
    print(f"  - {table[0]}")

# Get some match IDs
cursor.execute("SELECT match_id FROM matches LIMIT 3")
matches = cursor.fetchall()
print(f"\nSample match IDs: {[m[0] for m in matches]}")

conn.close()