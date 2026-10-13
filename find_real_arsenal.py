"""Gerçek Arsenal ve Leeds takımlarını bul."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.models import Team

# Backend klasöründeki DB'yi kullan
db_path = os.path.join(os.path.dirname(__file__), 'backend', 'football_intelligence.db')
engine = create_engine(f'sqlite:///{db_path}')
Session = sessionmaker(bind=engine)
session = Session()

print("Arsenal içeren tüm takımlar:")
print("="*80)
arsenals = session.query(Team).filter(Team.name.ilike('%arsenal%')).all()
for team in arsenals:
    print(f"ID: {team.id}")
    print(f"Name: {team.name}")
    print(f"Provider ID: {team.provider_id}")
    print(f"Country: {team.country}")
    print("-"*80)

print("\n\nLeeds içeren tüm takımlar:")
print("="*80)
leeds_teams = session.query(Team).filter(Team.name.ilike('%leeds%')).all()
for team in leeds_teams:
    print(f"ID: {team.id}")
    print(f"Name: {team.name}")
    print(f"Provider ID: {team.provider_id}")
    print(f"Country: {team.country}")
    print("-"*80)

# FotMob'daki bilinen Arsenal ID'leri: 9825, 8650
print("\n\nFotMob Arsenal ID'leriyle kontrol:")
print("="*80)
for provider_id in ['9825', '8650']:
    team = session.query(Team).filter(Team.provider_id == provider_id).first()
    if team:
        print(f"Provider ID {provider_id}: {team.name} (UUID: {team.id})")
    else:
        print(f"Provider ID {provider_id}: BULUNAMADI")

# FotMob Leeds ID'si: 8463
print("\n\nFotMob Leeds ID'leriyle kontrol:")
print("="*80)
for provider_id in ['8463']:
    team = session.query(Team).filter(Team.provider_id == provider_id).first()
    if team:
        print(f"Provider ID {provider_id}: {team.name} (UUID: {team.id})")
    else:
        print(f"Provider ID {provider_id}: BULUNAMADI")

session.close()
