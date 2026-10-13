#!/usr/bin/env python3
"""Database yapısını ve scheduled_at timezone durumunu kontrol et."""
import sys
import os

# Backend klasörüne geç
os.chdir('backend')
sys.path.insert(0, '.')

from app.database.session import get_db
from app.database.models import Match
from sqlalchemy import inspect

db = next(get_db())

print(f'Database URL: {db.bind.url}')
print(f'\nScheduled_at column info:')
inspector = inspect(db.bind)
for col in inspector.get_columns('matches'):
    if col['name'] == 'scheduled_at':
        print(f"  Column: {col['name']}")
        print(f"  Type: {col['type']}")
        print(f"  Nullable: {col['nullable']}")

# Database'deki scheduled_at değerlerini kontrol et
print(f'\nActual scheduled_at values from database:')
matches = db.query(Match).filter(Match.status == 'SCHEDULED').order_by(Match.scheduled_at).limit(5).all()
for m in matches:
    print(f'  {m.scheduled_at} | type: {type(m.scheduled_at)} | tzinfo: {m.scheduled_at.tzinfo if hasattr(m.scheduled_at, "tzinfo") else "N/A"}')

db.close()
