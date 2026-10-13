"""
Check if H2H data exists in AnalysisContext for Arsenal-Leeds.
"""

import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database.models import Match, Team
from app.api.dependencies import get_data_provider
from app.prediction.service import PredictionService
from app.config import Settings

settings = Settings()
engine = create_engine(settings.database_url)


def check_h2h_context():
    """Check H2H data in AnalysisContext."""
    with Session(engine) as db:
        # Get Arsenal-Leeds match
        match_id = "849f5743-1f96-4ade-be4c-af1c5d3da039"

        # Use development provider directly
        from app.providers.development import DevelopmentProvider
        provider = DevelopmentProvider()

        match = provider.get_match(match_id)

        if not match:
            print(f"✗ Match not found: {match_id}")
            return

        print("=" * 80)
        print(f"ARSENAL-LEEDS H2H CONTEXT CHECK")
        print("=" * 80)
        print()
        print(f"Match ID: {match_id}")
        print(f"Home Team ID: {match.home_team_id}")
        print(f"Away Team ID: {match.away_team_id}")
        print()

        # Generate prediction with full context
        prediction_service = PredictionService(provider=provider, db_session=db)

        try:
            analysis_context = prediction_service.generate_full_prediction(
                match=match,
                odds_data=None
            )

            # Check H2H fields
            print("H2H Fields in AnalysisContext:")
            print("-" * 80)

            h2h_matches = analysis_context.head_to_head_matches
            print(f"head_to_head_matches: {h2h_matches is not None} (count: {len(h2h_matches) if h2h_matches else 0})")

            print(f"h2h_home_wins: {analysis_context.h2h_home_wins}")
            print(f"h2h_draws: {analysis_context.h2h_draws}")
            print(f"h2h_away_wins: {analysis_context.h2h_away_wins}")

            print()

            if h2h_matches and len(h2h_matches) > 0:
                print(f"✓ H2H DATA FOUND: {len(h2h_matches)} matches")
                print()
                print("Recent H2H matches:")
                for i, m in enumerate(h2h_matches[:5], 1):
                    print(f"  {i}. {m.scheduled_at.date()} - {m.home_score}-{m.away_score}")
                print()
                print(f"Summary: {analysis_context.h2h_home_wins}W-{analysis_context.h2h_draws}D-{analysis_context.h2h_away_wins}L")
            else:
                print("✗ NO H2H DATA in AnalysisContext")
                print()
                print("Checking if H2H matches exist in database...")

                # Direct DB check
                h2h_db_matches = db.query(Match).filter(
                    (
                        ((Match.home_team_id == match.home_team_id) & (Match.away_team_id == match.away_team_id)) |
                        ((Match.home_team_id == match.away_team_id) & (Match.away_team_id == match.home_team_id))
                    ),
                    Match.status == 'finished',
                    Match.scheduled_at < match.scheduled_at
                ).all()

                print(f"  Direct DB query found: {len(h2h_db_matches)} H2H matches")

                if len(h2h_db_matches) > 0:
                    print("  ✓ H2H data EXISTS in database but NOT extracted to context")
                    print("  → NEED TO FIX: H2H extraction in service.py")
                else:
                    print("  ✗ No H2H matches in database for these teams")

            print()
            print("=" * 80)

        except Exception as e:
            print(f"✗ Error generating prediction: {e}")
            import traceback
            traceback.print_exc()


if __name__ == '__main__':
    check_h2h_context()
