"""Odds updater service for scheduled bookmaker odds fetching and storage.

Fetches odds from The Odds API and stores them in the database for later averaging.
"""

import logging
from typing import List, Optional, Dict
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.database.models import BookmakerOdds, AverageMarketOdds, Match
from app.providers.odds_api_provider import the_odds_api_provider
from app.database.session import get_db
from app.utils.team_name_normalizer import teams_match, calculate_team_similarity
from app.config import settings

logger = logging.getLogger(__name__)


class OddsUpdaterService:
    """Service for updating bookmaker odds in database."""
    
    def __init__(self, db: Session):
        """Initialize odds updater service.
        
        Args:
            db: Database session
        """
        self.db = db
        self.provider = the_odds_api_provider
    
    def update_odds_for_sport(self, sport_key: str = "soccer_epl") -> Dict[str, any]:
        """Update odds for a specific sport.
        
        Args:
            sport_key: Sport identifier (e.g., 'soccer_epl')
            
        Returns:
            Dictionary with update statistics
        """
        if not self.provider.is_available():
            logger.warning("The Odds API provider not available")
            return {
                'success': False,
                'error': 'Provider not available',
                'sport_key': sport_key
            }
        
        logger.info(f"Fetching odds for {sport_key}")
        
        # Fetch odds from API
        events = self.provider.get_odds(sport_key=sport_key, markets="h2h,totals")
        
        if not events:
            logger.warning(f"No events returned for {sport_key}")
            return {
                'success': False,
                'error': 'No events returned',
                'sport_key': sport_key
            }
        
        stats = {
            'success': True,
            'sport_key': sport_key,
            'events_processed': 0,
            'odds_created': 0,
            'odds_updated': 0,
            'averages_calculated': 0,
            'errors': []
        }
        
        now = datetime.now(timezone.utc)
        
        for event in events:
            try:
                event_stats = self._process_event(event, sport_key, now)
                stats['events_processed'] += 1
                stats['odds_created'] += event_stats['odds_created']
                stats['odds_updated'] += event_stats['odds_updated']
                stats['averages_calculated'] += event_stats['averages_calculated']
            except Exception as e:
                error_msg = f"Error processing event {event.get('id')}: {e}"
                logger.error(error_msg)
                stats['errors'].append(error_msg)
        
        # Commit all changes
        try:
            self.db.commit()
            logger.info(f"Odds update completed for {sport_key}: {stats}")
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to commit odds update: {e}")
            stats['success'] = False
            stats['error'] = str(e)
        
        return stats
    
    def _process_event(self, event: Dict, sport_key: str, fetched_at: datetime) -> Dict[str, int]:
        """Process a single event and store/update its odds.
        
        Args:
            event: Event data from The Odds API
            sport_key: Sport identifier
            fetched_at: Timestamp when data was fetched
            
        Returns:
            Statistics dictionary
        """
        stats = {
            'odds_created': 0,
            'odds_updated': 0,
            'averages_calculated': 0
        }
        
        event_id = event.get('id')
        home_team = event.get('home_team')
        away_team = event.get('away_team')
        commence_time_str = event.get('commence_time')
        
        if not all([event_id, home_team, away_team, commence_time_str]):
            logger.warning(f"Incomplete event data: {event_id}")
            return stats
        
        # Parse commence time
        try:
            commence_time = datetime.fromisoformat(commence_time_str.replace('Z', '+00:00'))
        except Exception as e:
            logger.error(f"Invalid commence_time format for event {event_id}: {e}")
            return stats
        
        # Skip past matches
        if commence_time < fetched_at:
            logger.debug(f"Skipping past match: {event_id}")
            return stats
        
        # Try to find matching TUTAR X match
        match_id = self._find_match_id(home_team, away_team, commence_time)
        
        # Process each bookmaker
        for bookmaker in event.get('bookmakers', []):
            bookmaker_key = bookmaker.get('key')
            bookmaker_title = bookmaker.get('title')
            last_update_str = bookmaker.get('last_update')
            
            if not all([bookmaker_key, bookmaker_title, last_update_str]):
                continue
            
            try:
                odds_last_update = datetime.fromisoformat(last_update_str.replace('Z', '+00:00'))
            except:
                odds_last_update = fetched_at
            
            # Process each market
            for market in bookmaker.get('markets', []):
                market_key = market.get('key')
                market_point = market.get('point')  # For totals/spreads
                
                if not market_key:
                    continue
                
                # Process each outcome
                for outcome in market.get('outcomes', []):
                    outcome_name = outcome.get('name')
                    price = outcome.get('price')
                    
                    if not outcome_name or not price or price <= 0:
                        continue
                    
                    # Upsert bookmaker odds
                    existing_odds = self.db.query(BookmakerOdds).filter(
                        BookmakerOdds.provider_event_id == event_id,
                        BookmakerOdds.market_key == market_key,
                        BookmakerOdds.market_point == market_point,
                        BookmakerOdds.outcome_name == outcome_name,
                        BookmakerOdds.bookmaker_key == bookmaker_key
                    ).first()
                    
                    if existing_odds:
                        # Update existing
                        existing_odds.odds = price
                        existing_odds.odds_last_update = odds_last_update
                        existing_odds.fetched_at = fetched_at
                        existing_odds.updated_at = fetched_at
                        stats['odds_updated'] += 1
                    else:
                        # Create new
                        new_odds = BookmakerOdds(
                            provider_event_id=event_id,
                            sport_key=sport_key,
                            match_id=match_id,
                            home_team_name=home_team,
                            away_team_name=away_team,
                            commence_time=commence_time,
                            market_key=market_key,
                            market_point=market_point,
                            outcome_name=outcome_name,
                            bookmaker_key=bookmaker_key,
                            bookmaker_title=bookmaker_title,
                            odds=price,
                            odds_last_update=odds_last_update,
                            fetched_at=fetched_at
                        )
                        self.db.add(new_odds)
                        stats['odds_created'] += 1
        
        # Calculate and store averages for this event
        # Flush bookmaker odds to database first so they're visible to the average calculation
        try:
            self.db.flush()
        except Exception as e:
            logger.error(f"Failed to flush bookmaker odds for event {event_id}: {e}")
            # Continue anyway - might work if records already exist
        
        averages_count = self._calculate_and_store_averages(event_id, match_id, fetched_at)
        stats['averages_calculated'] = averages_count
        
        return stats
    
    def _find_match_id(self, home_team: str, away_team: str, commence_time: datetime) -> Optional[str]:
        """Find TUTAR X match ID for external event using enhanced team matching.
        
        Args:
            home_team: Home team name from The Odds API
            away_team: Away team name from The Odds API
            commence_time: Match commence time
            
        Returns:
            Match ID if found, None otherwise
        """
        # Time window for matching (±6 hours)
        time_window = timedelta(hours=6)
        
        matches = self.db.query(Match).filter(
            Match.scheduled_at >= commence_time - time_window,
            Match.scheduled_at <= commence_time + time_window
        ).all()
        
        if not matches:
            logger.debug(f"No matches found in time window for {home_team} vs {away_team}")
            return None
        
        # Find best match using team name similarity
        best_match = None
        best_score = 0.0
        match_threshold = 0.5  # Lower threshold for more matches
        
        for match in matches:
            home_similarity = calculate_team_similarity(home_team, match.home_team.name)
            away_similarity = calculate_team_similarity(away_team, match.away_team.name)
            
            # Average similarity for both teams
            avg_similarity = (home_similarity + away_similarity) / 2
            
            if avg_similarity > best_score:
                best_score = avg_similarity
                best_match = match
        
        if best_match and best_score >= match_threshold:
            logger.info(
                f"Matched '{home_team} vs {away_team}' to "
                f"'{best_match.home_team.name} vs {best_match.away_team.name}' "
                f"(similarity: {best_score:.2f})"
            )
            return best_match.id
        
        # No confident match found
        if best_match:
            logger.warning(
                f"Low confidence match for '{home_team} vs {away_team}': "
                f"'{best_match.home_team.name} vs {best_match.away_team.name}' "
                f"(similarity: {best_score:.2f} < {match_threshold})"
            )
        else:
            logger.debug(f"No match found for '{home_team} vs {away_team}'")
        
        return None
    
    def _calculate_and_store_averages(self, event_id: str, match_id: Optional[str], calculated_at: datetime) -> int:
        """Calculate and store average odds for an event.
        
        Args:
            event_id: Provider event ID
            match_id: TUTAR X match ID (if mapped)
            calculated_at: Calculation timestamp
            
        Returns:
            Number of averages calculated
        """
        count = 0
        
        # Get all odds for this event grouped by market/outcome
        odds_records = self.db.query(BookmakerOdds).filter(
            BookmakerOdds.provider_event_id == event_id
        ).all()
        
        if not odds_records:
            return count
        
        # Group by (market_key, market_point, outcome_name)
        groups = {}
        for odds_record in odds_records:
            key = (odds_record.market_key, odds_record.market_point, odds_record.outcome_name)
            if key not in groups:
                groups[key] = []
            groups[key].append(odds_record)
        
        # Calculate average for each group
        for (market_key, market_point, outcome_name), odds_list in groups.items():
            if not odds_list:
                continue
            
            # Extract valid odds
            valid_odds = [o.odds for o in odds_list if o.odds > 0]
            if not valid_odds:
                continue
            
            # Calculate statistics
            avg_odds = sum(valid_odds) / len(valid_odds)
            bookmakers = [o.bookmaker_key for o in odds_list]
            
            # Upsert average
            existing_avg = self.db.query(AverageMarketOdds).filter(
                AverageMarketOdds.provider_event_id == event_id,
                AverageMarketOdds.market_key == market_key,
                AverageMarketOdds.market_point == market_point,
                AverageMarketOdds.outcome_name == outcome_name
            ).first()
            
            if existing_avg:
                # Update
                existing_avg.average_odds = avg_odds
                existing_avg.bookmaker_count = len(valid_odds)
                existing_avg.min_odds = min(valid_odds)
                existing_avg.max_odds = max(valid_odds)
                existing_avg.bookmakers = bookmakers
                existing_avg.individual_odds = valid_odds
                existing_avg.calculated_at = calculated_at
                existing_avg.updated_at = calculated_at
            else:
                # Create
                new_avg = AverageMarketOdds(
                    provider_event_id=event_id,
                    match_id=match_id,
                    market_key=market_key,
                    market_point=market_point,
                    outcome_name=outcome_name,
                    average_odds=avg_odds,
                    bookmaker_count=len(valid_odds),
                    min_odds=min(valid_odds),
                    max_odds=max(valid_odds),
                    bookmakers=bookmakers,
                    individual_odds=valid_odds,
                    calculated_at=calculated_at
                )
                self.db.add(new_avg)
            
            count += 1
        
        return count
    
    def cleanup_old_odds(self, days_old: int = 7) -> int:
        """Clean up odds for matches that have already started/finished.
        
        Args:
            days_old: Remove odds older than this many days
            
        Returns:
            Number of records deleted
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
        
        # Delete old bookmaker odds
        deleted_odds = self.db.query(BookmakerOdds).filter(
            BookmakerOdds.commence_time < cutoff_date
        ).delete()
        
        # Delete old averages
        deleted_avgs = self.db.query(AverageMarketOdds).filter(
            AverageMarketOdds.calculated_at < cutoff_date
        ).delete()
        
        self.db.commit()
        
        total_deleted = deleted_odds + deleted_avgs
        logger.info(f"Cleaned up {total_deleted} old odds records")
        
        return total_deleted


def update_all_odds() -> Dict[str, any]:
    """Update odds for all configured sports.
    
    This is the main entry point for scheduled jobs.
    
    Returns:
        Dictionary with overall statistics
    """
    db = next(get_db())
    service = OddsUpdaterService(db)
    
    # Get sports from config (comma-separated string)
    sports_str = settings.the_odds_api_sports
    
    if not sports_str:
        logger.warning("No sports configured in the_odds_api_sports setting")
        return {
            'success': False,
            'error': 'No sports configured',
            'started_at': datetime.now(timezone.utc).isoformat()
        }
    
    # Parse comma-separated sports list
    sports = [s.strip() for s in sports_str.split(',') if s.strip()]
    
    if not sports:
        logger.warning("Empty sports list after parsing")
        return {
            'success': False,
            'error': 'Empty sports list',
            'started_at': datetime.now(timezone.utc).isoformat()
        }
    
    logger.info(f"Updating odds for {len(sports)} configured sports: {sports}")
    
    overall_stats = {
        'started_at': datetime.now(timezone.utc).isoformat(),
        'sports': [],
        'total_events': 0,
        'total_odds': 0,
        'total_averages': 0,
        'errors': []
    }
    
    for sport_key in sports:
        try:
            stats = service.update_odds_for_sport(sport_key)
            overall_stats['sports'].append(stats)
            
            if stats.get('success'):
                overall_stats['total_events'] += stats.get('events_processed', 0)
                overall_stats['total_odds'] += stats.get('odds_created', 0) + stats.get('odds_updated', 0)
                overall_stats['total_averages'] += stats.get('averages_calculated', 0)
            
            if stats.get('errors'):
                overall_stats['errors'].extend(stats['errors'])
        except Exception as e:
            error_msg = f"Failed to update {sport_key}: {e}"
            logger.error(error_msg)
            overall_stats['errors'].append(error_msg)
    
    # Cleanup old odds (optional)
    try:
        service.cleanup_old_odds(days_old=7)
    except Exception as e:
        logger.warning(f"Cleanup failed: {e}")
    
    overall_stats['completed_at'] = datetime.now(timezone.utc).isoformat()
    
    logger.info(f"Odds update completed: {overall_stats}")
    
    return overall_stats
