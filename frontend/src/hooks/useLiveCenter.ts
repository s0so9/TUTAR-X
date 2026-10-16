/**
 * useLiveCenter — loads the live match centre and keeps it fresh.
 *
 * Cadence follows the match state reported by the endpoint itself:
 *   LIVE / EXTRA_TIME / PENALTIES  every 15 s
 *   HALF_TIME                      every 60 s
 *   SCHEDULED                      every 60 s from 15 min before kick-off, else 5 min
 *   FINISHED / POSTPONED / CANCELLED / ABANDONED   no polling
 * Polling pauses while the tab is hidden and resumes (fetching at once when the
 * data is older than one interval) when it becomes visible again. Failed polls
 * keep the last good data and back off (doubling, capped at 2 min). A 404 means
 * the endpoint or the match is not available and stops polling.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../api/client';
import { getLiveCenter } from '../api/liveCenter';
import type { LiveCenterResponse, LiveCenterStatus } from '../types/liveCenter';

export const LIVE_POLL_MS = 15_000;
export const HALF_TIME_POLL_MS = 60_000;
export const PRE_MATCH_NEAR_POLL_MS = 60_000;
export const PRE_MATCH_FAR_POLL_MS = 300_000;
export const MAX_BACKOFF_MS = 120_000;
const PRE_MATCH_NEAR_WINDOW_MS = 15 * 60_000;

export type LiveCenterLoadState = 'idle' | 'loading' | 'ready' | 'error' | 'unavailable';

/** Poll interval for a match state; null means "do not poll". */
export function pollIntervalFor(
  status: LiveCenterStatus | null | undefined,
  kickoff: string | null | undefined,
  now: number,
): number | null {
  switch (status) {
    case 'LIVE':
    case 'EXTRA_TIME':
    case 'PENALTIES':
      return LIVE_POLL_MS;
    case 'HALF_TIME':
      return HALF_TIME_POLL_MS;
    case 'SCHEDULED': {
      const ko = kickoff ? Date.parse(kickoff) : NaN;
      if (Number.isFinite(ko) && ko - now <= PRE_MATCH_NEAR_WINDOW_MS) return PRE_MATCH_NEAR_POLL_MS;
      return PRE_MATCH_FAR_POLL_MS;
    }
    default:
      return null;
  }
}

function isAbortError(err: unknown): boolean {
  return (err instanceof DOMException || err instanceof Error) && err.name === 'AbortError';
}

function isDocumentHidden(): boolean {
  return typeof document !== 'undefined' && document.visibilityState === 'hidden';
}

export interface UseLiveCenterOptions {
  enabled?: boolean;
  /** Match state known before the first response (from the match endpoint). */
  statusHint?: LiveCenterStatus | null;
  kickoffHint?: string | null;
}

export interface UseLiveCenterResult {
  data: LiveCenterResponse | null;
  state: LiveCenterLoadState;
  error: string | null;
  /** Time of the last successful response in this browser. */
  lastUpdated: Date | null;
  /** Current poll interval in ms, null when not polling. */
  pollIntervalMs: number | null;
  /** True while polling is paused because the tab is hidden. */
  paused: boolean;
  refresh: () => void;
}

export function useLiveCenter(matchId: string | null | undefined, options: UseLiveCenterOptions = {}): UseLiveCenterResult {
  const { enabled = true, statusHint = null, kickoffHint = null } = options;

  const [data, setData] = useState<LiveCenterResponse | null>(null);
  const [state, setState] = useState<LiveCenterLoadState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [pollIntervalMs, setPollIntervalMs] = useState<number | null>(null);
  const [paused, setPaused] = useState<boolean>(isDocumentHidden);

  const hintsRef = useRef({ statusHint, kickoffHint });
  hintsRef.current = { statusHint, kickoffHint };
  const runRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    setLastUpdated(null);
    setPollIntervalMs(null);
    if (!enabled || !matchId) {
      setState('idle');
      runRef.current = null;
      return;
    }

    let cancelled = false;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let controller: AbortController | null = null;
    let current: LiveCenterResponse | null = null;
    let failures = 0;
    let lastFetchAt = 0;

    const clearTimer = () => {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
    };

    const intervalNow = (): number | null => {
      const status = current?.status ?? hintsRef.current.statusHint;
      const kickoff = current?.kickoff ?? hintsRef.current.kickoffHint;
      const base = pollIntervalFor(status, kickoff, Date.now());
      if (base === null) return null;
      return failures === 0 ? base : Math.min(base * 2 ** failures, MAX_BACKOFF_MS);
    };

    const schedule = () => {
      clearTimer();
      if (cancelled || stopped) return;
      const ms = intervalNow();
      setPollIntervalMs(ms);
      if (ms === null || isDocumentHidden()) return;
      timer = setTimeout(run, ms);
    };

    async function run() {
      clearTimer();
      controller?.abort();
      const own = new AbortController();
      controller = own;
      if (!current) setState('loading');
      try {
        const res = await getLiveCenter(matchId as string, own.signal);
        if (cancelled || own.signal.aborted) return;
        current = res;
        failures = 0;
        lastFetchAt = Date.now();
        setData(res);
        setState('ready');
        setError(null);
        setLastUpdated(new Date(lastFetchAt));
      } catch (err) {
        if (cancelled || isAbortError(err)) return;
        if (err instanceof ApiError && err.status === 404) {
          stopped = true;
          setState('unavailable');
          setError('Canlı maç merkezi bu maç için bulunamadı.');
          setPollIntervalMs(null);
          return;
        }
        failures += 1;
        setError('Canlı veri güncellenemedi.');
        setState(current ? 'ready' : 'error');
      }
      schedule();
    }

    const onVisibility = () => {
      const hidden = isDocumentHidden();
      setPaused(hidden);
      if (hidden) {
        clearTimer();
        return;
      }
      if (stopped || cancelled) return;
      const ms = intervalNow();
      if (ms === null) return;
      const since = Date.now() - lastFetchAt;
      if (since >= ms) {
        void run();
      } else {
        clearTimer();
        timer = setTimeout(run, ms - since);
      }
    };

    runRef.current = () => {
      if (!stopped && !cancelled) void run();
    };
    document.addEventListener('visibilitychange', onVisibility);
    void run();

    return () => {
      cancelled = true;
      clearTimer();
      controller?.abort();
      document.removeEventListener('visibilitychange', onVisibility);
      runRef.current = null;
    };
  }, [matchId, enabled]);

  const refresh = useCallback(() => {
    runRef.current?.();
  }, []);

  return { data, state, error, lastUpdated, pollIntervalMs, paused, refresh };
}
