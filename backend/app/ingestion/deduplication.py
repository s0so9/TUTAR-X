"""Deduplication logic for ingestion.

Prevents data loss by never overwriting valid (non-None) fields with None values.
"""

from typing import Optional, Any
from datetime import datetime


class DeduplicationChecker:
    """Check for duplicate data and determine update strategy.
    
    Implements the core rule: NEVER overwrite non-None with None.
    """
    
    @staticmethod
    def should_preserve_field(
        existing_value: Optional[Any],
        new_value: Optional[Any]
    ) -> bool:
        """Determine if existing field value should be preserved.
        
        Rule: If existing value is not None and new value is None,
        preserve the existing value (don't overwrite with None).
        
        Args:
            existing_value: Current value in database
            new_value: New value from provider
            
        Returns:
            True if existing value should be preserved, False if it should be updated
        """
        if existing_value is not None and new_value is None:
            # Don't overwrite valid data with None
            return True
        return False
    
    @staticmethod
    def should_update(
        existing_fetched_at: Optional[datetime],
        new_fetched_at: Optional[datetime],
        existing_updated_at: Optional[datetime],
        new_updated_at: Optional[datetime]
    ) -> bool:
        """Determine if entity should be updated based on timestamps.
        
        Update if:
        - new_fetched_at is more recent than existing_fetched_at, OR
        - new_updated_at is more recent than existing_updated_at
        
        Args:
            existing_fetched_at: When existing data was fetched
            new_fetched_at: When new data was fetched
            existing_updated_at: When provider last updated existing data
            new_updated_at: When provider last updated new data
            
        Returns:
            True if should update, False otherwise
        """
        # If no timestamp info, default to update
        if not existing_fetched_at and not existing_updated_at:
            return True
        
        # Check if new fetch is more recent
        if new_fetched_at and existing_fetched_at:
            if new_fetched_at > existing_fetched_at:
                return True
        
        # Check if provider's update timestamp is more recent
        if new_updated_at and existing_updated_at:
            if new_updated_at > existing_updated_at:
                return True
        
        # Default to update if we have new data
        return True
