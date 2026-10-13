import { useEffect, useRef } from 'react';
import { getMatchPrediction } from '../api/client';
import { usePredictionCache } from '../contexts/PredictionCacheContext';

function isAbortError(err: unknown): boolean {
  return (
    (err instanceof DOMException && err.name === 'AbortError') ||
    (err instanceof Error && err.name === 'AbortError')
  );
}

/**
 * Hook for lazy-loading predictions on demand.
 *
 * Fetches the prediction when nothing is cached or in flight for the match.
 * The cache lives in PredictionCacheProvider (above the routes), so results and
 * cleanup are always written to it, even after this component unmounted:
 * - an aborted request always clears its "loading" entry, otherwise a later
 *   visit would wait forever for a request that no longer exists;
 * - a component that waits for another component's request re-checks the cache
 *   on every cache update and fetches itself if that request was aborted.
 *
 * REACT STRICTMODE SAFE: the request is aborted only on unmount / match change,
 * not when the cache entry changes.
 */
export function useLazyPrediction(matchId: string | null | undefined) {
  const cache = usePredictionCache();
  const { getPrediction, isLoading, setLoading, setPrediction, clearLoading, setError } = cache;
  const abortControllerRef = useRef<AbortController | null>(null);

  // Re-evaluated on every cache update (the provider re-renders its consumers).
  const needsFetch = !!matchId && !getPrediction(matchId) && !isLoading(matchId);

  // Abort this instance's request on unmount or when the match changes.
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
    };
  }, [matchId]);

  useEffect(() => {
    if (!matchId || !needsFetch) return;
    // Re-check the live cache: render-time values can be stale (e.g. StrictMode double effects).
    if (getPrediction(matchId) || isLoading(matchId)) return;

    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    setLoading(matchId);

    getMatchPrediction(matchId, abortController.signal)
      .then((prediction) => {
        setPrediction(matchId, prediction);
      })
      .catch((err: unknown) => {
        if (abortController.signal.aborted) {
          // Always clear, mounted or not: a stale loading entry blocks every later visit.
          clearLoading(matchId);
          return;
        }
        if (isAbortError(err)) {
          // Abort that did not come from this hook: record it as an error instead of
          // clearing, so the hook does not immediately re-request in a loop.
          setError(matchId, new Error('Tahmin isteği iptal edildi'));
          return;
        }
        setError(matchId, err instanceof Error ? err : new Error('Failed to fetch prediction'));
      })
      .finally(() => {
        if (abortControllerRef.current === abortController) {
          abortControllerRef.current = null;
        }
      });
  }, [matchId, needsFetch, getPrediction, isLoading, setLoading, setPrediction, clearLoading, setError]); // cache callbacks are stable (useCallback with [])

  // Return cached state
  if (!matchId) {
    return { prediction: null, loading: false, error: null };
  }

  const cached = cache.getPrediction(matchId);
  return {
    prediction: cached?.prediction ?? null,
    loading: cached?.loading ?? needsFetch,
    error: cached?.error ?? null,
  };
}
