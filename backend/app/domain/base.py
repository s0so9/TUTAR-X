"""Base domain models."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class BaseEntity(BaseModel):
    """Base entity with common fields."""

    id: str = Field(..., description="Unique identifier")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    class Config:
        """Pydantic configuration."""

        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "entity_123",
                "created_at": "2026-10-03T12:00:00",
                "updated_at": "2026-10-03T12:00:00",
            }
        }


class DataQualityMetadata(BaseModel):
    """Data quality and source metadata."""

    source: str = Field(..., description="Data source identifier")
    fetched_at: datetime = Field(..., description="Data fetch timestamp")
    freshness_seconds: Optional[int] = Field(None, description="Data age in seconds")
    confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Data confidence score"
    )
    provider: Optional[str] = Field(None, description="Data provider name")

    class Config:
        """Pydantic configuration."""

        from_attributes = True
