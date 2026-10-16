"""Application configuration management."""

from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Database
    database_url: str = "sqlite:///./football_intelligence.db"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8003
    api_debug: bool = True

    # CORS
    cors_origins: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
    ]

    # AI Provider (Ollama)
    ollama_endpoint: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3-coder:30b"

    # Football Data Providers
    # Ryzellx (PRIMARY provider)
    # Use local Ryzellx for development: http://localhost:3001
    # Use public Ryzellx for production: https://football-live-api.vercel.app
    ryzellx_base_url: str = "http://localhost:3001"
    
    # FotMob (FAST/LIVE provider)
    # Correct base URL: endpoints are /api/data/matches, /api/data/matchDetails
    fotmob_base_url: str = "https://www.fotmob.com"
    
    # OpenLigaDB (INDEPENDENT FALLBACK provider)
    openligadb_base_url: str = "https://api.openligadb.de"
    
    # Provider behavior
    provider_timeout_seconds: float = 10.0
    provider_retry_count: int = 2
    use_real_providers: bool = True  # True = Use HybridProvider (database + external), False = DevelopmentProvider only
    is_development: bool = Field(
        default=False,
        validation_alias="FI_IS_DEVELOPMENT",
        description="Development mode flag. Set FI_IS_DEVELOPMENT=true in environment."
    )

    # Competitions shown by default in match lists (FotMob league ids): the 10 strongest
    # European leagues by UEFA coefficient + Champions/Europa/Conference League — the
    # competitions whose player data is collected and trained on. "?scope=all" lists everything.
    featured_competition_ids: str = "47,87,55,54,53,57,61,40,71,122,42,73,10216"

    # Feature Engineering
    team_form_window: int = 5  # Number of recent matches to consider for form
    min_sample_size: int = 3  # Minimum matches needed for reliable features
    
    # Data Freshness Configuration
    # Controls when HybridProvider should refresh data from external providers vs using cached database data
    
    # SCHEDULED matches: Refresh if data is older than this (in minutes)
    data_freshness_scheduled_minutes: int = 120  # 2 hours - scheduled matches don't change frequently
    
    # LIVE matches: Refresh if data is older than this (in seconds)
    data_freshness_live_seconds: int = 30  # 30 seconds - live matches need real-time updates
    
    # FINISHED matches: Refresh if data is older than this (in minutes)
    # Increased to 72 hours (3 days) to handle database-only scenarios better
    data_freshness_finished_minutes: int = 4320  # 72 hours - finished matches are stable
    
    # Recently finished: Consider matches finished within this window as needing verification (in minutes)
    data_freshness_finished_recent_minutes: int = 180  # 3 hours - final scores should be confirmed
    
    # Approaching kickoff: Refresh scheduled matches if kickoff is within this window (in minutes)
    data_freshness_approaching_kickoff_minutes: int = 60  # 1 hour - lineup and last-minute changes

    # Logging
    log_level: str = "INFO"
    
    # The Odds API (Bookmaker Odds Provider)
    the_odds_api_key: str = ""
    the_odds_api_enabled: bool = False
    the_odds_api_base_url: str = "https://api.the-odds-api.com/v4"
    the_odds_api_cache_minutes: int = 60  # Cache odds for 1 hour
    the_odds_api_timeout_seconds: float = 10.0
    the_odds_api_min_remaining_requests: int = 50  # Skip updates if credits below this
    the_odds_api_sports: str = "soccer_epl,soccer_germany_bundesliga,soccer_spain_la_liga,soccer_italy_serie_a,soccer_france_ligue_one"  # Comma-separated

    # Team-news live layer (injuries/suspensions, expected/confirmed XI, last-5
    # form). See docs/live-layer.md. The background refresh is OFF by default;
    # scripts/live/refresh_team_news.py --once can run it from cron instead.
    team_news_refresh_enabled: bool = False
    team_news_competitions: str = "47,87,55,54,53,57,61,40,71,122,42,73,10216"  # FotMob league ids
    team_news_hours_ahead: float = 72.0  # refresh matches kicking off within this window
    team_news_finished_lookback_hours: float = 24.0  # ingest player stats of matches finished in this window
    team_news_squad_refresh_hours: float = 6.0
    team_news_match_refresh_minutes: float = 15.0
    team_news_near_kickoff_hours: float = 2.0
    team_news_near_kickoff_refresh_minutes: float = 5.0
    team_news_finished_refresh_minutes: float = 30.0
    team_news_fotmob_min_interval_seconds: float = 1.0  # in-process pacing, never below 1 s
    team_news_keep_raw: bool = True  # keep changed raw responses (gzip) for offline re-parsing
    team_news_raw_cache_dir: str = ""  # empty -> backend/data/raw_cache/live_team_news

    # Headline pick tracking (Banko / Oranli, docs/PROGRESS.md 2026-10-15): freezes the two headline
    # picks of every featured-competition match shortly before kick-off and settles them after full
    # time, in an in-app background loop (HEADLINE_TRACKING_ENABLED=false turns it off;
    # backend/scripts/live/headline_tracking.py --once runs one pass by hand).
    headline_tracking_enabled: bool = True
    headline_freeze_minutes_before: float = 20  # freeze when kick-off is this close (confirmed line-ups are out ~60 min before)
    headline_tick_seconds: float = 60.0
    headline_schedule_refresh_seconds: float = 300.0  # how often the fixture list is re-read (shared provider cache)
    headline_settle_first_check_minutes: float = 95.0  # no result lookups before kick-off + this
    headline_settle_check_seconds: float = 120.0  # per unsettled match, after the first check
    headline_settle_give_up_hours: float = 12.0  # stop looking for a result this long after kick-off

    # Admin API Security
    FI_ADMIN_TOKEN: str = Field(
        default="",
        description="Admin token for protected endpoints (e.g., manual odds update). Leave empty to disable auth (dev only)."
    )

    class Config:
        """Pydantic configuration."""

        env_file = ".env"
        case_sensitive = False


settings = Settings()
