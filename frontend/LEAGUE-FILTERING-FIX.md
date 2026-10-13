# League Filtering and Scheduled Match Score Bug Fixes

**Date:** 2026-10-07
**Status:** ✅ FIXED AND TESTED

## Root Cause Analysis

### Problem 1: League Filtering Not Working

**Symptom:** When selecting a league (e.g., Premier League), matches from completely different leagues/competitions were displayed (e.g., J-League matches with competition_id 9011, Uruguayan matches with competition_id 10342, etc.).

**Root Cause:**
1. Backend is using **real providers** (`USE_REAL_PROVIDERS=true`)
2. The `ProviderManagerAdapter.get_matches_async()` method **IGNORES the `competition_id` parameter**
3. Backend comment explicitly states: `"NOT YET SUPPORTED: - competition_id, season_id, team_id filtering"`
4. The adapter fetches ALL matches for the date range and returns them unfiltered
5. Frontend was displaying whatever the backend returned without client-side validation

**Evidence:**
```python
# backend/app/providers/adapter.py line 188
async def get_matches_async(
    self,
    competition_id: Optional[str] = None,  # <-- IGNORED
    season_id: Optional[str] = None,       # <-- IGNORED
    team_id: Optional[str] = None,         # <-- IGNORED
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    status: Optional[str] = None,
) -> List[Match]:
    # ... fetches ALL matches, no competition_id filtering
```

### Problem 2: Scheduled Matches Displaying Fake Scores

**Symptom:** Scheduled matches displayed scores like "0 - 0", "2 - 1", "2 - 2" even though they haven't been played yet.

**Root Cause:**
1. Real provider (FotMob/Ryzellx) returns `home_score` and `away_score` values even for scheduled matches
2. Frontend checked `match.homeScore !== null && match.awayScore !== null` to decide whether to show scores
3. This check passed for scheduled matches if the backend returned numeric values
4. Frontend needs to check **match status** first, not just null values

### Problem 3: Raw Numeric Competition IDs Displayed

**Symptom:** Competition names showed as raw provider IDs like "9011", "10342", "530" instead of proper league names or fallback text.

**Root Cause:**
1. Match `competition_id` from real providers (e.g., "9011") doesn't match the competitions list IDs
2. `formatCompetitionName()` utility only handles dev patterns like `"dev_comp_xxx"`
3. Numeric IDs passed through unchanged
4. No fallback for unknown numeric IDs

## Solution Implemented

### Fix 1: Client-Side Competition Filtering

**File:** `frontend/src/pages/Matches.tsx`

**Changes:**
1. Removed `competition_id` parameter from API call (backend ignores it anyway)
2. Fetch ALL matches for the date range
3. Apply **explicit client-side filter**: `matches.filter(match => match.competitionId === selectedCompetitionId)`
4. Added AbortController to cancel in-flight requests when league changes
5. Added logging to show total fetched vs. filtered count

**Code:**
```typescript
// Backend adapter does NOT filter by competition_id correctly
// We MUST fetch all matches and filter client-side
const response = await getMatches({
  from_date: fromDate,
  to_date: toDate,
  status: 'scheduled',
});

const normalizedMatches = normalizeMatches(response.matches);

// CRITICAL: Client-side filtering by exact competition_id match
const filteredMatches = normalizedMatches.filter(
  match => match.competitionId === selectedCompetitionId
);
```

### Fix 2: Status-Based Score Display Logic

**File:** `frontend/src/pages/Matches.tsx`

**Changes:**
1. Check `match.status` FIRST before checking score values
2. Only show scores for `status === 'finished'` or `status === 'live'`
3. Always show "vs" for `status === 'scheduled'` regardless of score values in the response

**Code:**
```typescript
{/* CRITICAL: Scheduled matches must NEVER show scores */}
{match.status === 'finished' && match.homeScore !== null && match.awayScore !== null ? (
  <div className="match-score">
    {match.homeScore} - {match.awayScore}
  </div>
) : match.status === 'live' && match.homeScore !== null && match.awayScore !== null ? (
  <div className="match-score">
    {match.homeScore} - {match.awayScore}
  </div>
) : (
  <span className="vs-text">vs</span>
)}
```

### Fix 3: Competition Name Fallback Logic

**File:** `frontend/src/pages/Matches.tsx`

**Changes:**
1. Look up competition name from the loaded `competitions` array first
2. If found, use `competition.name`
3. If NOT found and ID is numeric (`/^\d+$/`), show `"Lig bilgisi yok"`
4. Otherwise, fall back to `formatCompetitionName()` for dev patterns

**Code:**
```typescript
{(() => {
  // Find the competition name from the competitions list
  const competition = competitions.find(c => c.id === match.competitionId);
  if (competition) {
    return competition.name;
  }
  // Fallback: format the ID if not found
  // But NEVER display raw numeric provider IDs
  if (/^\d+$/.test(match.competitionId)) {
    return 'Lig bilgisi yok';
  }
  return formatCompetitionName(match.competitionId);
})()}
```

## Tests Added

**File:** `frontend/src/pages/__tests__/Matches.test.tsx`

**Test Coverage:**
1. ✅ Premier League selection filters correctly
2. ✅ Bundesliga selection filters correctly
3. ✅ Switching leagues removes previous league matches
4. ✅ Empty state when no matches for selected league
5. ✅ Scheduled matches do NOT show scores even if backend returns them
6. ✅ Finished matches DO show actual scores
7. ✅ Raw numeric competition IDs show "Lig bilgisi yok"

**Test Results:**
```
✓ src/pages/__tests__/Matches.test.tsx (7)
  ✓ Matches Page - League Filtering (4)
  ✓ Matches Page - Scheduled Match Score Bug (2)
  ✓ Matches Page - Raw Competition ID Display Bug (1)

Test Files  1 passed (1)
Tests  7 passed (7)
```

## Verification Steps

### TypeScript Compilation
```bash
cd frontend
npx tsc --noEmit
```
✅ **Result:** No errors

### Test Execution
```bash
cd frontend
npx vitest run src/pages/__tests__/Matches.test.tsx
```
✅ **Result:** All 7 tests passed

### Production Build
```bash
cd frontend
npx vite build
```
✅ **Result:** Build succeeded (285KB bundle)

### Browser Testing (Required)

**Test Scenario 1: League Filtering**
1. Open http://localhost:5173/matches
2. Select "Premier League"
3. ✅ Verify ONLY Premier League matches appear
4. ✅ Verify no J-League, Bundesliga, or other league matches
5. Select "Bundesliga"
6. ✅ Verify ONLY Bundesliga matches appear
7. ✅ Verify Premier League matches are gone

**Test Scenario 2: Scheduled Match Scores**
1. Select any league with scheduled matches
2. ✅ Verify scheduled matches show "vs", NOT "0 - 0" or other scores
3. ✅ Verify finished matches (if any) DO show real scores like "3 - 2"

**Test Scenario 3: Competition Names**
1. Browse all matches
2. ✅ Verify NO raw numeric IDs like "9011", "10342", "530" appear as competition names
3. ✅ Verify either proper league names or "Lig bilgisi yok" appear

**Test Scenario 4: Race Conditions**
1. Rapidly switch between leagues (Premier League → Bundesliga → Premier League)
2. ✅ Verify matches update correctly
3. ✅ Verify no stale results from previous league remain
4. ✅ Verify no "mixed league" results appear

## Files Changed

- ✅ `frontend/src/pages/Matches.tsx` - Core fixes
- ✅ `frontend/src/pages/__tests__/Matches.test.tsx` - Test coverage

## Files NOT Changed (As Per Requirements)

- ❌ Backend files (user explicitly forbid backend changes)
- ❌ Backend endpoints (user explicitly forbid new endpoints)
- ❌ UI components (user explicitly forbid UI redesign)
- ❌ API client (no hardcoded IDs added)

## Known Limitations

1. **Backend Still Returns Unfiltered Results**: The real fix should be in `backend/app/providers/adapter.py` to implement `competition_id` filtering, but user requirements forbid backend changes.

2. **Performance**: Client-side filtering means the frontend fetches ALL matches for the date range, then filters them. This works fine for reasonable match counts but could be optimized by fixing the backend.

3. **Competition ID Mismatches**: If a match's `competition_id` doesn't match any ID in `/api/v1/competitions`, it won't be displayed (by design - correct behavior).

## Recommendations for Backend Team

When backend filtering is implemented, update `backend/app/providers/adapter.py`:

```python
async def get_matches_async(
    self,
    competition_id: Optional[str] = None,
    # ...
) -> List[Match]:
    # ... fetch matches ...

    # TODO: Implement competition_id filtering here
    if competition_id:
        matches = [m for m in matches if m.competition_id == competition_id]

    return matches
```

Once backend filtering works, the frontend can remove client-side filtering and rely on the backend.
