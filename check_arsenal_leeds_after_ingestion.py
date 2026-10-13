"""Ingestion sonrası Arsenal ve Leeds durumunu kontrol et."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlalchemy import create_engine, func, or_
from sqlalchemy.orm import sessionmaker
from app.database.models import Match, Team

db_path = os.path.join(os.path.dirname(__file__), 'backend', 'football_intelligence.db')
engine = create_engine(f'sqlite:///{db_path}')
Session = sessionmaker(bind=engine)
session = Session()

print("=" * 80)
print("POST-INGESTION CHECK")
print("=" * 80)

# Toplam maç sayıları
total_matches = session.query(func.count(Match.id)).scalar()
print(f"\nTotal matches in DB: {total_matches}")

# Status dağılımı
from app.domain.enums import MatchStatus
statuses = session.query(Match.status, func.count(Match.id)).group_by(Match.status).all()
print(f"\nMatch status distribution:")
for status, count in statuses:
    print(f"  {status}: {count}")

# Arsenal ve Leeds
print(f"\n" + "=" * 80)
print("ARSENAL")
print("=" * 80)

arsenal = session.query(Team).filter(Team.provider_id == '9825').first()
if arsenal:
    print(f"UUID: {arsenal.id}")
    print(f"Name: {arsenal.name}")
    print(f"Provider ID: {arsenal.provider_id}")

    # Tüm maçlar
    all_arsenal = session.query(Match).filter(
        or_(
            Match.home_team_id == arsenal.id,
            Match.away_team_id == arsenal.id
        )
    ).all()

    print(f"\nTotal matches: {len(all_arsenal)}")

    # Status dağılımı
    status_dist = {}
    for m in all_arsenal:
        status = str(m.status)
        status_dist[status] = status_dist.get(status, 0) + 1

    print(f"Status distribution:")
    for status, count in status_dist.items():
        print(f"  {status}: {count}")

    # Skorlu maçları göster
    with_scores = [m for m in all_arsenal if m.home_score is not None and m.away_score is not None]
    print(f"\nMatches with scores: {len(with_scores)}")

    if with_scores:
        print(f"Sample (first 5):")
        for m in with_scores[:5]:
            is_home = m.home_team_id == arsenal.id
            print(f"  {m.scheduled_at.date()}: {'H' if is_home else 'A'}, {m.home_score}-{m.away_score}, {m.status}")
else:
    print("Arsenal NOT FOUND!")

print(f"\n" + "=" * 80)
print("LEEDS UNITED")
print("=" * 80)

leeds = session.query(Team).filter(Team.provider_id == '8463').first()
if leeds:
    print(f"UUID: {leeds.id}")
    print(f"Name: {leeds.name}")
    print(f"Provider ID: {leeds.provider_id}")

    all_leeds = session.query(Match).filter(
        or_(
            Match.home_team_id == leeds.id,
            Match.away_team_id == leeds.id
        )
    ).all()

    print(f"\nTotal matches: {len(all_leeds)}")

    status_dist = {}
    for m in all_leeds:
        status = str(m.status)
        status_dist[status] = status_dist.get(status, 0) + 1

    print(f"Status distribution:")
    for status, count in status_dist.items():
        print(f"  {status}: {count}")

    with_scores = [m for m in all_leeds if m.home_score is not None and m.away_score is not None]
    print(f"\nMatches with scores: {len(with_scores)}")

    if with_scores:
        print(f"Sample (first 5):")
        for m in with_scores[:5]:
            is_home = m.home_team_id == leeds.id
            print(f"  {m.scheduled_at.date()}: {'H' if is_home else 'A'}, {m.home_score}-{m.away_score}, {m.status}")
else:
    print("Leeds NOT FOUND!")

session.close()
