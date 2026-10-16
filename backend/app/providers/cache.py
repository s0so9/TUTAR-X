"""Simple in-memory TTL cache for provider data.

Thread-safe implementation using threading.Lock.
Designed for development and low-volume production use.
For high-traffic production, consider Redis or similar.
"""

import threading
from datetime import datetime, timedelta
from typing import Optional, Any, Dict


# TTL constants (in seconds)
LIVE_DATA_TTL = 30  # 30 seconds for live match data
UPCOMING_FIXTURES_TTL = 300  # 5 minutes for upcoming fixtures
HISTORICAL_MATCH_TTL = 3600  # 1 hour for finished matches
METADATA_TTL = 3600  # 1 hour for league/team/player metadata


class CacheEntry:
    """Cache entry with value and expiry timestamp."""
    
    def __init__(self, value: Any, expires_at: datetime):
        self.value = value
        self.expires_at = expires_at
    
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return datetime.utcnow() > self.expires_at


class ProviderCache:
    """Thread-safe in-memory TTL cache for provider data.
    
    This cache is designed to reduce redundant API calls to external providers.
    Each entry has a TTL (time-to-live) after which it expires.
    
    Thread-safety is ensured using a threading.Lock for all operations.
    
    Example usage:
        cache = ProviderCache()
        
        # Set with TTL
        cache.set("match:123", match_data, ttl_seconds=300)
        
        # Get (returns None if expired or not found)
        data = cache.get("match:123")
        
        # Delete specific key
        cache.delete("match:123")
        
        # Clear all
        cache.clear()
    """
    
    def __init__(self):
        self._store: Dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value if exists and not expired, None otherwise
        """
        with self._lock:
            entry = self._store.get(key)
            
            if entry is None:
                return None
            
            if entry.is_expired():
                # Clean up expired entry
                del self._store[key]
                return None
            
            return entry.value
    
    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Set value in cache with TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time-to-live in seconds
        """
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        
        with self._lock:
            self._store[key] = CacheEntry(value, expires_at)
    
    def delete(self, key: str) -> None:
        """Delete specific key from cache.
        
        Args:
            key: Cache key to delete
        """
        with self._lock:
            self._store.pop(key, None)
    
    def clear(self) -> None:
        """Clear all entries from cache."""
        with self._lock:
            self._store.clear()
    
    def cleanup_expired(self) -> int:
        """Remove all expired entries from cache.
        
        Returns:
            Number of expired entries removed
        """
        now = datetime.utcnow()
        expired_keys = []
        
        with self._lock:
            for key, entry in self._store.items():
                if entry.expires_at <= now:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._store[key]
        
        return len(expired_keys)
    
    def size(self) -> int:
        """Get current number of entries in cache (including expired).
        
        Returns:
            Number of entries
        """
        with self._lock:
            return len(self._store)
    
    def __repr__(self) -> str:
        return f"ProviderCache(size={self.size()})"
