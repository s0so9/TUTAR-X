#!/usr/bin/env python3
"""
Check database matches directly
"""

import sqlite3
import os

def check_database():
    """Check database match structure"""

    # Check different database files
    db_files = [
        'football_intelligence.db',
        'backend/football_intelligence.db',
        'backend/football.db',
        'backend/fotmob_dev.db'
    ]

    for db_file in db_files:
        if not os.path.exists(db_file):
            print(f"❌ {db_file} does not exist")
            continue

        print(f"\n=== Checking {db_file} ===")
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        try:
            print("Available tables:")
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()

            if not tables:
                print("❌ No tables found!")
                conn.close()
                continue

            for table in tables:
                print(f"  - {table[0]}")

            # Check if matches table exists
            if any('match' in table[0].lower() for table in tables):
                match_table = next(table[0] for table in tables if 'match' in table[0].lower())
                print(f"\nChecking {match_table} table:")

                cursor.execute(f"SELECT COUNT(*) FROM {match_table}")
                count = cursor.fetchone()[0]
                print(f"  Total records: {count}")

                if count > 0:
                    cursor.execute(f"SELECT * FROM {match_table} LIMIT 1")
                    sample = cursor.fetchone()
                    print(f"  Sample record: {sample}")

                    # Check for Fluminense
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM {match_table}
                        WHERE (home_team LIKE '%Fluminense%' OR away_team LIKE '%Fluminense%')
                           OR (home_team LIKE '%fluminense%' OR away_team LIKE '%fluminense%')
                    """)
                    fluminense_count = cursor.fetchone()[0]
                    print(f"  Fluminense matches: {fluminense_count}")

        except Exception as e:
            print(f"❌ Error checking {db_file}: {e}")
        finally:
            conn.close()

if __name__ == "__main__":
    check_database()

if __name__ == "__main__":
    check_database()
