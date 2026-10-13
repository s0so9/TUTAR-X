#!/usr/bin/env python3
"""Arsenal-Leeds maçını veritabanında bul."""

import sys
import os
sys.path.append(os.path.abspath('.'))
from app.database import get_db
from app.database.models import Match, Team

def find_arsenal_leeds():
    """Arsenal-Leeds maçlarını veritabanında bul."""

    session = next(get_db())

    try:
        # Arsenal ve Leeds takım ID'lerini bul
        arsenal = session.query(Team).filter(Team.name.ilike('%arsenal%')).first()
        leeds = session.query(Team).filter(Team.name.ilike('%leeds%')).first()

        if arsenal:
            print(f'Arsenal ID: {arsenal.id} - Name: {arsenal.name}')
        else:
            print('Arsenal bulunamadi')

        if leeds:
            print(f'Leeds ID: {leeds.id} - Name: {leeds.name}')
        else:
            print('Leeds bulunamadi')

        # Arsenal-Leeds maçlarını bul
        if arsenal and leeds:
            matches = session.query(Match).filter(
                ((Match.home_team_id == arsenal.id) & (Match.away_team_id == leeds.id)) |
                ((Match.home_team_id == leeds.id) & (Match.away_team_id == arsenal.id))
            ).all()

            print(f'\nBulunan Arsenal-Leeds maclari: {len(matches)}')
            for match in matches:
                home_team = session.query(Team).filter_by(id=match.home_team_id).first()
                away_team = session.query(Team).filter_by(id=match.away_team_id).first()

                print(f'Match ID: {match.id}')
                home_name = home_team.name if home_team else 'Unknown'
                away_name = away_team.name if away_team else 'Unknown'
                print(f'  {home_name} vs {away_name}')
                print(f'  Scheduled: {match.scheduled_at}')
                print(f'  Status: {match.status}')

                home_score = match.home_score if match.home_score is not None else '?'
                away_score = match.away_score if match.away_score is not None else '?'
                print(f'  Score: {home_score}-{away_score}')
                print()
        else:
            print('Arsenal veya Leeds bulunamadi, tüm takımları listeleyelim:')
            teams = session.query(Team).limit(20).all()
            for team in teams:
                print(f'  {team.id}: {team.name}')

    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    find_arsenal_leeds()
