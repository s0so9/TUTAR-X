#!/usr/bin/env python3

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

engine = create_engine('sqlite:///./football_intelligence.db')
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

with SessionLocal() as session:
    result = session.execute(text('SELECT scheduled_at, status, COUNT(*) FROM matches WHERE scheduled_at >= "2026-10-07" GROUP BY scheduled_at, status ORDER BY scheduled_at'))
    print('Matches in 2026 Oct period:')
    for date_str, status, count in result.fetchall():
        print(f'  {date_str}: {status} - {count} matches')