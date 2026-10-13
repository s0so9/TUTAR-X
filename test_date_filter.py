#!/usr/bin/env python3
"""Test tarih filtreleme sorununu."""
from app.database.session import get_db
from app.database.models import Match
from datetime import datetime, date

db = next(get_db())

# SCHEDULED maçları say
total_scheduled = db.query(Match).filter(Match.status == 'SCHEDULED').count()
print(f'Total SCHEDULED matches: {total_scheduled}')

# İlk 5 SCHEDULED maç
matches = db.query(Match).filter(Match.status == 'SCHEDULED').order_by(Match.scheduled_at).limit(5).all()
print(f'\nFirst 5 SCHEDULED matches:')
for m in matches:
    print(f'ID: {m.id[:8]}... Date: {m.scheduled_at} (tzinfo: {m.scheduled_at.tzinfo})')
    print(f'  Home: {m.home_team_id[:8] if m.home_team_id else None}... Away: {m.away_team_id[:8] if m.away_team_id else None}...')

# Test filtreleme
from_date = date(2026, 10, 10)
to_date = date(2026, 10, 17)
print(f'\nTest filter: from_date={from_date}, to_date={to_date}')

# Naive datetime (mevcut kod)
from_datetime_naive = datetime.combine(from_date, datetime.min.time())
to_datetime_naive = datetime.combine(to_date, datetime.max.time())
print(f'\nNaive datetime filtering:')
print(f'from_datetime: {from_datetime_naive} (tzinfo: {from_datetime_naive.tzinfo})')
print(f'to_datetime: {to_datetime_naive} (tzinfo: {to_datetime_naive.tzinfo}')

filtered_naive = db.query(Match).filter(
    Match.status == 'SCHEDULED',
    Match.scheduled_at >= from_datetime_naive,
    Match.scheduled_at <= to_datetime_naive
).count()
print(f'Result: {filtered_naive} matches')

# Timezone-aware datetime (düzeltilmiş)
from zoneinfo import ZoneInfo
from_datetime_tz = datetime.combine(from_date, datetime.min.time()).replace(tzinfo=ZoneInfo('Europe/Istanbul'))
to_datetime_tz = datetime.combine(to_date, datetime.max.time()).replace(tzinfo=ZoneInfo('Europe/Istanbul'))
print(f'\nTimezone-aware datetime filtering:')
print(f'from_datetime: {from_datetime_tz} (tzinfo: {from_datetime_tz.tzinfo})')
print(f'to_datetime: {to_datetime_tz} (tzinfo: {to_datetime_tz.tzinfo})')

filtered_tz = db.query(Match).filter(
    Match.status == 'SCHEDULED',
    Match.scheduled_at >= from_datetime_tz,
    Match.scheduled_at <= to_datetime_tz
).count()
print(f'Result: {filtered_tz} matches')

# Örnek maçları göster
print(f'\nExample matches in range (timezone-aware):')
example_matches = db.query(Match).filter(
    Match.status == 'SCHEDULED',
    Match.scheduled_at >= from_datetime_tz,
    Match.scheduled_at <= to_datetime_tz
).order_by(Match.scheduled_at).limit(3).all()

for m in example_matches:
    print(f'ID: {m.id[:8]}... Date: {m.scheduled_at}')
    print(f'  Home: {m.home_team_id[:8] if m.home_team_id else None}... Away: {m.away_team_id[:8] if m.away_team_id else None}...')
