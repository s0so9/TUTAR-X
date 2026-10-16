"""Latency tracking utilities."""

from typing import Optional
from datetime import datetime, timezone, timedelta

from app.latency.models import LatencyMetrics


class LatencyTracker:
    """Track latency metrics for provider data.
    
    Usage:
        tracker = LatencyTracker()
        tracker.track_provider_response(provider_match)
        # ... process data ...
        tracker.track_storage()
        # ... generate API response ...
        metrics = tracker.track_api_response()
    """
    
    # Grace period for future timestamp detection (5 seconds)
    FUTURE_GRACE_SECONDS = 5
    
    # Maximum reasonable latency between stages (60 seconds)
    SKEW_THRESHOLD_SECONDS = 60
    
    def __init__(self):
        """Initialize latency tracker."""
        self.provider_event_timestamp: Optional[datetime] = None
        self.provider_received_timestamp: Optional[datetime] = None
        self.processing_timestamp: Optional[datetime] = None
        self.stored_timestamp: Optional[datetime] = None
        self.api_timestamp: Optional[datetime] = None
        
        self.has_clock_skew: bool = False
        self.has_future_timestamp: bool = False
        self.is_realtime: bool = False
        self.event_id: Optional[str] = None
        self.notes: Optional[str] = None
    
    def track_provider_response(
        self,
        provider_event_timestamp: Optional[datetime] = None,
        provider_received_timestamp: Optional[datetime] = None,
        is_live: bool = False,
        event_id: Optional[str] = None
    ):
        """Track provider response receipt.
        
        Args:
            provider_event_timestamp: When event occurred (from provider's source_updated_at)
            provider_received_timestamp: When we received data (from provider's fetched_at)
            is_live: Whether data is from live source
            event_id: Optional event identifier
        """
        self.provider_event_timestamp = provider_event_timestamp
        self.provider_received_timestamp = provider_received_timestamp
        self.processing_timestamp = datetime.now(timezone.utc)
        self.is_realtime = is_live
        self.event_id = event_id
        
        # Detect future timestamps
        if provider_event_timestamp:
            now = datetime.now(timezone.utc)
            grace = timedelta(seconds=self.FUTURE_GRACE_SECONDS)
            
            if provider_event_timestamp > (now + grace):
                self.has_future_timestamp = True
                self.notes = f"Provider event timestamp is in future: {provider_event_timestamp.isoformat()}"
        
        # Detect clock skew between provider timestamps
        if provider_event_timestamp and provider_received_timestamp:
            delta = abs((provider_received_timestamp - provider_event_timestamp).total_seconds())
            if delta > self.SKEW_THRESHOLD_SECONDS:
                self.has_clock_skew = True
                if not self.notes:
                    self.notes = f"Clock skew detected: {delta:.1f}s between event and receipt"
    
    def track_storage(self):
        """Track database storage completion."""
        self.stored_timestamp = datetime.now(timezone.utc)
    
    def track_api_response(self) -> LatencyMetrics:
        """Track API response and calculate final metrics.
        
        Returns:
            LatencyMetrics with all calculated values
        """
        self.api_timestamp = datetime.now(timezone.utc)
        
        # Calculate latency metrics (all nullable)
        provider_to_mensione_ms = None
        if self.provider_event_timestamp and self.provider_received_timestamp:
            provider_to_mensione_ms = (
                self.provider_received_timestamp - self.provider_event_timestamp
            ).total_seconds() * 1000
        
        processing_ms = None
        if self.provider_received_timestamp and self.processing_timestamp:
            processing_ms = (
                self.processing_timestamp - self.provider_received_timestamp
            ).total_seconds() * 1000
        
        storage_ms = None
        if self.processing_timestamp and self.stored_timestamp:
            storage_ms = (
                self.stored_timestamp - self.processing_timestamp
            ).total_seconds() * 1000
        
        backend_to_frontend_ms = None
        if self.stored_timestamp and self.api_timestamp:
            backend_to_frontend_ms = (
                self.api_timestamp - self.stored_timestamp
            ).total_seconds() * 1000
        
        total_latency_ms = None
        if self.provider_event_timestamp and self.api_timestamp:
            total_latency_ms = (
                self.api_timestamp - self.provider_event_timestamp
            ).total_seconds() * 1000
        
        # Calculate data age
        data_age_seconds = None
        if self.provider_event_timestamp:
            now = datetime.now(timezone.utc)
            data_age_seconds = int((now - self.provider_event_timestamp).total_seconds())
        
        # If future timestamp detected, set provider_to_mensione_ms to None
        if self.has_future_timestamp:
            provider_to_mensione_ms = None
            total_latency_ms = None
        
        return LatencyMetrics(
            provider_event_timestamp=self.provider_event_timestamp,
            provider_received_timestamp=self.provider_received_timestamp,
            processing_timestamp=self.processing_timestamp,
            stored_timestamp=self.stored_timestamp,
            api_timestamp=self.api_timestamp,
            provider_to_mensione_ms=provider_to_mensione_ms,
            processing_ms=processing_ms,
            storage_ms=storage_ms,
            backend_to_frontend_ms=backend_to_frontend_ms,
            total_latency_ms=total_latency_ms,
            has_clock_skew=self.has_clock_skew,
            has_future_timestamp=self.has_future_timestamp,
            is_realtime=self.is_realtime,
            data_age_seconds=data_age_seconds,
            event_id=self.event_id,
            notes=self.notes,
        )
    
    def get_data_age_seconds(self) -> Optional[int]:
        """Get current age of data in seconds.
        
        Returns:
            Age in seconds, or None if provider_event_timestamp unavailable
        """
        if not self.provider_event_timestamp:
            return None
        
        now = datetime.now(timezone.utc)
        return int((now - self.provider_event_timestamp).total_seconds())
