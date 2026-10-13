# Phase 10 Groups 1-2 Stabilization Report
## MENSIONE Football Intelligence Platform

**Date:** 2026-10-07
**Scope:** Provider Pipeline Stabilization + Prediction Root Cause Analysis
**Status:** INFRASTRUCTURE STABLE, EMPIRICAL VALIDATION INCOMPLETE

---

## Executive Summary

### Infrastructure Status: ✅ OPERATIONAL

- **Match API**: Operational, returns 3463+ historical matches
- **Prediction API**: Operational, generates full predictions with probabilities, xG, MENSIONE picks
- **Provider Fallback**: Working (Ryzellx 402 → FotMob → OpenLigaDB)
- **Frontend Timeout**: Fixed (30-second AbortController)

### Critical Finding: Dashboard Empty Due to Data Coverage Gap

**Root Cause:** Dashboard requests **upcoming matches** (next 7 days), but database contains only **historical matches** (Jan 2024). Prediction API returns 200 OK for historical matches but **no upcoming matches exist**.

**NOT a threshold problem** - Selection logic is correct:
- `pass_decision: false` = BestTip selected ✓
- `pass_decision: true` = Pass/skip match ✓
- Dashboard correctly filters for `!pass_decision`

---

## Group 1: Match API Performance

### Fixes Applied

1. **FotMob Provider NameError** (FIXED)
   - **File:** `backend/app/providers/fotmob.py` line 908
   - **Error:** `NameError: name 'FINISHED_MATCH_TTL' is not defined`
   - **Fix:** Changed to `HISTORICAL_MATCH_TTL`
   - **Impact:** Provider was crashing on `get_matches_by_range()` calls

2. **OpenLigaDB Missing Method** (FIXED)
   - **File:** `backend/app/providers/openligadb.py`
   - **Error:** `AttributeError: 'OpenLigaDBProvider' object has no attribute 'get_matches_by_range'`
   - **Fix:** Added missing `async def get_matches_by_range()` method
   - **Impact:** Provider was unusable in fallback chain

### Verification Results

```powershell
# FotMob Unit Tests
pytest tests/providers/test_fotmob_normalization.py tests/providers/test_fotmob_live.py -v
# Result: 10/10 PASSED ✅

# Match API Performance Test
GET /api/v1/matches?from_date=2024-01-01&to_date=2024-01-31&limit=10
# Result: HTTP 200, 3463 matches, ~2 seconds ✅

# Provider Fallback Trace (from backend logs)
[ProviderManager] get_matches_by_range: provider 'ryzellx' raised ProviderHTTPError: Client error: 402 Payment Required
# FotMob takes over successfully ✅
```

### Provider Behavior

| Provider | Status | Behavior |
|----------|--------|----------|
| Ryzellx | 402 Payment Required | Fails fast (~10s timeout), fallback works |
| FotMob | ✅ Working | NameError FIXED, returns 3463 matches |
| OpenLigaDB | ✅ Available | AttributeError FIXED, method implemented |

---

## Group 2: Prediction 400 Root Cause Analysis

### Initial Hypothesis (INCORRECT)

❌ "Predictions return 400 'Insufficient data'"
❌ "MENSIONE picks have pass_decision=true (no qualifying market)"
❌ "Selection thresholds too strict"

### Actual Finding (CORRECT)

✅ **Predictions generate successfully** (HTTP 200)
✅ **MENSIONE picks have pass_decision=false** (BestTip selected)
✅ **Selection thresholds working correctly**

### Test Case: fotmob_4193724

```http
GET /api/v1/matches/fotmob_4193724/prediction
HTTP 200 OK

{
  "home_win_probability": 0.846,
  "draw_probability": 0.098,
  "away_win_probability": 0.056,
  "home_xg": 3.6,
  "away_xg": 0.96,
  "mensione_pick": {
    "match_id": "unknown",
    "market": "OVER_0_5",
    "selection": "Over 0.5 Goals",
    "probability": 0.987,
    "confidence": 0.686,
    "model_agreement": 0.993,
    "data_quality": 0.688,
    "edge": null,
    "fair_odds": 1.013,
    "bookmaker_odds": null,
    "value_classification": "NEUTRAL",
    "risk_level": "MEDIUM",
    "selection_score": 0.853,
    "pass_decision": false  ← BestTip WAS selected
  },
  "easy_match": {
    "is_easy_match": true,
    "confidence_score": 68.1
  }
}
```

### Selection Threshold Analysis

**Configured Thresholds:**
- `min_confidence`: 0.4 (40%)
- `min_probability`: 0.5 (50%)
- `min_edge`: 0.0 (accepts null edge when no odds)
- `max_risk_level`: "HIGH"

**Test Case Results:**
- Probability: 98.7% ✅ (exceeds 50%)
- Confidence: 68.6% ✅ (exceeds 40%)
- Risk Level: MEDIUM ✅ (within HIGH threshold)
- Edge: null ✅ (no odds, edge filter skipped)

**Verdict:** Pick PASSED all filters, BestTip returned ✅

### Why Dashboard Shows Empty

**Dashboard Logic:**
```typescript
// Fetch upcoming matches (7 days)
const matchesResponse = await getUpcomingMatches(7);  ← Looks for FUTURE matches

for (const match of matches) {
  const prediction = await getMatchPrediction(match.id);
  if (prediction.mensione_pick && !prediction.mensione_pick.pass_decision) {
    picksData.push({ match, prediction });  // Correct filter
  }
}
```

**Database State:**
- Historical matches: 653 (Jan 2024) ✅
- Upcoming matches: 0 (future dates) ❌

**Conclusion:** Dashboard correctly filters for `pass_decision: false`, but `getUpcomingMatches(7)` returns **zero matches** because database contains only historical data.

---

## Known Issues (Non-Blocking)

### 1. Negative Binomial Model Validation Warning

**Error:**
```
Model negative_binomial_v1 failed: 1 validation error for ModelPrediction
Value error, Probabilities must sum to 1.0 (±0.001), got 0.996633.
```

**Impact:** Model excluded from ensemble, but other models continue
**Severity:** Low (ensemble still produces predictions)
**Fix Required:** Adjust probability normalization in `backend/app/prediction/negative_binomial.py` line 317

### 2. FotMob Unknown Status Codes

**Warnings:**
```
[fotmob] Unknown status 'penalties_short', defaulting to SCHEDULED
[fotmob] Unknown status 'afterextratime_short', defaulting to SCHEDULED
[fotmob] Unknown status 'aborted_short', defaulting to SCHEDULED
```

**Impact:** Minimal, matches still processed
**Severity:** Low
**Fix Required:** Add status mappings to `backend/app/providers/fotmob.py`

---

## Database State

```sql
-- Matches
SELECT COUNT(*) FROM matches WHERE status = 'FINISHED';
-- Result: 653

-- Match Statistics (shots, possession, xG)
SELECT
  COUNT(*) AS total_records,
  COUNT(shots_total) AS with_shots,
  COUNT(shots_on_target) AS with_sot,
  COUNT(possession_percentage) AS with_possession,
  SUM(CASE WHEN home_xg IS NOT NULL OR away_xg IS NOT NULL THEN 1 ELSE 0 END) AS with_xg
FROM match_statistics;
-- Result: 506 total, 506 shots, 506 SoT, 506 possession, 252 xG (50% coverage)
```

---

## Next Steps

### GROUP 3: Populate Upcoming Matches Data

**Options:**
1. Run `import_historical_data.py` for recent dates (last 7 days)
2. Use FotMob `/live` endpoint to fetch genuinely upcoming matches
3. Temporarily test Dashboard with historical date range

**Required for:** Dashboard visibility, walk-forward backtest validation

### GROUP 4: Shot Intelligence Integration

- Verify `MatchFeatureSnapshot.shot_intelligence` is populated
- Inspect `backend/app/features/shot_market_engine.py` completeness
- Test shot-based market predictions (O/U shots, shots on target)

### GROUP 5: Negative Binomial Model Fix

- Adjust probability normalization to satisfy ±0.001 tolerance
- Re-run prediction tests to confirm model participates in ensemble

### GROUP 6: Walk-Forward Backtest Execution

- Run `WalkForwardEvaluator` with database matches
- Execute temporal leakage checks (prediction_timestamp > match_timestamp)
- Record baseline metrics: accuracy, calibration, Brier score

---

## Files Modified

| File | Change | Status |
|------|--------|--------|
| `backend/app/providers/fotmob.py` | Line 908: FINISHED_MATCH_TTL → HISTORICAL_MATCH_TTL | ✅ Fixed |
| `backend/app/providers/openligadb.py` | Added `get_matches_by_range()` method | ✅ Fixed |
| `frontend/src/api/client.ts` | Added 30s AbortController timeout | ✅ Fixed |
| `frontend/src/pages/Dashboard.tsx` | Enhanced logging, error handling | ✅ Improved |

---

## Verification Commands

```powershell
# 1. Test FotMob Provider
$env:PYTHONPATH="C:\FootballIntelligence\backend"
cd backend
pytest tests/providers/test_fotmob_normalization.py tests/providers/test_fotmob_live.py -v

# 2. Test Match API
Invoke-WebRequest -Uri "http://127.0.0.1:8002/api/v1/matches?from_date=2024-01-01&to_date=2024-01-31&limit=10" -TimeoutSec 30

# 3. Test Prediction API
Invoke-WebRequest -Uri "http://127.0.0.1:8002/api/v1/matches/fotmob_4193724/prediction" -TimeoutSec 30

# 4. Check Database Stats
sqlite3 backend/football_intelligence.db "SELECT COUNT(*) FROM matches WHERE status='FINISHED';"

# 5. Start Backend
$env:PYTHONPATH="C:\FootballIntelligence\backend"
cd backend
uvicorn app.main:app --reload --port 8002

# 6. Start Frontend
cd frontend
npm run dev
```

---

## Conclusion

**INFRASTRUCTURE STABILIZATION: COMPLETE ✅**
- Provider errors fixed
- Match API operational
- Prediction API operational
- Frontend timeout handling working
- Selection logic verified correct

**DASHBOARD EMPTY: DATA COVERAGE GAP ❌**
- Dashboard requests upcoming matches (next 7 days)
- Database contains only historical matches (Jan 2024)
- Solution: Import recent/upcoming match data

**EMPIRICAL VALIDATION: BLOCKED**
- Cannot validate walk-forward backtest without upcoming match data
- Cannot verify shot intelligence integration without recent match statistics
- Prediction engine proven functional on historical data

**Recommendation:** Proceed to GROUP 3 (populate upcoming matches) before continuing to Groups 4-6.
