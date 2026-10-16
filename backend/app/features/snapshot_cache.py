"""Feature snapshot cache for deduplicating feature calculations within a prediction request.

Temporal Validity:
- Cache keys include prediction_timestamp
- Features are NEVER reused across different prediction timestamps
- Cache is request-scoped (cleared after each prediction)

Thread Safety:
- Uses threading.local() for thread isolation
- Each request gets its own cache instance
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Dict, Tuple
import threading


@dataclass
class CacheKey:
    """Cache key for feature snapshot."""
    team_id: str
    window_type: str  # "recent", "medium", "season"
    prediction_timestamp: datetime
    calculator_type: str  # "team_intelligence", "shot_intelligence", etc.
    
    def to_tuple(self) -> Tuple:
        """Convert to hashable tuple."""
        # Bucket timestamp to minute precision to allow cache hits within same minute
        timestamp_bucket = self.prediction_timestamp.replace(second=0, microsecond=0)
        return (self.team_id, self.window_type, timestamp_bucket, self.calculator_type)


class FeatureSnapshotCache:
    """Request-scoped cache for feature calculator results.
    
    Usage:
        cache = FeatureSnapshotCache()
        
        # At start of prediction request
        cache.clear()
        
        # During feature extraction
        key = CacheKey(team_id, "recent", prediction_timestamp, "team_intelligence")
        cached = cache.get(key)
        if cached is None:
            result = expensive_calculator.calculate(...)
            cache.set(key, result)
        else:
            result = cached
        
        # At end of prediction request
        cache.clear()
    """
    
    def __init__(self):
        """Initialize thread-local cache storage."""
        self._local = threading.local()
    
    @property
    def _cache(self) -> Dict[Tuple, Any]:
        """Get thread-local cache dict."""
        if not hasattr(self._local, 'cache'):
            self._local.cache = {}
        return self._local.cache
    
    def get(self, key: CacheKey) -> Optional[Any]:
        """Get cached feature result.
        
        Args:
            key: Cache key
            
        Returns:
            Cached result or None if not found
        """
        return self._cache.get(key.to_tuple())
    
    def set(self, key: CacheKey, value: Any) -> None:
        """Store feature result in cache.
        
        Args:
            key: Cache key
            value: Feature calculator result
        """
        self._cache[key.to_tuple()] = value
    
    def clear(self) -> None:
        """Clear all cached features for this thread.
        
        MUST be called at the start and end of each prediction request
        to prevent temporal leakage across predictions.
        """
        self._cache.clear()
    
    def size(self) -> int:
        """Get current cache size."""
        return len(self._cache)
