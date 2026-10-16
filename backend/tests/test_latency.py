"""Tests for latency tracking."""

import pytest
from datetime import datetime, timezone, timedelta

from app.latency.tracker import LatencyTracker
from app.latency.models import LatencyMetrics


def test_latency_tracker_with_all_timestamps():
    """Test latency tracker with all timestamps available."""
    tracker = LatencyTracker()
    
    now = datetime.now(timezone.utc)
    provider_event = now - timedelta(seconds=5)
    provider_received = now - timedelta(seconds=4)
    
    tracker.track_provider_response(
        provider_event_timestamp=provider_event,
        provider_received_timestamp=provider_received,
        is_live=True,
        event_id="event_123"
    )
    
    tracker.track_storage()
    metrics = tracker.track_api_response()
    
    assert metrics.provider_event_timestamp == provider_event
    assert metrics.provider_received_timestamp == provider_received
    assert metrics.processing_timestamp is not None
    assert metrics.stored_timestamp is not None
    assert metrics.api_timestamp is not None
    
    # All metrics should be calculated
    assert metrics.provider_to_mensione_ms is not None
    assert metrics.provider_to_mensione_ms >= 0
    assert metrics.processing_ms is not None
    assert metrics.storage_ms is not None
    assert metrics.backend_to_frontend_ms is not None
    assert metrics.total_latency_ms is not None
    
    assert metrics.is_realtime is True
    assert metrics.event_id == "event_123"
    assert metrics.has_future_timestamp is False
    assert metrics.data_age_seconds is not None


def test_latency_tracker_missing_provider_event_timestamp():
    """Test latency tracker when provider event timestamp is unavailable."""
    tracker = LatencyTracker()
    
    now = datetime.now(timezone.utc)
    provider_received = now - timedelta(seconds=1)
    
    # No provider_event_timestamp
    tracker.track_provider_response(
        provider_event_timestamp=None,
        provider_received_timestamp=provider_received,
        is_live=False
    )
    
    tracker.track_storage()
    metrics = tracker.track_api_response()
    
    assert metrics.provider_event_timestamp is None
    assert metrics.provider_received_timestamp == provider_received
    
    # Metrics requiring provider_event_timestamp should be None
    assert metrics.provider_to_mensione_ms is None
    assert metrics.total_latency_ms is None
    assert metrics.data_age_seconds is None
    
    # Metrics not requiring provider_event_timestamp should be calculated
    assert metrics.processing_ms is not None
    assert metrics.storage_ms is not None
    assert metrics.backend_to_frontend_ms is not None


def test_latency_tracker_missing_provider_received_timestamp():
    """Test latency tracker when provider received timestamp is unavailable."""
    tracker = LatencyTracker()
    
    now = datetime.now(timezone.utc)
    provider_event = now - timedelta(seconds=5)
    
    # No provider_received_timestamp
    tracker.track_provider_response(
        provider_event_timestamp=provider_event,
        provider_received_timestamp=None,
        is_live=False
    )
    
    tracker.track_storage()
    metrics = tracker.track_api_response()
    
    assert metrics.provider_event_timestamp == provider_event
    assert metrics.provider_received_timestamp is None
    
    # Metrics requiring provider_received_timestamp should be None
    assert metrics.provider_to_mensione_ms is None
    assert metrics.processing_ms is None
    
    # Other metrics should be calculated where possible
    assert metrics.storage_ms is not None
    assert metrics.backend_to_frontend_ms is not None
    assert metrics.total_latency_ms is not None
    assert metrics.data_age_seconds is not None


def test_latency_tracker_future_timestamp_rejection():
    """Test latency tracker rejects future timestamps."""
    tracker = LatencyTracker()
    
    now = datetime.now(timezone.utc)
    # Future timestamp beyond grace period (5 seconds)
    provider_event = now + timedelta(seconds=10)
    provider_received = now - timedelta(seconds=1)
    
    tracker.track_provider_response(
        provider_event_timestamp=provider_event,
        provider_received_timestamp=provider_received,
        is_live=False
    )
    
    tracker.track_storage()
    metrics = tracker.track_api_response()
    
    assert metrics.has_future_timestamp is True
    assert metrics.notes is not None
    assert "future" in metrics.notes.lower()
    
    # Metrics involving future timestamp should be None
    assert metrics.provider_to_mensione_ms is None
    assert metrics.total_latency_ms is None


def test_latency_tracker_future_timestamp_within_grace():
    """Test latency tracker accepts timestamps within grace period."""
    tracker = LatencyTracker()
    
    now = datetime.now(timezone.utc)
    # Future timestamp within grace period (< 5 seconds)
    provider_event = now + timedelta(seconds=2)
    provider_received = now + timedelta(seconds=3)
    
    tracker.track_provider_response(
        provider_event_timestamp=provider_event,
        provider_received_timestamp=provider_received,
        is_live=False
    )
    
    tracker.track_storage()
    metrics = tracker.track_api_response()
    
    # Within grace period, should not be flagged as future
    assert metrics.has_future_timestamp is False
    assert metrics.provider_to_mensione_ms is not None


def test_latency_tracker_clock_skew_detection():
    """Test latency tracker detects clock skew between provider timestamps."""
    tracker = LatencyTracker()
    
    now = datetime.now(timezone.utc)
    provider_event = now - timedelta(seconds=100)  # 100s ago
    provider_received = now - timedelta(seconds=1)  # 1s ago
    # Delta = 99s > 60s threshold
    
    tracker.track_provider_response(
        provider_event_timestamp=provider_event,
        provider_received_timestamp=provider_received,
        is_live=False
    )
    
    tracker.track_storage()
    metrics = tracker.track_api_response()
    
    assert metrics.has_clock_skew is True
    assert metrics.notes is not None
    assert "skew" in metrics.notes.lower()
    
    # Metrics should still be calculated despite skew
    assert metrics.provider_to_mensione_ms is not None


def test_latency_tracker_no_clock_skew_normal():
    """Test latency tracker does not flag normal delays as clock skew."""
    tracker = LatencyTracker()
    
    now = datetime.now(timezone.utc)
    provider_event = now - timedelta(seconds=50)  # 50s ago
    provider_received = now - timedelta(seconds=1)  # 1s ago
    # Delta = 49s < 60s threshold
    
    tracker.track_provider_response(
        provider_event_timestamp=provider_event,
        provider_received_timestamp=provider_received,
        is_live=False
    )
    
    tracker.track_storage()
    metrics = tracker.track_api_response()
    
    assert metrics.has_clock_skew is False


def test_latency_tracker_get_data_age():
    """Test get_data_age_seconds method."""
    tracker = LatencyTracker()
    
    now = datetime.now(timezone.utc)
    provider_event = now - timedelta(seconds=30)
    
    tracker.track_provider_response(
        provider_event_timestamp=provider_event,
        provider_received_timestamp=now,
        is_live=False
    )
    
    age = tracker.get_data_age_seconds()
    assert age is not None
    assert age >= 30
    assert age < 35  # Allow small time delta


def test_latency_tracker_get_data_age_no_timestamp():
    """Test get_data_age_seconds returns None when no event timestamp."""
    tracker = LatencyTracker()
    
    tracker.track_provider_response(
        provider_event_timestamp=None,
        provider_received_timestamp=datetime.now(timezone.utc),
        is_live=False
    )
    
    age = tracker.get_data_age_seconds()
    assert age is None


def test_latency_metrics_model():
    """Test LatencyMetrics Pydantic model."""
    now = datetime.now(timezone.utc)
    
    metrics = LatencyMetrics(
        provider_event_timestamp=now,
        provider_received_timestamp=now + timedelta(seconds=1),
        processing_timestamp=now + timedelta(seconds=2),
        stored_timestamp=now + timedelta(seconds=3),
        api_timestamp=now + timedelta(seconds=4),
        provider_to_mensione_ms=1000.0,
        processing_ms=1000.0,
        storage_ms=1000.0,
        backend_to_frontend_ms=1000.0,
        total_latency_ms=4000.0,
        has_clock_skew=False,
        has_future_timestamp=False,
        is_realtime=True,
        data_age_seconds=10,
        event_id="test_event",
        notes="Test note"
    )
    
    assert metrics.provider_event_timestamp == now
    assert metrics.total_latency_ms == 4000.0
    assert metrics.is_realtime is True
    assert metrics.event_id == "test_event"
    
    # Test serialization
    data = metrics.model_dump()
    assert data["total_latency_ms"] == 4000.0
    assert data["is_realtime"] is True


def test_latency_metrics_with_nulls():
    """Test LatencyMetrics accepts None for optional fields."""
    metrics = LatencyMetrics(
        provider_event_timestamp=None,
        provider_received_timestamp=None,
        processing_timestamp=None,
        stored_timestamp=None,
        api_timestamp=None,
        provider_to_mensione_ms=None,
        processing_ms=None,
        storage_ms=None,
        backend_to_frontend_ms=None,
        total_latency_ms=None,
        has_clock_skew=False,
        has_future_timestamp=False,
        is_realtime=False,
        data_age_seconds=None,
        event_id=None,
        notes=None
    )
    
    assert metrics.provider_event_timestamp is None
    assert metrics.total_latency_ms is None
    assert metrics.is_realtime is False
