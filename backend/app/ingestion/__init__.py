"""Ingestion module for persisting provider data to database."""

from app.ingestion.service import IngestionService, IngestionResult

__all__ = [
    "IngestionService",
    "IngestionResult",
]
