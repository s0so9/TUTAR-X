#!/usr/bin/env python3
"""Tarih filtreleme sorununu test et."""
import sys
sys.path.insert(0, 'backend')

from datetime import date, datetime
from app.database.session import get_db
from app.database.models import Match as MatchDB, MatchStatus

db = next(get_db())

# Test parametreleri
from_date = date(2026, 10, 10)
to_date = date(2026, 10, 17)

print(f"Test: {from_date} - {to_date}")

# Toplam SCHEDULED maç
total = db.query(MatchDB).filter(MatchDB.status == MatchStatus.SCHEDULED).count()
print(f"Toplam SCHEDULED: {total}")

# Database adapter mantığı ile filtreleme
from_dt = datetime.combine(from_date, datetime.min.time())
to_dt = datetime.combine(to_date, datetime.max.time())

print(f"\nDatetime convert:")
print(f"  from: {from_dt} (tzinfo: {from_dt.tzinfo})")
print(f"  to: {to_dt} (tzinfo: {to_dt.tzinfo})")

# Filtreli sorgu
query = db.query(MatchDB).filter(
    MatchDB.status == MatchStatus.SCHEDULED,
    MatchDB.scheduled_at >= from_dt,
    MatchDB.scheduled_at <= to_dt
)

count = query.count()
print(f"\nFiltreli sonuç: {count} maç")

if count > 0:
    print(f"\nİlk 5 maç:")
    for m in query.order_by(MatchDB.scheduled_at).limit(5).all():
        print(f"  {m.scheduled_at} - ID: {m.id[:8]}...")
else:
    print("\n❌ Hiç maç bulunamadı!")
    print("\nIlk 5 SCHEDULED maç (tarihsiz):")
    for m in db.query(MatchDB).filter(MatchDB.status == MatchStatus.SCHEDULED).order_by(MatchDB.scheduled_at).limit(5).all():
        print(f"  {m.scheduled_at} - ID: {m.id[:8]}...")

db.close()
