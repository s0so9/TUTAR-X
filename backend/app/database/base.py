"""Database base classes and utilities."""

from datetime import datetime, timezone
from typing import Any
import uuid

from sqlalchemy import Column, DateTime, String
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import declarative_base

# Base for all ORM models
Base = declarative_base()


class TimestampMixin:
    """Mixin that adds created_at and updated_at timestamps.
    
    All timestamps are stored in UTC.
    """
    
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class BaseModel(TimestampMixin):
    """Base model with UUID primary key and timestamps.
    
    All models inherit from this to get:
    - UUID primary key
    - created_at timestamp (UTC)
    - updated_at timestamp (UTC, auto-updates on modification)
    """
    
    __abstract__ = True
    
    @declared_attr
    def id(cls):
        """UUID primary key."""
        return Column(
            String(36),
            primary_key=True,
            default=lambda: str(uuid.uuid4()),
        )


def utc_now() -> datetime:
    """Get current UTC datetime.
    
    Helper function for consistent UTC timestamp generation.
    
    Returns:
        Current datetime in UTC timezone
    """
    return datetime.now(timezone.utc)
