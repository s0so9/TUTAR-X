# Prediction Loading Bug Fix Report

**Date:** 2026-10-07
**Issue:** Match cards stuck at "Tahmin hazırlanıyor..." (Prediction loading...) indefinitely

## Root Cause

The prediction loading state became permanently stuck when requests were aborted during React component mount/unmount cycles. This commonly happened in:

1. **React StrictMode** - double-mount behavior in development
2. **Rapid navigation** - user navigating away before prediction loads
3. **Component remounts** - any scenario where the MatchDetail component unmounts quickly

### Technical Details

In `useLazyPrediction.ts`, when an AbortError occurred:
- The catch block detected the abort and returned early (lines 61-67)
- However, it **did NOT clear the `inFlightRef`** in `PredictionCacheContext`
- The `cache.setLoading(matchId)` call on line 50 added the match ID to `inFlightRef`
- When aborted, the code just returned without calling `setError()` or any cleanup
- Result: `inFlightRef` still contained the match ID
- Future component mounts checked `cache.isLoading(matchId)` which returned `true`
- These mounts would skip fetching entirely (line 34)
- The UI showed `loading: true` **forever** with no retry mechanism

## The Fix

### 1. Added `clearLoading()` method to PredictionCacheContext

**File:** `frontend/src/contexts/PredictionCacheContext.tsx`

```typescript
// New method added to interface
clearLoading: (matchId: string) => void;

// Implementation
const clearLoading = useCallback((matchId: string) => {
  inFlightRef.current.delete(matchId); // Clear in-flight tracking
  cacheRef.current.delete(matchId); // Remove from cache entirely
  forceUpdate({}); // Trigger re-render
}, []);
```

This method:
- Removes the match ID from `inFlightRef` (allowing future requests)
- Removes the entry from cache entirely (no stale loading state)
- Triggers a re-render to update all components

### 2. Updated useLazyPrediction to call clearLoading() on abort

**File:** `frontend/src/hooks/useLazyPrediction.ts`

```typescript
catch (err) {
  // Don't update cache if request was aborted (component unmounted)
  if (err instanceof DOMException && err.name === 'AbortError') {
    // CRITICAL FIX: Clear loading state on abort to prevent stuck loading
    // This clears inFlightRef so future mounts can retry
    cache.clearLoading(matchId);
    return;
  }

  // Check ApiError wrapped AbortError
  if (err instanceof Error && err.message.includes('aborted')) {
    // CRITICAL FIX: Clear loading state on abort
    cache.clearLoading(matchId);
    return;
  }

  // Store error in cache
  if (!abortController.signal.aborted) {
    cache.setError(
      matchId,
      err instanceof Error ? err : new Error('Failed to fetch prediction')
    );
  } else {
    // Aborted but didn't throw AbortError - still need to clear loading state
    cache.clearLoading(matchId);
  }
}
```

Now when a request is aborted:
- `clearLoading()` is called immediately
- `inFlightRef` is cleared
- Cache entry is removed
- Future mounts can retry the request
- No permanent stuck loading state

## Files Changed

1. `frontend/src/contexts/PredictionCacheContext.tsx`
   - Added `clearLoading()` method to interface and implementation
   - Exported method in Provider value

2. `frontend/src/hooks/useLazyPrediction.ts`
   - Replaced early returns in abort handlers with `cache.clearLoading(matchId)` calls
   - Removed debug logging
   - Simplified error retry logic

3. `frontend/src/hooks/useLazyPrediction.test.tsx` (NEW)
   - Added comprehensive tests for abort scenarios
   - Tests verify loading state doesn't get stuck
   - Tests verify retry works after abort

## Verification

### Tests
```
✓ should handle aborted requests and allow retry
✓ should not get stuck in loading state after abort
✓ should handle API errors without getting stuck

Test Files  1 passed (1)
Tests  3 passed (3)
```

### TypeScript
```
npx tsc --noEmit
Exit Code: 0 ✓
```

### Production Build
```
npx vite build
✓ built in 6.15s
dist/assets/index-BXhikcBD.js   289.42 kB │ gzip: 81.86 kB
```

## Behavior After Fix

### Before Fix
1. User navigates to match detail page
2. useLazyPrediction starts loading prediction
3. User quickly navigates away → AbortError
4. inFlightRef NOT cleared
5. User returns to same match
6. cache.isLoading() returns true → no retry
7. **STUCK**: "Tahmin hazırlanıyor..." forever

### After Fix
1. User navigates to match detail page
2. useLazyPrediction starts loading prediction
3. User quickly navigates away → AbortError
4. clearLoading() called → inFlightRef cleared, cache cleared
5. User returns to same match
6. cache.isLoading() returns false → retry starts
7. **SUCCESS**: Prediction loads normally

## Additional Notes

- No changes to Smart Market Selector
- No changes to prediction engine
- No mock data or hardcoded match IDs added
- Preserves existing caching and bounded concurrency
- Fix applies to all prediction loading scenarios (Dashboard preload, MatchDetail lazy load)
- Works correctly with React StrictMode double-mounting

## Performance Impact

- Negligible: only adds one `delete()` operation on abort
- No impact on successful requests
- Actually improves performance by preventing stuck states that required page refresh
