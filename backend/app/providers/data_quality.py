"""Data quality engine for statistics validation and quality scoring.

This module provides pure calculation-based data quality checks for provider statistics.
NO HTTP calls, NO async operations, NO provider dependencies.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from app.providers.models import ProviderMatchStats, ProviderMetadata


class DataQualityEngine:
    """Pure calculation engine for data quality validation and scoring.
    
    Evaluates provider statistics across multiple dimensions:
    - Completeness: percentage of expected fields present
    - Consistency: logical validation of field relationships
    - Freshness: age of data based on fetch timestamp
    - Source conflicts: field-level disagreements across providers
    - Quality score: deterministic weighted combination
    
    This class is synchronous and has no external dependencies.
    """
    
    # Expected statistics fields for complete match data
    EXPECTED_STATS_FIELDS = [
        'goals_scored',
        'goals_conceded',
        'xg',
        'xg_against',
        'shots_total',
        'shots_on_target',
        'shots_off_target',
        'shots_blocked',
        'possession_percentage',
        'passes_completed',
        'passes_attempted',
        'pass_accuracy',
        'corners',
        'free_kicks',
        'offsides',
        'yellow_cards',
        'red_cards',
        'fouls_committed',
        'tackles',
        'interceptions',
        'clearances',
        'saves',
    ]
    
    def check_completeness(self, stats: ProviderMatchStats) -> Dict[str, Any]:
        """Check what percentage of expected statistics fields are present.
        
        Args:
            stats: Provider match statistics to evaluate
            
        Returns:
            Dict containing:
                - available (int): count of non-None expected fields
                - expected (int): total count of expected fields
                - ratio (float): available / expected (0.0 to 1.0)
                - missing_fields (List[str]): list of None fields
        """
        available = 0
        missing_fields = []
        
        for field in self.EXPECTED_STATS_FIELDS:
            value = getattr(stats, field, None)
            if value is not None:
                available += 1
            else:
                missing_fields.append(field)
        
        expected = len(self.EXPECTED_STATS_FIELDS)
        ratio = available / expected if expected > 0 else 0.0
        
        return {
            'available': available,
            'expected': expected,
            'ratio': ratio,
            'missing_fields': missing_fields,
        }
    
    def check_consistency(self, stats: ProviderMatchStats) -> Dict[str, Any]:
        """Check logical consistency of statistics values.
        
        Validates relationships such as:
        - shots_on_target <= shots_total
        - shots_off_target <= shots_total
        - shots_blocked <= shots_total
        - 0 <= possession_percentage <= 100
        - xg >= 0
        - goals_scored >= 0
        - all count fields >= 0
        
        Args:
            stats: Provider match statistics to validate
            
        Returns:
            Dict containing:
                - violations (List[str]): human-readable violation descriptions
                - is_consistent (bool): True if no violations found
        """
        violations = []
        
        # Shot consistency checks
        if stats.shots_on_target is not None and stats.shots_total is not None:
            if stats.shots_on_target > stats.shots_total:
                violations.append(
                    f'shots_on_target ({stats.shots_on_target}) > shots_total ({stats.shots_total})'
                )
        
        if stats.shots_off_target is not None and stats.shots_total is not None:
            if stats.shots_off_target > stats.shots_total:
                violations.append(
                    f'shots_off_target ({stats.shots_off_target}) > shots_total ({stats.shots_total})'
                )
        
        if stats.shots_blocked is not None and stats.shots_total is not None:
            if stats.shots_blocked > stats.shots_total:
                violations.append(
                    f'shots_blocked ({stats.shots_blocked}) > shots_total ({stats.shots_total})'
                )
        
        # Possession percentage range check
        if stats.possession_percentage is not None:
            if not (0 <= stats.possession_percentage <= 100):
                violations.append(
                    f'possession_percentage ({stats.possession_percentage}) not in range [0, 100]'
                )
        
        # xG non-negative check
        if stats.xg is not None:
            if stats.xg < 0:
                violations.append(f'xg ({stats.xg}) < 0')
        
        if stats.xg_against is not None:
            if stats.xg_against < 0:
                violations.append(f'xg_against ({stats.xg_against}) < 0')
        
        # Goals non-negative check
        if stats.goals_scored is not None:
            if stats.goals_scored < 0:
                violations.append(f'goals_scored ({stats.goals_scored}) < 0')
        
        if stats.goals_conceded is not None:
            if stats.goals_conceded < 0:
                violations.append(f'goals_conceded ({stats.goals_conceded}) < 0')
        
        # Count fields non-negative checks
        count_fields = [
            'passes_completed',
            'passes_attempted',
            'corners',
            'free_kicks',
            'offsides',
            'yellow_cards',
            'red_cards',
            'fouls_committed',
            'tackles',
            'interceptions',
            'clearances',
            'saves',
        ]
        
        for field in count_fields:
            value = getattr(stats, field, None)
            if value is not None and value < 0:
                violations.append(f'{field} ({value}) < 0')
        
        # Pass accuracy consistency
        if stats.pass_accuracy is not None:
            if not (0 <= stats.pass_accuracy <= 100):
                violations.append(
                    f'pass_accuracy ({stats.pass_accuracy}) not in range [0, 100]'
                )
        
        return {
            'violations': violations,
            'is_consistent': len(violations) == 0,
        }
    
    def check_freshness(
        self,
        metadata: ProviderMetadata,
        max_age_seconds: int = 300
    ) -> bool:
        """Check if data is fresh based on fetch timestamp.
        
        Args:
            metadata: Provider metadata containing fetched_at timestamp
            max_age_seconds: Maximum acceptable age in seconds (default: 300 = 5 minutes)
            
        Returns:
            True if data age <= max_age_seconds, False otherwise
        """
        now = datetime.now(timezone.utc)
        
        # Ensure fetched_at is timezone-aware
        fetched_at = metadata.fetched_at
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        
        age_seconds = (now - fetched_at).total_seconds()
        return age_seconds <= max_age_seconds
    
    def detect_source_conflicts(
        self,
        stats_list: List[ProviderMatchStats]
    ) -> Dict[str, Any]:
        """Detect field-level disagreements across multiple provider sources.
        
        For each expected statistics field, collects values from all providers
        where the field is not None. If values differ across providers, records
        a conflict.
        
        Args:
            stats_list: List of provider statistics for the same match/team
            
        Returns:
            Dict containing:
                - conflicts (List[Dict]): list of field conflicts, each with:
                    - field (str): field name
                    - values (List[Dict]): list of {provider, value} dicts
                - has_conflicts (bool): True if any conflicts found
        """
        conflicts = []
        
        for field in self.EXPECTED_STATS_FIELDS:
            # Collect all non-None values for this field
            field_values = []
            
            for stats in stats_list:
                value = getattr(stats, field, None)
                if value is not None:
                    field_values.append({
                        'provider': stats.provider,
                        'value': value,
                    })
            
            # Check if values differ
            if len(field_values) > 1:
                unique_values = set(item['value'] for item in field_values)
                if len(unique_values) > 1:
                    conflicts.append({
                        'field': field,
                        'values': field_values,
                    })
        
        return {
            'conflicts': conflicts,
            'has_conflicts': len(conflicts) > 0,
        }
    
    def calculate_quality_score(
        self,
        completeness: Dict[str, Any],
        consistency: Dict[str, Any],
        freshness: bool
    ) -> Dict[str, Any]:
        """Calculate deterministic data quality score.
        
        Formula:
            completeness_score = completeness['ratio'] * 100  (0-100)
            consistency_score = 100 if consistent else max(0, 100 - violations * 20)
            freshness_score = 100 if fresh else 50
            overall = (completeness * 0.4) + (consistency * 0.4) + (freshness * 0.2)
        
        Weights:
            - Completeness: 40% (having data is critical)
            - Consistency: 40% (data must be logically valid)
            - Freshness: 20% (age matters less than correctness)
        
        Args:
            completeness: Result from check_completeness()
            consistency: Result from check_consistency()
            freshness: Result from check_freshness()
            
        Returns:
            Dict containing:
                - overall (float): weighted overall score (0-100)
                - completeness (float): completeness component score (0-100)
                - consistency (float): consistency component score (0-100)
                - freshness (float): freshness component score (0-100)
        """
        # Completeness score: 0-100 based on field availability ratio
        completeness_score = completeness['ratio'] * 100
        
        # Consistency score: 100 if valid, deduct 20 points per violation
        if consistency['is_consistent']:
            consistency_score = 100.0
        else:
            violation_count = len(consistency['violations'])
            consistency_score = max(0.0, 100.0 - (violation_count * 20))
        
        # Freshness score: 100 if fresh, 50 if stale
        freshness_score = 100.0 if freshness else 50.0
        
        # Weighted overall score
        overall = (
            completeness_score * 0.4 +
            consistency_score * 0.4 +
            freshness_score * 0.2
        )
        
        return {
            'overall': overall,
            'completeness': completeness_score,
            'consistency': consistency_score,
            'freshness': freshness_score,
        }
