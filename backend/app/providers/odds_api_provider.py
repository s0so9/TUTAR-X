"""The Odds API provider for bookmaker odds.

Fetches real bookmaker odds from The Odds API and calculates average market odds.
"""

import logging
import re
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
import requests

from app.config import settings

logger = logging.getLogger(__name__)

# Matches the apiKey query parameter in URLs embedded in exception messages
# (requests includes the full request URL in ConnectionError/HTTPError text).
_API_KEY_PARAM_RE = re.compile(r"(apiKey=)[^&\s'\"]+", re.IGNORECASE)


def redact_api_key(text: object, api_key: Optional[str] = None) -> str:
    """Return ``text`` as a string with any The Odds API key removed.

    Redacts both the ``apiKey=...`` query parameter and, if given, any literal
    occurrence of the configured key. Use this for every log line that may
    contain a request URL or exception message.
    """
    message = str(text)
    message = _API_KEY_PARAM_RE.sub(r"\1***REDACTED***", message)
    if api_key:
        message = message.replace(api_key, "***REDACTED***")
    return message


class TheOddsAPIProvider:
    """Provider for fetching bookmaker odds from The Odds API."""

    def __init__(self):
        """Initialize The Odds API provider."""
        self.api_key = settings.the_odds_api_key
        self.base_url = settings.the_odds_api_base_url
        self.enabled = settings.the_odds_api_enabled
        self.timeout = settings.the_odds_api_timeout_seconds
        self.cache_duration = settings.the_odds_api_cache_minutes * 60  # Convert to seconds

        # Simple in-memory cache
        # Format: {cache_key: (data, timestamp)}
        self._cache: Dict[str, Tuple[any, float]] = {}

    def is_available(self) -> bool:
        """Check if provider is available."""
        if not self.enabled:
            logger.debug("The Odds API is disabled in config")
            return False

        if not self.api_key:
            logger.warning("The Odds API key not configured")
            return False

        return True

    def _get_cache_key(self, sport_key: str, markets: str) -> str:
        """Generate cache key."""
        return f"{sport_key}_{markets}"

    def _get_from_cache(self, cache_key: str) -> Optional[any]:
        """Get data from cache if still valid."""
        if cache_key not in self._cache:
            return None

        data, cached_time = self._cache[cache_key]
        age = time.time() - cached_time

        if age > self.cache_duration:
            # Cache expired
            del self._cache[cache_key]
            return None

        logger.debug(f"Cache hit for {cache_key} (age: {age:.1f}s)")
        return data

    def _set_cache(self, cache_key: str, data: any):
        """Store data in cache."""
        self._cache[cache_key] = (data, time.time())

    def get_available_sports(self) -> Optional[List[Dict]]:
        """Get list of available sports.

        Returns:
            List of sport objects or None if request fails
        """
        if not self.is_available():
            return None

        try:
            url = f"{self.base_url}/sports"
            params = {'apiKey': self.api_key}

            response = requests.get(url, params=params, timeout=self.timeout)

            if response.status_code == 200:
                sports = response.json()
                logger.info(f"Fetched {len(sports)} sports from The Odds API")
                return sports
            elif response.status_code == 401:
                logger.error("The Odds API: Unauthorized - check API key")
                return None
            elif response.status_code == 429:
                logger.warning("The Odds API: Rate limit exceeded")
                return None
            else:
                logger.error(f"The Odds API returned status {response.status_code}")
                return None

        except requests.exceptions.Timeout:
            logger.error("The Odds API request timed out")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"The Odds API request failed: {redact_api_key(e, self.api_key)}")
            return None

    def check_quota(self) -> Tuple[bool, Optional[int]]:
        """Check if API quota is sufficient before making requests.

        Returns:
            Tuple of (has_quota, remaining_requests)
        """
        if not self.is_available():
            return (False, None)

        try:
            # Use sports endpoint to check quota (lightweight request)
            url = f"{self.base_url}/sports"
            params = {'apiKey': self.api_key}

            response = requests.get(url, params=params, timeout=self.timeout)

            remaining = response.headers.get('x-requests-remaining')
            if remaining:
                remaining_int = int(remaining)
                min_required = settings.the_odds_api_min_remaining_requests

                logger.info(f"The Odds API quota check: {remaining_int} requests remaining (threshold: {min_required})")

                if remaining_int < min_required:
                    logger.warning(f"API quota too low: {remaining_int} < {min_required}. Skipping odds fetch.")
                    return (False, remaining_int)

                return (True, remaining_int)

            # If header not present, assume we have quota
            logger.warning("x-requests-remaining header not found, proceeding with caution")
            return (True, None)

        except Exception as e:
            logger.error(f"Quota check failed: {redact_api_key(e, self.api_key)}")
            return (False, None)

    def get_odds(
        self,
        sport_key: str = "soccer_epl",
        regions: str = "eu,uk",
        markets: str = "h2h,spreads,totals",
        skip_quota_check: bool = False
    ) -> Optional[List[Dict]]:
        """Get odds for a specific sport.

        Args:
            sport_key: Sport identifier (e.g., 'soccer_epl', 'soccer_turkey_super_league')
            regions: Comma-separated regions (e.g., 'eu,uk,us')
            markets: Comma-separated markets (e.g., 'h2h,spreads,totals')
            skip_quota_check: Skip quota verification (use with caution)

        Returns:
            List of event objects with bookmaker odds or None if request fails
        """
        if not self.is_available():
            return None

        # Check cache first
        cache_key = self._get_cache_key(sport_key, markets)
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        # Check quota before making expensive request
        if not skip_quota_check:
            has_quota, remaining = self.check_quota()
            if not has_quota:
                logger.warning(f"Skipping odds fetch for {sport_key} due to low quota")
                return None

        try:
            url = f"{self.base_url}/sports/{sport_key}/odds"
            params = {
                'apiKey': self.api_key,
                'regions': regions,
                'markets': markets,
                'oddsFormat': 'decimal'
            }

            response = requests.get(url, params=params, timeout=self.timeout)

            # Log rate limit info
            remaining = response.headers.get('x-requests-remaining')
            used = response.headers.get('x-requests-used')
            if remaining:
                logger.info(f"The Odds API requests remaining: {remaining}")
            if used:
                logger.debug(f"The Odds API requests used: {used}")

            if response.status_code == 200:
                events = response.json()
                logger.info(f"Fetched {len(events)} events from The Odds API for {sport_key}")

                # Cache the result
                self._set_cache(cache_key, events)

                return events
            elif response.status_code == 401:
                logger.error("The Odds API: Unauthorized - check API key")
                return None
            elif response.status_code == 429:
                logger.warning("The Odds API: Rate limit exceeded")
                return None
            else:
                logger.error(f"The Odds API returned status {response.status_code}")
                return None

        except requests.exceptions.Timeout:
            logger.error(f"The Odds API request timed out for {sport_key}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"The Odds API request failed for {sport_key}: {redact_api_key(e, self.api_key)}")
            return None

    def calculate_average_odds(
        self,
        home_team: str,
        away_team: str,
        sport_key: str = "soccer_epl"
    ) -> Optional[Dict[str, any]]:
        """Calculate average bookmaker odds for a specific match.

        Args:
            home_team: Home team name
            away_team: Away team name
            sport_key: Sport identifier

        Returns:
            Dictionary with average odds and metadata:
            {
                'match_found': bool,
                'home_win': {
                    'average_odds': float,
                    'bookmaker_count': int,
                    'bookmakers': List[str],
                    'individual_odds': List[float]
                },
                'draw': {...},
                'away_win': {...},
                'over_2_5': {...},
                'under_2_5': {...},
                'timestamp': str
            }
        """
        if not self.is_available():
            logger.warning("The Odds API provider not available")
            return None

        # Fetch odds
        events = self.get_odds(sport_key=sport_key, markets="h2h,totals")
        if not events:
            logger.warning(f"No events fetched for {sport_key}")
            return None

        # Find matching event
        target_event = None
        for event in events:
            if (event.get('home_team', '').lower() == home_team.lower() and
                event.get('away_team', '').lower() == away_team.lower()):
                target_event = event
                break

        if not target_event:
            logger.info(f"Match not found: {home_team} vs {away_team} in {sport_key}")
            return {
                'match_found': False,
                'home_team': home_team,
                'away_team': away_team,
                'sport_key': sport_key
            }

        logger.info(f"Found match: {home_team} vs {away_team}")

        # Collect odds from all bookmakers
        h2h_odds = {'home': [], 'draw': [], 'away': []}
        totals_odds = {'over_2_5': [], 'under_2_5': []}
        bookmakers_used = set()

        for bookmaker in target_event.get('bookmakers', []):
            bookmaker_key = bookmaker.get('key')
            bookmakers_used.add(bookmaker_key)

            for market in bookmaker.get('markets', []):
                market_key = market.get('key')

                if market_key == 'h2h':
                    # Head-to-head (Match Result: Home, Draw, Away)
                    for outcome in market.get('outcomes', []):
                        name = outcome.get('name', '').lower()
                        price = outcome.get('price')

                        if price and price > 0:  # Valid odds
                            if name == home_team.lower():
                                h2h_odds['home'].append(price)
                            elif name == away_team.lower():
                                h2h_odds['away'].append(price)
                            elif 'draw' in name:
                                h2h_odds['draw'].append(price)

                elif market_key == 'totals':
                    # Totals (Over/Under)
                    point = market.get('point')
                    if point == 2.5:
                        for outcome in market.get('outcomes', []):
                            name = outcome.get('name', '').lower()
                            price = outcome.get('price')

                            if price and price > 0:
                                if 'over' in name:
                                    totals_odds['over_2_5'].append(price)
                                elif 'under' in name:
                                    totals_odds['under_2_5'].append(price)

        # Calculate averages
        def calc_avg(odds_list: List[float]) -> Optional[Dict]:
            """Calculate average from odds list."""
            if not odds_list:
                return None

            valid_odds = [o for o in odds_list if o > 0 and isinstance(o, (int, float))]
            if not valid_odds:
                return None

            avg = sum(valid_odds) / len(valid_odds)
            return {
                'average_odds': round(avg, 2),
                'bookmaker_count': len(valid_odds),
                'individual_odds': valid_odds,
                'min': min(valid_odds),
                'max': max(valid_odds)
            }

        result = {
            'match_found': True,
            'event_id': target_event.get('id'),
            'home_team': target_event.get('home_team'),
            'away_team': target_event.get('away_team'),
            'commence_time': target_event.get('commence_time'),
            'bookmakers_count': len(bookmakers_used),
            'bookmakers': sorted(list(bookmakers_used)),
            'home_win': calc_avg(h2h_odds['home']),
            'draw': calc_avg(h2h_odds['draw']),
            'away_win': calc_avg(h2h_odds['away']),
            'over_2_5': calc_avg(totals_odds['over_2_5']),
            'under_2_5': calc_avg(totals_odds['under_2_5']),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        logger.info(f"Calculated average odds from {len(bookmakers_used)} bookmakers")
        return result


# Global instance
the_odds_api_provider = TheOddsAPIProvider()
