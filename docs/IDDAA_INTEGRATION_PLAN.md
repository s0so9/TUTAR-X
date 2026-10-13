# İDDAA ODDS INTEGRATION & OVER 0.5 FIX

**Date:** 2026-10-07
**Objective:** Integrate real İddaa odds and fix market selector to prioritize value over raw probability

---

## ROOT CAUSE ANALYSIS: OVER 0.5 DOMINANCE

### Finding

Located in `backend/app/prediction/market_selector.py` line 440-445:

```python
selection_score = (
    0.35 * probability +      # ← 35% weight on raw probability
    0.30 * confidence +
    0.20 * model_agreement +
    0.15 * data_quality
)
```

### Problem

1. **Probability dominates scoring** - 35% of score comes from raw probability
2. **OVER_0.5 has probability ~0.90-0.96** → base score ~0.32-0.34
3. **BTTS/1X2 have probability ~0.55-0.65** → base score ~0.19-0.23
4. **Edge bonus is tiny** - capped at 0.02 (10% of max 0.2 edge)
5. **No odds consideration in base formula** - bookmaker prices don't affect base score

### Result

OVER_0.5 wins by default due to high base-rate probability, regardless of value/price.

**GROUP 1 Validation:** 95.7% of picks were OVER_0.5
**GROUP 3 Baseline:** 80% of picks were OVER_0.5
**All confidence scores:** ~68% (suspiciously constant)

---

## SOLUTION ARCHITECTURE

### Phase 1: İddaa Odds Integration

#### 1.1 Database Schema Extension

Add odds table:

```python
class MatchOdds(Base):
    __tablename__ = "match_odds"

    id = Column(UUID, primary_key=True)
    match_id = Column(UUID, ForeignKey("matches.id"))
    provider = Column(String)  # "iddaa", "development", etc.

    # 1X2
    home_win_odds = Column(Float)
    draw_odds = Column(Float)
    away_win_odds = Column(Float)

    # Over/Under (multiple lines)
    over_under_line = Column(Float)  # 0.5, 1.5, 2.5, 3.5
    over_odds = Column(Float)
    under_odds = Column(Float)

    # BTTS
    btts_yes_odds = Column(Float)
    btts_no_odds = Column(Float)

    # Double Chance
    home_or_draw_odds = Column(Float)
    draw_or_away_odds = Column(Float)
    home_or_away_odds = Column(Float)

    # Timestamps (CRITICAL for temporal validation)
    odds_timestamp = Column(DateTime, nullable=False)  # When odds were published
    fetched_at = Column(DateTime, nullable=False)       # When we fetched them

    # Quality
    availability = Column(String)  # "available", "unavailable", "stale"
    data_quality = Column(Float)
```

#### 1.2 İddaa Provider (Future)

**Current Status:** NO İddaa provider exists

**Options:**
1. **Wait for official İddaa API** (if available)
2. **Use authorized third-party** (e.g., odds aggregator with İddaa data)
3. **Operate without odds** until provider is available

**Decision:** Implement odds-aware architecture NOW, use NULL odds until provider is ready

#### 1.3 Odds Service

```python
class OddsService:
    async def get_match_odds(match_id: str, timestamp: datetime) -> Optional[MatchOdds]:
        """Get odds for match at specific timestamp (temporal validation)."""

    async def get_implied_probability(market: str, odds: float) -> float:
        """Calculate implied probability from decimal odds."""
        return 1.0 / odds

    async def calculate_edge(
        model_prob: float,
        implied_prob: float
    ) -> float:
        """Calculate probability edge."""
        return model_prob - implied_prob

    async def calculate_expected_value(
        model_prob: float,
        odds: float
    ) -> float:
        """Calculate expected value."""
        return (model_prob * odds) - 1.0
```

---

### Phase 2: Market Selector Reconstruction

#### 2.1 New Selection Score Formula

**OLD (probability-dominated):**
```python
score = 0.35*prob + 0.30*conf + 0.20*agreement + 0.15*quality
```

**NEW (value-aware):**
```python
# Base score from reliability/confidence
base_score = (
    0.40 * confidence +
    0.30 * model_agreement +
    0.30 * data_quality
)

# Probability contribution (REDUCED from 35% to dynamic)
# Use Kelly-like criterion: weight by probability but cap contribution
prob_contribution = min(probability * 0.5, 0.35)  # Cap at 0.35

# Value contribution (when odds available)
if odds and odds > 0:
    implied_prob = 1.0 / odds
    edge = probability - implied_prob
    expected_value = (probability * odds) - 1.0

    # Strong value bonus
    if expected_value > 0.15:  # EV > 15%
        value_contribution = 0.25
    elif expected_value > 0.08:  # EV > 8%
        value_contribution = 0.15
    elif expected_value > 0.03:  # EV > 3%
        value_contribution = 0.08
    else:
        value_contribution = 0.0
else:
    value_contribution = 0.0  # No odds = no value bonus

# Final score
selection_score = base_score + prob_contribution + value_contribution
```

#### 2.2 High Base-Rate Market Protection

```python
# Identify high base-rate markets
HIGH_BASE_RATE_MARKETS = {'OVER_0_5', 'HOME_OR_AWAY'}

if market in HIGH_BASE_RATE_MARKETS:
    # Require stronger value to justify selection
    if odds:
        implied_prob = 1.0 / odds
        edge = probability - implied_prob

        # High base-rate markets need POSITIVE edge to be selected
        if edge <= 0.05:  # Less than 5% edge
            # Penalize score
            selection_score *= 0.7
```

#### 2.3 Market-Specific Reliability

Track performance separately per market:

```python
class MarketReliability:
    market_type: str  # "OVER_0_5", "BTTS_YES", "HOME_WIN", etc.
    sample_size: int
    hit_rate: float
    brier_score: float
    average_confidence: float
    average_edge: float
    roi: Optional[float]  # Only when odds available
```

Use market reliability in selection:

```python
market_reliability = get_market_reliability(market_type)

if market_reliability.sample_size < 30:
    # Insufficient historical sample
    selection_score *= 0.8  # Penalty for unproven markets
elif market_reliability.brier_score > 0.25:
    # Poor calibration
    selection_score *= 0.6
```

#### 2.4 Enhanced PASS Logic

```python
# PASS when no value
if odds:
    best_ev = max([c['expected_value'] for c in candidates if c['expected_value']])

    if best_ev < 0.03:  # No market has EV > 3%
        return PassDecision(
            match_id=match_id,
            pass_reason="insufficient_value",
            best_market_details={...}
        )

# PASS when high uncertainty
if uncertainty > 0.70:
    return PassDecision(
        match_id=match_id,
        pass_reason="high_uncertainty",
        ...
    )

# PASS when poor data quality
if data_quality < 0.40:
    return PassDecision(
        match_id=match_id,
        pass_reason="insufficient_data",
        ...
    )
```

---

### Phase 3: Candidate Diagnostics

Add detailed candidate evaluation tracking:

```python
@dataclass
class CandidateEvaluation:
    market: str
    selection: str

    # Probabilities
    model_probability: float
    calibrated_probability: float
    implied_probability: Optional[float]

    # Odds
    fair_odds: float
    bookmaker_odds: Optional[float]

    # Value
    edge: Optional[float]
    expected_value: Optional[float]

    # Reliability
    confidence: float
    model_agreement: float
    data_quality: float
    market_reliability: Optional[float]
    uncertainty: float

    # Scoring
    base_score: float
    probability_contribution: float
    value_contribution: float
    reliability_penalty: float
    selection_score: float

    # Decision
    qualified: bool
    rejection_reason: Optional[str]
    selection_reason: Optional[str]
```

Store all evaluations for debugging:

```json
{
  "match_id": "fotmob_6097137",
  "candidates": [
    {
      "market": "OVER_0_5",
      "model_probability": 0.964,
      "bookmaker_odds": 1.05,
      "implied_probability": 0.952,
      "edge": 0.012,
      "expected_value": 0.012,
      "selection_score": 0.723,
      "qualified": false,
      "rejection_reason": "insufficient_value (EV=1.2% < threshold 3%)"
    },
    {
      "market": "BTTS_YES",
      "model_probability": 0.634,
      "bookmaker_odds": 1.72,
      "implied_probability": 0.581,
      "edge": 0.053,
      "expected_value": 0.090,
      "selection_score": 0.817,
      "qualified": true,
      "selection_reason": "best_value (EV=9.0%, edge=5.3%)"
    }
  ],
  "selected": "BTTS_YES"
}
```

---

## IMPLEMENTATION STEPS

### Step 1: Database Migration
- [ ] Create MatchOdds table
- [ ] Add odds_timestamp, fetched_at columns
- [ ] Run migration

### Step 2: Odds Service
- [ ] Implement OddsService with implied_prob, edge, EV calculations
- [ ] Add temporal validation (odds_timestamp <= prediction_timestamp)
- [ ] Create fallback for missing odds (NULL, not fabricated)

### Step 3: Market Selector Refactor
- [ ] Implement new selection_score formula (value-aware)
- [ ] Add high base-rate market protection
- [ ] Implement market-specific reliability tracking
- [ ] Enhanced PASS logic (value threshold, uncertainty, data quality)
- [ ] Add CandidateEvaluation diagnostics

### Step 4: Market Reliability System
- [ ] Extend existing market reliability to track per-market performance
- [ ] Separate tracking for OVER_0_5, BTTS, 1X2, etc.
- [ ] Calculate Brier score, hit rate, ROI per market
- [ ] Use reliability in selection scoring

### Step 5: Confidence Fix Investigation
- [ ] Investigate why all confidence ~68%
- [ ] Check confidence_engine for constant fallbacks
- [ ] Verify calibration data is being used
- [ ] Fix if needed

### Step 6: Testing
- [ ] Unit tests: odds calculations (implied prob, edge, EV)
- [ ] Unit tests: new selection scoring
- [ ] Unit tests: high base-rate protection
- [ ] Integration tests: OVER_0_5 vs BTTS selection
- [ ] Temporal validation tests
- [ ] API validation tests

### Step 7: Walk-Forward Validation
- [ ] Run GROUP 3 backtest with new selector
- [ ] Measure market distribution (OVER_0_5, BTTS, 1X2, etc.)
- [ ] Calculate per-market hit rate, Brier score
- [ ] Compare OLD vs NEW selector performance
- [ ] Validate PASS frequency increases appropriately

---

## SUCCESS CRITERIA

### NOT Success:
- ❌ OVER_0.5 disappears completely
- ❌ Random market distribution
- ❌ Lower overall accuracy

### IS Success:
- ✅ OVER_0.5 selected when justified by value/odds
- ✅ Markets compete fairly based on calibrated_prob + edge + reliability
- ✅ PASS becomes common when no value exists
- ✅ Market diversity increases (BTTS, 1X2, OVER_1_5, etc. get fair chances)
- ✅ Selection scores are explainable and traceable
- ✅ No fabricated odds
- ✅ Temporal validation enforced
- ✅ Out-of-sample metrics improve or remain stable

### Metrics to Track:

**Market Distribution:**
- OVER_0_5: X% → Y%
- OVER_1_5: X% → Y%
- OVER_2_5: X% → Y%
- BTTS: X% → Y%
- 1X2: X% → Y%
- PASS: X% → Y%

**Performance:**
- Overall hit rate
- Brier score per market
- Calibration curves
- ROI (when odds available)
- Market-specific reliability

---

## TEMPORAL VALIDATION RULES

For every prediction at time T:

```python
# Rule 1: Feature timestamp < T
assert feature_snapshot.timestamp < prediction_timestamp

# Rule 2: Odds timestamp <= T
assert odds.odds_timestamp <= prediction_timestamp

# Rule 3: Market reliability uses only data before T
market_reliability = calculate_reliability(
    historical_predictions.filter(timestamp < prediction_timestamp)
)

# Rule 4: No future match data
assert not uses_future_match_result(feature_extraction)
```

---

## ODDS PROVIDER DECISION

**Current Reality:**
- No İddaa provider exists in codebase
- Cannot legally scrape İddaa website
- No official İddaa API available

**Implementation Decision:**
1. **Build odds-aware architecture NOW** (selection scoring, edge, EV, etc.)
2. **Use NULL odds** until provider is available
3. **System operates without odds** but selection logic is ready
4. **When provider becomes available** → plug in seamlessly

**Fallback Behavior:**
```python
if odds is None:
    # No odds available
    edge = None
    expected_value = None
    value_contribution = 0.0
    value_classification = "NEUTRAL"

    # Selector still works, just without value component
    selection_score = base_score + probability_contribution
```

---

## FILES TO MODIFY

1. `backend/app/database/models.py` - Add MatchOdds table
2. `backend/app/prediction/market_selector.py` - Refactor selection logic
3. `backend/app/prediction/market_reliability.py` - Per-market tracking
4. `backend/app/services/odds_service.py` - NEW: Odds utilities
5. `backend/app/prediction/confidence_engine.py` - Fix constant confidence
6. `backend/tests/test_market_selector.py` - Update tests
7. `backend/scripts/group3_walk_forward_backtest.py` - Add outcome evaluation

---

## NEXT ACTIONS

1. Create database migration for MatchOdds
2. Implement OddsService with value calculations
3. Refactor SmartMarketSelector with new formula
4. Add candidate diagnostics
5. Run tests
6. Run GROUP 3 validation OLD vs NEW
7. Document results
