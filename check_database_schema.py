#!/usr/bin/env python3
import sqlite3
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def check_schema():
    db_path = os.path.join('backend', 'football_intelligence.db')
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print('Available tables:')
        for table in tables:
            print(f'  - {table[0]}')
            cursor.execute(f'PRAGMA table_info({table[0]})')
            columns = cursor.fetchall()
            print(f'    Columns: {[col[1] for col in columns]}')
        conn.close()
    else:
        print('Database not found at backend/football_intelligence.db')

if __name__ == '__main__':
    check_schema()