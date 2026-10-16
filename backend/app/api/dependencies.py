"""FastAPI dependency injection for API endpoints.

This module provides dependency injection functions for FastAPI routes.
These dependencies handle provider instantiation and other shared resources.
"""

import asyncio
from typing import Generator

from app.config import settings
from app.providers import (
    FootballDataProvider,
    DevelopmentProvider,
    RyzellxFootballProvider,
    FotMobFootballProvider,
    OpenLigaDBFootballProvider,
    ProviderManager,
    ProviderManagerAdapter,
    HybridProvider,
    ProviderCache,
)


def get_data_provider() -> Generator[FootballDataProvider, None, None]:
    """
    Dependency that provides the football data provider.
    
    Behavior is controlled by settings.use_real_providers:
    - False (default): Returns DevelopmentProvider (mock data, backward compatible)
    - True: Returns HybridProvider that tries external providers first, then falls back to database
    
    Yields:
        FootballDataProvider instance
    """
    if not settings.use_real_providers:
        # Backward compatible: use DevelopmentProvider (PHASE 1 behavior)
        provider = DevelopmentProvider()
        try:
            yield provider
        finally:
            pass
    else:
        # Hybrid provider: external providers + database fallback
        from sqlalchemy.orm import sessionmaker
        from app.database.session import engine
        
        # Create database session for hybrid provider - use existing SessionLocal
        from app.database.session import SessionLocal
        db_session = SessionLocal()
        
        try:
            # OPTIMIZATION: Use application-level cache shared across requests
            # instead of creating a new cache per request
            from app.main import app_state
            
            if app_state.provider_cache is None:
                # Fallback: create request-local cache if app cache not initialized
                # This can happen during testing or if app startup failed
                import logging
                logger = logging.getLogger(__name__)
                logger.warning("Application-level cache not initialized, using request-local cache")
                from app.providers.cache import ProviderCache
                cache = ProviderCache()
            else:
                cache = app_state.provider_cache
            
            # Create provider instances
            # NOTE: Ryzellx temporarily disabled due to 402 Payment Required errors
            # This significantly improves prediction performance (25s -> expected ~8s)
            ryzellx = None  # RyzellxFootballProvider(
            #     base_url=settings.ryzellx_base_url,
            #     timeout_seconds=settings.provider_timeout_seconds,
            #     retry_count=settings.provider_retry_count,
            #     cache=cache,
            # )
            
            fotmob = FotMobFootballProvider(
                base_url=settings.fotmob_base_url,
                timeout_seconds=settings.provider_timeout_seconds,
                retry_count=min(settings.provider_retry_count, 1),  # Cap at 1 for unofficial API
                cache=cache,
            )
            
            openligadb = OpenLigaDBFootballProvider(
                base_url=settings.openligadb_base_url,
                timeout_seconds=settings.provider_timeout_seconds,
                retry_count=settings.provider_retry_count,
                cache=cache,
            )
            
            # Create manager and adapter
            manager = ProviderManager(
                ryzellx=ryzellx,
                fotmob=fotmob,
                openligadb=openligadb,
                cache=cache,
            )
            
            external_adapter = ProviderManagerAdapter(manager=manager)
            
            # Create hybrid provider that combines external and database
            hybrid_provider = HybridProvider(
                external_provider=external_adapter,
                session=db_session
            )
            
            yield hybrid_provider
            
        finally:
            # Clean up database session
            db_session.close()

