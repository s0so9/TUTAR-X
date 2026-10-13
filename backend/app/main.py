"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.v1 import api_router
from app.database import get_session_factory
from app.ingestion.service import IngestionService


# Application state
class AppState:
    """Application state container."""
    ingestion_service: IngestionService = None
    provider_cache = None  # Application-level provider cache shared across requests


app_state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    import logging
    logger = logging.getLogger(__name__)

    # Startup
    from app.providers.cache import ProviderCache

    # Initialize application-level provider cache
    # This cache is shared across all requests within the same worker process
    app_state.provider_cache = ProviderCache()
    logger.info("✓ Initialized application-level provider cache")

    session_factory = get_session_factory()
    app_state.ingestion_service = IngestionService(session_factory)
    logger.info("✓ Initialized ingestion service")

    # Team-news live refresh (OFF by default; docs/live-layer.md)
    team_news_handle = None
    if settings.team_news_refresh_enabled:
        from app.services.team_news.scheduler import start_team_news_refresher

        team_news_handle = start_team_news_refresher(session_factory)

    yield

    if team_news_handle is not None:
        from app.services.team_news.scheduler import stop_team_news_refresher

        await stop_team_news_refresher(team_news_handle)

    # Shutdown
    if app_state.provider_cache:
        app_state.provider_cache.clear()
        logger.info("✓ Cleared provider cache")
        app_state.provider_cache = None


app = FastAPI(
    title="TUTAR X API",
    description="TUTAR X - Maçın geleceğini veriden oku. Professional football analytics and prediction platform.",
    version="0.1.0",
    lifespan=lifespan,
)

# Make app_state accessible
app.state.app_state = app_state

# CORS middleware
# Origins come from CORS_ORIGINS (JSON list in .env, see backend/.env.example).
# A wildcard origin must never be combined with credentials.
_cors_origins = [origin.strip() for origin in settings.cors_origins if origin and origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials="*" not in _cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API v1 router
app.include_router(api_router)


@app.get("/health")
async def health_check():
    """Health check endpoint with real database connectivity verification."""
    from app.database.session import get_session_factory

    # Check service initialization
    service_status = "healthy" if app_state.ingestion_service else "not_initialized"

    # Perform actual database connectivity test
    database_status = "unknown"
    database_details = {}

    try:
        session_factory = get_session_factory()
        with session_factory() as session:
            # Execute a simple query to verify database connectivity
            from app.database.models import Team as TeamDB
            team_count = session.query(TeamDB).count()

            database_status = "connected"
            database_details = {
                "teams_count": team_count,
                "connection_verified": True
            }

            # Add warning for empty teams table in production
            if team_count == 0:
                database_details["warning"] = "Teams table is empty - team ID resolution will fail"
                # Log this as a warning for monitoring
                import logging
                logger = logging.getLogger(__name__)
                logger.warning("Production database teams table is empty - this will cause team ID resolution failures")
    except Exception:
        # Never return raw exception text (it can leak DSNs, file paths, SQL).
        # Full detail goes to the server log only.
        import logging
        logging.getLogger(__name__).exception("Health check: database connectivity test failed")
        database_status = "connection_failed"
        database_details = {
            "error": "Database connectivity check failed. See server logs for details.",
            "connection_verified": False
        }

    # Overall health determination
    overall_status = "healthy" if (service_status == "healthy" and database_status == "connected") else "degraded"

    return {
        "status": overall_status,
        "service": "TUTAR X API",
        "version": "0.1.0",
        "database": database_status,
        "database_details": database_details,
        "ingestion_service": service_status,
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "TUTAR X API",
        "version": "0.1.0",
        "docs": "/docs",
    }
