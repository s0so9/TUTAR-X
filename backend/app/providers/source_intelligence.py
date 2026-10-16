"""Source intelligence for multi-provider data merging and conflict detection.

This module provides synchronous utilities for intelligently merging statistics
from multiple providers, detecting disagreements, and tracking field sources.

NO HTTP calls, NO async operations, NO provider dependencies.
Pure calculation-based merging and conflict detection logic.
"""

from typing import List, Optional, Dict, Any

from app.domain.odds import Odds
from app.providers.models import ProviderMatchStats
from app.providers.data_quality import DataQualityEngine


class SourceIntelligence:
    """Pure calculation engine for multi-provider data merging and source tracking.
    
    Provides strategies for merging statistics from multiple providers:
    - 'first': First non-None value per field wins
    - 'most_complete': Provider with most non-None fields wins entirely
    - 'highest_quality': Provider with highest data quality score wins
    
    Also provides conflict detection and field source tracking.
    
    This class is synchronous and has no external dependencies.
    """
    
    def __init__(self):
        """Initialize SourceIntelligence with DataQualityEngine."""
        self.quality_engine = DataQualityEngine()
    
    def merge_statistics(
        self,
        stats_list: List[ProviderMatchStats],
        strategy: str = 'first'
    ) -> Optional[ProviderMatchStats]:
        """Merge statistics from multiple providers using specified strategy.
        
        Strategies:
        - 'first': First non-None value per field wins (field-by-field merge)
        - 'most_complete': Provider with most non-None fields wins entirely (whole provider)
        - 'highest_quality': Provider with highest quality score wins entirely (whole provider)
        
        Args:
            stats_list: List of ProviderMatchStats to merge
            strategy: Merge strategy ('first', 'most_complete', 'highest_quality')
            
        Returns:
            Merged ProviderMatchStats, or None if stats_list is empty
            
        Raises:
            ValueError: If strategy is not recognized
        """
        if not stats_list:
            return None
        
        if strategy == 'first':
            return self._merge_first(stats_list)
        elif strategy == 'most_complete':
            return self._merge_most_complete(stats_list)
        elif strategy == 'highest_quality':
            return self._merge_highest_quality(stats_list)
        else:
            raise ValueError(f"Unknown merge strategy: {strategy}")
    
    def _merge_first(
        self,
        stats_list: List[ProviderMatchStats]
    ) -> ProviderMatchStats:
        """Merge using 'first' strategy: first non-None value per field wins.
        
        This is a field-by-field merge where each field is taken from the first
        provider in the list that has a non-None value for that field.
        
        Args:
            stats_list: List of ProviderMatchStats to merge (non-empty)
            
        Returns:
            Merged ProviderMatchStats
        """
        # Start with a copy of the first provider's stats
        base = stats_list[0]
        
        # Create merged dict starting with base values
        merged_data = base.model_dump()
        
        # Get all fields from ProviderMatchStats
        fields = base.model_fields.keys()
        
        # For each field, use first non-None value from stats_list
        for field in fields:
            # Skip metadata fields - use first provider's metadata
            if field in ['provider', 'source_id', 'fetched_at', 'source_updated_at', 
                         'is_live', 'data_freshness_seconds', 'match_id', 'team_id', 
                         'team_name', 'period']:
                continue
            
            # Find first non-None value
            for stats in stats_list:
                value = getattr(stats, field, None)
                if value is not None:
                    merged_data[field] = value
                    break
        
        # Mark as merged by updating provider to "merged"
        merged_data['provider'] = 'merged'
        
        return ProviderMatchStats(**merged_data)
    
    def _merge_most_complete(
        self,
        stats_list: List[ProviderMatchStats]
    ) -> ProviderMatchStats:
        """Merge using 'most_complete' strategy: provider with most non-None fields wins.
        
        This selects the entire provider with the most available data fields.
        No field-by-field merging.
        
        Args:
            stats_list: List of ProviderMatchStats to merge (non-empty)
            
        Returns:
            The most complete ProviderMatchStats
        """
        best_stats = None
        best_count = -1
        
        for stats in stats_list:
            # Count non-None statistics fields
            completeness = self.quality_engine.check_completeness(stats)
            available = completeness['available']
            
            if available > best_count:
                best_count = available
                best_stats = stats
        
        return best_stats
    
    def _merge_highest_quality(
        self,
        stats_list: List[ProviderMatchStats]
    ) -> ProviderMatchStats:
        """Merge using 'highest_quality' strategy: provider with highest quality score wins.
        
        Uses DataQualityEngine to score each provider based on completeness and consistency.
        The provider with the highest overall quality score wins.
        No field-by-field merging.
        
        Args:
            stats_list: List of ProviderMatchStats to merge (non-empty)
            
        Returns:
            The highest quality ProviderMatchStats
        """
        best_stats = None
        best_score = -1.0
        
        for stats in stats_list:
            # Calculate quality score
            completeness = self.quality_engine.check_completeness(stats)
            consistency = self.quality_engine.check_consistency(stats)
            # Note: freshness not available here as we don't have metadata reference
            # Use True (fresh) as default for quality calculation
            quality = self.quality_engine.calculate_quality_score(
                completeness,
                consistency,
                freshness=True
            )
            
            score = quality['overall']
            
            if score > best_score:
                best_score = score
                best_stats = stats
        
        return best_stats
    
    def detect_conflicts(
        self,
        stats_list: List[ProviderMatchStats]
    ) -> Dict[str, List[Dict]]:
        """Detect field-level disagreements across multiple providers.
        
        For each field, checks if providers disagree on the value.
        Returns only fields where values differ across providers (excluding None values).
        
        Args:
            stats_list: List of ProviderMatchStats to compare
            
        Returns:
            Dict mapping field names to list of {provider, value} dicts for conflicting fields.
            Empty dict if no conflicts or if stats_list is empty.
            
        Example:
            {
                'shots_total': [
                    {'provider': 'fotmob', 'value': 14},
                    {'provider': 'sofascore', 'value': 15}
                ],
                'possession_percentage': [
                    {'provider': 'fotmob', 'value': 52.0},
                    {'provider': 'sofascore', 'value': 53.0}
                ]
            }
        """
        if not stats_list:
            return {}
        
        conflicts = {}
        
        # Get all fields from first provider
        fields = stats_list[0].model_fields.keys()
        
        # Skip metadata fields
        metadata_fields = ['provider', 'source_id', 'fetched_at', 'source_updated_at',
                          'is_live', 'data_freshness_seconds', 'match_id', 'team_id',
                          'team_name', 'period']
        
        for field in fields:
            if field in metadata_fields:
                continue
            
            # Collect all non-None values for this field
            field_values = []
            
            for stats in stats_list:
                value = getattr(stats, field, None)
                if value is not None:
                    field_values.append({
                        'provider': stats.provider,
                        'value': value
                    })
            
            # Check if values differ
            if len(field_values) > 1:
                # Extract unique values
                unique_values = set(item['value'] for item in field_values)
                if len(unique_values) > 1:
                    # Conflict detected
                    conflicts[field] = field_values
        
        return conflicts
    
    def get_field_sources(
        self,
        merged_stats: ProviderMatchStats,
        stats_list: List[ProviderMatchStats]
    ) -> Dict[str, str]:
        """Track which provider supplied each field in merged statistics.
        
        For each non-None field in merged_stats, finds which provider in stats_list
        supplied that value.
        
        Args:
            merged_stats: The merged ProviderMatchStats
            stats_list: Original list of ProviderMatchStats used for merging
            
        Returns:
            Dict mapping field names to provider names.
            Only includes fields with non-None values.
            
        Example:
            {
                'shots_total': 'sofascore',
                'possession_percentage': 'fotmob',
                'xg': 'sofascore'
            }
        """
        if not stats_list:
            return {}
        
        field_sources = {}
        
        # Get all fields
        fields = merged_stats.model_fields.keys()
        
        # Skip metadata fields
        metadata_fields = ['provider', 'source_id', 'fetched_at', 'source_updated_at',
                          'is_live', 'data_freshness_seconds', 'match_id', 'team_id',
                          'team_name', 'period']
        
        for field in fields:
            if field in metadata_fields:
                continue
            
            merged_value = getattr(merged_stats, field, None)
            if merged_value is None:
                continue
            
            # Find which provider supplied this value
            for stats in stats_list:
                provider_value = getattr(stats, field, None)
                if provider_value == merged_value:
                    field_sources[field] = stats.provider
                    break
        
        return field_sources
    
    def merge_bookmaker_odds(
        self,
        odds_list: List[Odds],
        strategy: str = 'first'
    ) -> Optional[Odds]:
        """Merge bookmaker odds from multiple sources using specified strategy.
        
        Follows same merge patterns as merge_statistics():
        - 'first': First non-None value per odds field wins (field-by-field merge)
        - 'most_complete': Provider with most non-None odds fields wins entirely
        - 'highest_quality': Provider with most non-None odds fields wins (uses completeness as quality proxy)
        
        Args:
            odds_list: List of Odds to merge
            strategy: Merge strategy ('first', 'most_complete', 'highest_quality')
            
        Returns:
            Merged Odds, or None if odds_list is empty
            
        Raises:
            ValueError: If strategy is not recognized
        """
        if not odds_list:
            return None
        
        if strategy == 'first':
            return self._merge_odds_first(odds_list)
        elif strategy == 'most_complete':
            return self._merge_odds_most_complete(odds_list)
        elif strategy == 'highest_quality':
            # For odds, we use completeness as quality proxy since DataQualityEngine
            # is designed for ProviderMatchStats. Delegate to most_complete.
            return self._merge_odds_most_complete(odds_list)
        else:
            raise ValueError(f"Unknown merge strategy: {strategy}")
    
    def _merge_odds_first(
        self,
        odds_list: List[Odds]
    ) -> Odds:
        """Merge odds using 'first' strategy: first non-None value per field wins.
        
        This is a field-by-field merge where each odds field is taken from the first
        provider in the list that has a non-None value for that field.
        
        Args:
            odds_list: List of Odds to merge (non-empty)
            
        Returns:
            Merged Odds
        """
        # Start with a copy of the first odds
        base = odds_list[0]
        
        # Create merged dict starting with base values
        merged_data = base.model_dump()
        
        # Get all fields from Odds model
        fields = base.model_fields.keys()
        
        # Odds fields that should be merged (not metadata)
        odds_fields = [
            'home_win_odds', 'draw_odds', 'away_win_odds',
            'over_under_line', 'over_odds', 'under_odds',
            'btts_yes_odds', 'btts_no_odds',
            'asian_handicap_line', 'asian_handicap_home_odds', 'asian_handicap_away_odds',
            # Phase 5 fields
            'source_provider', 'normalized_market_type', 'selection_label', 'odds_timestamp'
        ]
        
        # For each odds field, use first non-None value from odds_list
        for field in odds_fields:
            if field not in fields:
                continue
            
            # Find first non-None value
            for odds in odds_list:
                value = getattr(odds, field, None)
                if value is not None:
                    merged_data[field] = value
                    break
        
        # Update bookmaker to indicate merged source
        if len(odds_list) > 1:
            merged_data['bookmaker'] = 'merged'
            merged_data['source_provider'] = 'merged'
        
        return Odds(**merged_data)
    
    def _merge_odds_most_complete(
        self,
        odds_list: List[Odds]
    ) -> Odds:
        """Merge odds using 'most_complete' strategy: provider with most non-None odds fields wins.
        
        This selects the entire Odds object with the most available odds data.
        No field-by-field merging.
        
        Args:
            odds_list: List of Odds to merge (non-empty)
            
        Returns:
            The most complete Odds object
        """
        best_odds = None
        best_count = -1
        
        # Odds fields to count for completeness
        odds_fields = [
            'home_win_odds', 'draw_odds', 'away_win_odds',
            'over_under_line', 'over_odds', 'under_odds',
            'btts_yes_odds', 'btts_no_odds',
            'asian_handicap_line', 'asian_handicap_home_odds', 'asian_handicap_away_odds'
        ]
        
        for odds in odds_list:
            # Count non-None odds fields
            count = sum(
                1 for field in odds_fields
                if getattr(odds, field, None) is not None
            )
            
            if count > best_count:
                best_count = count
                best_odds = odds
        
        return best_odds
