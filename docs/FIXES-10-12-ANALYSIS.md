# Fixes 10-12 Analysis

**Date:** 2026-10-12
**Status:** ANALYSIS COMPLETE - REQUIRES USER DECISION

---

## Summary

Fixes 7-9 implemented and committed (4825b52). Fixes 10-12 require architectural decisions due to:
- Database migrations (Fix #10)
- Data normalization requirements (Fix #11)
- Framework design changes (Fix #12)

---

## Fix #10: PredictionVersionManager Persistence

**File:** `backend/app/prediction/version_manager.py`
**Line:** 128 - `PredictionVersionManager(persistence_service=None)`

### Current State
```python
self.version_manager = PredictionVersionManager(persistence_service=None)  # In-memory for now
```

### Problem
- No database persistence for prediction versions
- Prediction history is lost on service restart
- Cannot track prediction accuracy over time
- Settlement and backtesting impossible without persistence

### Required Changes

**1. Database Schema** (NEW TABLE)
```sql
CREATE TABLE prediction_versions (
    id UUID PRIMARY KEY,
    match_id VARCHAR NOT NULL,
    version_number INTEGER NOT NULL,
    prediction_data JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL,
    model_version VARCHAR NOT NULL,
    ensemble_config JSONB,
    calibration_status VARCHAR,
    FOREIGN KEY (match_id) REFERENCES matches(provider_match_id),
    UNIQUE(match_id, version_number)
);

CREATE INDEX idx_prediction_versions_match ON prediction_versions(match_id);
CREATE INDEX idx_prediction_versions_created ON prediction_versions(created_at);
```

**2. Implementation Changes**
- Create `backend/app/database/prediction_repository.py`
- Create `backend/app/services/prediction_persistence.py`
- Update `PredictionVersionManager` to accept real persistence service
- Implement `PredictionPersistenceService` with SQLAlchemy

**3. Migration Required**
- Alembic migration script
- Backward compatibility handling (nullable foreign key initially)

### Complexity: **HIGH**
### Risk: **MEDIUM** (new table, no existing data migration)
### Estimated Effort: **2-3 hours**

---

## Fix #11: BTTS Settlement Parsing

**File:** `backend/app/settlement/settlement.py`
**Line:** 164 - BTTS outcome parsing from text

### Current State
```python
# Parsing BTTS from text like "Her İki Takım da Gol Atar"
if "Her İki Takım" in outcome_text or "BTTS" in outcome_text:
    # Parse outcome...
```

### Problem
- Text-based outcome matching is fragile
- Turkish/English mixing causes issues
- No canonical outcome IDs
- Settlement accuracy depends on text format stability

### Required Changes

**1. Canonical Outcome Enumeration**
```python
class BTTSOutcome(Enum):
    YES = "btts_yes"
    NO = "btts_no"

class MarketOutcomeMap:
    BTTS = {
        "yes": BTTSOutcome.YES,
        "no": BTTSOutcome.NO
    }
```

**2. Database Normalization**
```sql
-- Add canonical_outcome_id to prediction_markets
ALTER TABLE prediction_markets
ADD COLUMN canonical_outcome_id VARCHAR;

-- Update existing data
UPDATE prediction_markets
SET canonical_outcome_id = 'btts_yes'
WHERE market_type = 'BTTS' AND outcome_text LIKE '%Atar%';

UPDATE prediction_markets
SET canonical_outcome_id = 'btts_no'
WHERE market_type = 'BTTS' AND outcome_text LIKE '%Atmaz%';
```

**3. Settlement Refactoring**
- Update `MatchOutcomeExtractor` to set canonical IDs
- Update `SettlementEngine` to use canonical IDs
- Maintain backward compatibility with text-based matching

### Complexity: **HIGH**
### Risk: **MEDIUM-HIGH** (existing prediction data migration)
### Estimated Effort: **3-4 hours**

### Dependencies
- Requires Fix #10 (prediction persistence) for full value
- Existing prediction data needs migration

---

## Fix #12: Walk-Forward Backtest Framework

**File:** `backend/scripts/walk_forward.py`
**Multiple lines:** Parameter mismatches, temporal leakage risks

### Current State
```python
def run_walk_forward_validation(
    train_window_days: int = 90,
    test_window_days: int = 30,
    # ... other params
):
    # Implementation has temporal leakage risks
    # Parameters don't match actual usage
```

### Problems Identified

**1. Temporal Leakage**
- Training data may include future information
- Match timestamps not strictly enforced
- Calibration training uses "future" data

**2. Parameter Mismatches**
- Function signature doesn't match docstring
- Default values inconsistent with usage
- Optional parameters missing

**3. Missing Validation**
- No verification that train/test split is clean
- No check for data availability in windows
- No validation of temporal ordering

### Required Changes

**1. Temporal Safety Framework**
```python
class TemporalSplitter:
    """Ensures clean temporal splits for backtesting."""

    def validate_split(
        self,
        train_end: datetime,
        test_start: datetime,
        test_end: datetime
    ) -> ValidationResult:
        """Verify no temporal overlap or leakage."""
        pass

    def get_available_data_range(
        self,
        team_id: str,
        before: datetime
    ) -> DateRange:
        """Get data range available before cutoff."""
        pass
```

**2. Walk-Forward Redesign**
```python
@dataclass
class WalkForwardConfig:
    """Configuration for walk-forward validation."""
    train_window_days: int = 90
    test_window_days: int = 30
    step_size_days: int = 7
    min_train_matches: int = 30
    min_test_matches: int = 10

    def validate(self) -> None:
        """Validate configuration consistency."""
        pass

def run_walk_forward_validation(
    config: WalkForwardConfig,
    league_ids: List[str],
    output_dir: Path,
    temporal_validator: TemporalSplitter
) -> WalkForwardResult:
    """Run walk-forward validation with temporal safety."""
    pass
```

**3. Integration with Fix #10**
- Requires prediction persistence to store historical predictions
- Settlement requires Fix #11 canonical IDs
- Calibration training must respect temporal boundaries

### Complexity: **VERY HIGH**
### Risk: **HIGH** (affects backtesting validity, research integrity)
### Estimated Effort: **6-8 hours**

### Dependencies
- **REQUIRES Fix #10** (prediction persistence)
- **REQUIRES Fix #11** (settlement with canonical IDs)
- Needs comprehensive testing framework
- Requires validation of existing backtest results

---

## Recommendation

### Immediate Action (This Session)
**NONE** - Fixes 10-12 require architectural planning

### Suggested Approach

**Option A: Implement in Order (Fix #10 → #11 → #12)**
- **Pros:** Each fix builds on previous, logical progression
- **Cons:** Long session, high complexity accumulation
- **Time:** 11-15 hours total

**Option B: Skip to Lower-Hanging Fruit**
- **Pros:** Quick wins, incremental value
- **Cons:** Fixes 10-12 remain unaddressed
- **Recommendation:** Implement Fix #8 variants (ensemble)

**Option C: User Decision Required**
- **Best for:** Complex fixes requiring product decisions
- **Recommended:** Get user input on:
  - Prediction persistence priority (Fix #10)
  - Settlement accuracy urgency (Fix #11)
  - Backtest framework redesign scope (Fix #12)

---

## Current Status

✅ **Fixes 1-9 COMPLETE**
- All implemented, tested (35/35 passing)
- Committed: ebd355d (fixes 1-6), 4825b52 (fixes 7-9)
- Production-ready

⚠️ **Fixes 10-12 BLOCKED - USER DECISION REQUIRED**
- Fix #10: Database migration + persistence service
- Fix #11: Data normalization + canonical IDs
- Fix #12: Framework redesign + temporal safety

---

## Questions for User

1. **Priority:** Which fix (10, 11, or 12) has highest business value?
2. **Scope:** Should these be implemented now or in separate sprint?
3. **Migration:** Acceptable to run database migrations on production?
4. **Testing:** How to validate backtest framework changes (Fix #12)?
5. **Dependencies:** OK to implement Fix #10 as prerequisite for #11 and #12?
