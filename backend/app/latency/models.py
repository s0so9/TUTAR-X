"""Latency metrics models."""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class LatencyMetrics(BaseModel):
    """Latency metrics for data freshness tracking.
    
    Tracks latency from provider event timestamp through to API response.
    All timestamp fields are optional - they may not be available depending
    on provider support.
    
    All millisecond calculations are nullable: if either endpoint timestamp
    is missing, the metric is None.
    """
    
    # Timestamps (all optional, may not be available from all providers)
    provider_event_timestamp: Optional[datetime] = Field(
        None,
        description="When the event occurred according to provider"
    )
    provider_received_timestamp: Optional[datetime] = Field(
        None,
        description="When we received the data from provider"
    )
    processing_timestamp: Optional[datetime] = Field(
        None,
        description="When we started processing the data"
    )
    stored_timestamp: Optional[datetime] = Field(
        None,
        description="When data was stored in database"
    )
    api_timestamp: Optional[datetime] = Field(
        None,
        description="When API response was sent"
    )
    
    # Latency calculations (all optional, None if timestamps unavailable)
    provider_to_mensione_ms: Optional[float] = Field(
        None,
        description="Milliseconds from provider event to TUTAR X receipt (field name kept for backward compatibility)"
    )
    processing_ms: Optional[float] = Field(
        None,
        description="Milliseconds spent processing"
    )
    storage_ms: Optional[float] = Field(
        None,
        description="Milliseconds spent storing to database"
    )
    backend_to_frontend_ms: Optional[float] = Field(
        None,
        description="Milliseconds from stored to API response"
    )
    total_latency_ms: Optional[float] = Field(
        None,
        description="Total milliseconds from provider event to API response"
    )
    
    # Data quality flags
    has_clock_skew: bool = Field(
        False,
        description="True if unreasonable clock skew detected"
    )
    has_future_timestamp: bool = Field(
        False,
        description="True if provider timestamp is in the future"
    )
    is_realtime: bool = Field(
        False,
        description="True if data is from live source"
    )
    
    # Additional metadata
    data_age_seconds: Optional[int] = Field(
        None,
        description="Age of data in seconds (now - provider_event_timestamp)"
    )
    event_id: Optional[str] = Field(
        None,
        description="Event identifier for deduplication"
    )
    notes: Optional[str] = Field(
        None,
        description="Additional notes (e.g., warnings about data quality)"
    )
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "provider_event_timestamp": "2024-01-15T15:30:45.123Z",
                "provider_received_timestamp": "2024-01-15T15:30:46.456Z",
                "processing_timestamp": "2024-01-15T15:30:46.500Z",
                "stored_timestamp": "2024-01-15T15:30:46.600Z",
                "api_timestamp": "2024-01-15T15:30:46.650Z",
                "provider_to_mensione_ms": 1333.0,
                "processing_ms": 44.0,
                "storage_ms": 100.0,
                "backend_to_frontend_ms": 50.0,
                "total_latency_ms": 1527.0,
                "has_clock_skew": False,
                "has_future_timestamp": False,
                "is_realtime": True,
                "data_age_seconds": 120,
                "event_id": "goal_123",
                "notes": None,
            }
        }
