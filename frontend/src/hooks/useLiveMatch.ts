/**
 * useLiveMatch Hook
 * 
 * Custom hook for polling live match data with connection status tracking
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { getLiveMatchDetail } from '../api/client';
import type { LiveMatchState, ConnectionStatus } from '../types/live';

const POLL_INTERVAL = 5000; // 5 seconds
const DELAYED_THRESHOLD = 10000; // 10 seconds
const ERROR_BACKOFF_MAX = 60000; // 60 seconds max backoff

interface UseLiveMatchResult {
  liveMatch: LiveMatchState | null;
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  connectionStatus: ConnectionStatus;
  refetch: () => Promise<void>;
}

interface UseLiveMatchOptions {
  enabled?: boolean;
  pollInterval?: number;
}

/**
 * Hook for fetching and polling live match data
 * 
 * @param matchId - Match ID to fetch
 * @param options - Configuration options
 * @returns Live match state with connection status
 */
export function useLiveMatch(
  matchId: string,
  options: UseLiveMatchOptions = {}
): UseLiveMatchResult {
  const { enabled = true, pollInterval = POLL_INTERVAL } = options;

  const [liveMatch, setLiveMatch] = useState<LiveMatchState | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('UPDATING');

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const errorCountRef = useRef<number>(0);
  const isVisibleRef = useRef<boolean>(true);
  const isMountedRef = useRef<boolean>(true);

  /**
   * Fetch live match data
   */
  const fetchLiveMatch = useCallback(async () => {
    if (!enabled) return;

    try {
      setConnectionStatus('UPDATING');
      
      const data = await getLiveMatchDetail(matchId);
      
      if (!isMountedRef.current) return;
      
      if (data) {
        setLiveMatch(data);
        setLastUpdated(new Date());
        setConnectionStatus('CONNECTED');
        setError(null);
        errorCountRef.current = 0; // Reset error count on success
      } else {
        // Match is not live
        setLiveMatch(null);
        setConnectionStatus('UNAVAILABLE');
        setError('Match is not currently live');
      }
      
      setLoading(false);
    } catch (err) {
      if (!isMountedRef.current) return;
      
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch live match data';
      setError(errorMessage);
      setConnectionStatus('UNAVAILABLE');
      setLoading(false);
      errorCountRef.current++;
      
      console.error('[useLiveMatch] Fetch error:', err);
    }
  }, [matchId, enabled]);

  /**
   * Calculate backoff delay based on error count
   */
  const getBackoffDelay = useCallback(() => {
    if (errorCountRef.current === 0) return pollInterval;
    
    // Exponential backoff: 5s, 10s, 20s, 40s, 60s (max)
    const backoff = Math.min(
      pollInterval * Math.pow(2, errorCountRef.current - 1),
      ERROR_BACKOFF_MAX
    );
    
    return backoff;
  }, [pollInterval]);

  /**
   * Check if data is delayed
   */
  useEffect(() => {
    if (!lastUpdated || !enabled) return;

    const checkDelayed = setInterval(() => {
      const now = Date.now();
      const elapsed = now - lastUpdated.getTime();
      
      if (elapsed > DELAYED_THRESHOLD && connectionStatus === 'CONNECTED') {
        setConnectionStatus('DELAYED');
      }
    }, 1000);

    return () => clearInterval(checkDelayed);
  }, [lastUpdated, connectionStatus, enabled]);

  /**
   * Handle visibility change (pause polling when tab hidden)
   */
  useEffect(() => {
    const handleVisibilityChange = () => {
      isVisibleRef.current = document.visibilityState === 'visible';
      
      if (isVisibleRef.current && enabled) {
        // Resume polling immediately when tab becomes visible
        fetchLiveMatch();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [fetchLiveMatch, enabled]);

  /**
   * Setup polling
   */
  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }

    // Initial fetch
    fetchLiveMatch();

    // Setup polling interval
    const setupPolling = () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }

      const delay = getBackoffDelay();
      
      intervalRef.current = setInterval(() => {
        // Only poll if tab is visible
        if (isVisibleRef.current) {
          fetchLiveMatch();
        }
      }, delay);
    };

    setupPolling();

    // Cleanup
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [matchId, enabled, fetchLiveMatch, getBackoffDelay]);

  /**
   * Cleanup on unmount
   */
  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  /**
   * Manual refetch
   */
  const refetch = useCallback(async () => {
    await fetchLiveMatch();
  }, [fetchLiveMatch]);

  return {
    liveMatch,
    loading,
    error,
    lastUpdated,
    connectionStatus,
    refetch,
  };
}
