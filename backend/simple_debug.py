#!/usr/bin/env python3
"""Basit debug - mevcut test sonuçlarını analiz et."""

import sys
import os
sys.path.append(os.path.abspath('.'))

from app.database import get_db
from app.database.models import Match, Team

def check_match_data():
    """Arsenal-Leeds maç verilerini basit kontrolü."""

    target_match_id = 'fcca0ac7-8551-41f1-922e-38ae3c97fce0'
    session = next(get_db())

    try:
        # Get match
        match = session.query(Match).filter_by(id=target_match_id).first()
        if not match:
            print("❌ Match not found")
            return

        print("=" * 50)
        print("ARSENAL-LEEDS MAÇI VERİ ANALİZİ")
        print("=" * 50)

        # Get teams
        home_team = session.query(Team).filter_by(id=match.home_team_id).first()
        away_team = session.query(Team).filter_by(id=match.away_team_id).first()

        print(f"Maç: {home_team.name if home_team else 'Unknown'} vs {away_team.name if away_team else 'Unknown'}")
        print(f"Tarih: {match.scheduled_at}")
        print()

        # Historical matches with xG
        print("GEÇMİŞ xG VERİLERİ:")

        # Home team matches
        home_matches = session.query(Match).filter(
            ((Match.home_team_id == match.home_team_id) |
             (Match.away_team_id == match.home_team_id)) &
            (Match.scheduled_at < match.scheduled_at) &
            (Match.status == 'FINISHED') &
            (Match.home_xg.isnot(None)) &
            (Match.away_xg.isnot(None))
        ).order_by(Match.scheduled_at.desc()).limit(5).all()

        print(f"\n{home_team.name if home_team else 'Home team'} son 5 maçı (xG ile):")
        home_total_goals = 0
        home_count = 0
        for hm in home_matches:
            is_home = hm.home_team_id == match.home_team_id
            team_xg = hm.home_xg if is_home else hm.away_xg
            opp_xg = hm.away_xg if is_home else hm.home_xg
            total_xg = hm.home_xg + hm.away_xg
            team_goals = hm.home_score if is_home else hm.away_score
            opp_goals = hm.away_score if is_home else hm.home_score
            total_goals = hm.home_score + hm.away_score

            venue = "Ev" if is_home else "Deplasman"
            print(f"  {hm.scheduled_at.date()}: {venue} - xG: {team_xg:.1f}-{opp_xg:.1f} (Top:{total_xg:.1f}), Skor: {team_goals}-{opp_goals} (Top:{total_goals})")
            home_total_goals += total_goals
            home_count += 1

        # Away team matches
        away_matches = session.query(Match).filter(
            ((Match.home_team_id == match.away_team_id) |
             (Match.away_team_id == match.away_team_id)) &
            (Match.scheduled_at < match.scheduled_at) &
            (Match.status == 'FINISHED') &
            (Match.home_xg.isnot(None)) &
            (Match.away_xg.isnot(None))
        ).order_by(Match.scheduled_at.desc()).limit(5).all()

        print(f"\n{away_team.name if away_team else 'Away team'} son 5 maçı (xG ile):")
        away_total_goals = 0
        away_count = 0
        for am in away_matches:
            is_home = am.home_team_id == match.away_team_id
            team_xg = am.home_xg if is_home else am.away_xg
            opp_xg = am.away_xg if is_home else am.home_xg
            total_xg = am.home_xg + am.away_xg
            team_goals = am.home_score if is_home else am.away_score
            opp_goals = am.away_score if is_home else am.home_score
            total_goals = am.home_score + am.away_score

            venue = "Ev" if is_home else "Deplasman"
            print(f"  {am.scheduled_at.date()}: {venue} - xG: {team_xg:.1f}-{opp_xg:.1f} (Top:{total_xg:.1f}), Skor: {team_goals}-{opp_goals} (Top:{total_goals})")
            away_total_goals += total_goals
            away_count += 1

        # Calculate averages
        if home_count > 0:
            avg_home_goals = home_total_goals / home_count
            print(f"\n{home_team.name if home_team else 'Home team'} son maçlarında ortalama toplam gol: {avg_home_goals:.2f}")

        if away_count > 0:
            avg_away_goals = away_total_goals / away_count
            print(f"{away_team.name if away_team else 'Away team'} son maçlarında ortalama toplam gol: {avg_away_goals:.2f}")

        if home_count > 0 and away_count > 0:
            overall_avg = (home_total_goals + away_total_goals) / (home_count + away_count)
            print(f"Her iki takım için genel ortalama: {overall_avg:.2f}")

            if overall_avg > 2.5:
                print(f"⚠️  Ortalama 2.5 üzerinde - Over 2.5 için yüksek olasılık beklenir")
            if overall_avg > 3.5:
                print(f"⚠️  Ortalama 3.5 üzerinde - aşırı yüksek gol beklentisi")

        # Check for high-scoring teams
        high_scoring_matches = session.query(Match).filter(
            ((Match.home_team_id == match.home_team_id) |
             (Match.away_team_id == match.home_team_id) |
             (Match.home_team_id == match.away_team_id) |
             (Match.away_team_id == match.away_team_id)) &
            (Match.scheduled_at < match.scheduled_at) &
            (Match.status == 'FINISHED') &
            ((Match.home_score + Match.away_score) > 3)
        ).count()

        total_finished_matches = session.query(Match).filter(
            ((Match.home_team_id == match.home_team_id) |
             (Match.away_team_id == match.home_team_id) |
             (Match.home_team_id == match.away_team_id) |
             (Match.away_team_id == match.away_team_id)) &
            (Match.scheduled_at < match.scheduled_at) &
            (Match.status == 'FINISHED')
        ).count()

        if total_finished_matches > 0:
            high_scoring_ratio = high_scoring_matches / total_finished_matches
            print(f"\nYüksek skorlu maç oranı (>3 gol): {high_scoring_matches}/{total_finished_matches} = {high_scoring_ratio:.2%}")

            if high_scoring_ratio > 0.6:
                print("⚠️  Çok yüksek skorlu takımlar - %99.3 Over olasılığını açıklayabilir")

    finally:
        session.close()

if __name__ == '__main__':
    check_match_data()
