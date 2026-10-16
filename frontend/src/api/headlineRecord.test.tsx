/**
 * useMatchHeadlineRecord polling. The payload is a TEST FIXTURE (made-up values).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { apiClient } from './client';
import { useMatchHeadlineRecord, RECORD_POLL_MS, RECORD_POLL_SLOW_MS } from './headlineRecord';
import type { HeadlinePickItem, MatchHeadlineRecord } from './headlineRecord';

vi.mock('./client', () => ({ apiClient: { get: vi.fn() } }));
const apiGet = apiClient.get as unknown as ReturnType<typeof vi.fn>;

const NOW = Date.parse('2026-10-15T16:00:00Z');

function item(result: HeadlinePickItem['result']): HeadlinePickItem {
  return {
    id: 'p', match_id: 'fotmob_1', kind: 'banko', stage: 'headline_banko', home_team: 'Mock Ev', away_team: 'Mock Dep',
    competition_id: '42', competition_name: 'Mock Kupa', kickoff_at: '2026-10-15T16:45:00Z', frozen_at: '2026-10-15T16:25:00Z',
    minutes_before_kickoff: 20, market_key: 'HOME_OR_DRAW', label: '1X', selection_text: '1X', market_name: 'Çifte Şans',
    probability: 0.8, fair_odds: 1.25, odds: null, lineup_type: { home: 'confirmed', away: 'confirmed', source: 'test' },
    model_1x2: null, result, final_score: null, settled_at: null, source: 'live_freeze', rule_version: 'headline_v1',
  };
}

const NOT_FROZEN: MatchHeadlineRecord = { match_id: 'fotmob_1', frozen: false, picks: { banko: null, oranli: null } };
const frozen = (result: HeadlinePickItem['result']): MatchHeadlineRecord => ({
  match_id: 'fotmob_1', frozen: true, picks: { banko: item(result), oranli: null },
});

function answer(...records: MatchHeadlineRecord[]) {
  let i = 0;
  apiGet.mockImplementation(() => {
    const record = records[Math.min(i++, records.length - 1)];
    return { json: () => Promise.resolve(record) };
  });
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
  vi.setSystemTime(NOW);
  apiGet.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useMatchHeadlineRecord', () => {
  it('reads the record and keeps asking every minute until it is frozen and settled', async () => {
    answer(NOT_FROZEN, frozen(null), frozen('won'));
    const { result } = renderHook(() => useMatchHeadlineRecord('fotmob_1', '2026-10-15T16:45:00Z'));
    await flush();
    expect(result.current?.frozen).toBe(false);
    expect(apiGet).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(RECORD_POLL_MS);
    });
    await flush();
    expect(result.current?.picks.banko?.result).toBeNull();
    expect(apiGet).toHaveBeenCalledTimes(2);

    await act(async () => {
      vi.advanceTimersByTime(RECORD_POLL_MS);
    });
    await flush();
    expect(result.current?.picks.banko?.result).toBe('won');
    expect(apiGet).toHaveBeenCalledTimes(3);

    await act(async () => {
      vi.advanceTimersByTime(10 * RECORD_POLL_MS);
    });
    expect(apiGet).toHaveBeenCalledTimes(3); // settled: no more requests
  });

  it('reads an old match once', async () => {
    answer(frozen('lost'));
    renderHook(() => useMatchHeadlineRecord('fotmob_1', '2026-10-01T16:45:00Z'));
    await flush();
    await act(async () => {
      vi.advanceTimersByTime(5 * RECORD_POLL_MS);
    });
    expect(apiGet).toHaveBeenCalledTimes(1);
  });

  it('looks only every five minutes while kick-off is hours away', async () => {
    answer(NOT_FROZEN);
    renderHook(() => useMatchHeadlineRecord('fotmob_1', '2026-10-15T23:00:00Z'));
    await flush();
    await act(async () => {
      vi.advanceTimersByTime(RECORD_POLL_MS * 2);
    });
    expect(apiGet).toHaveBeenCalledTimes(1);
    await act(async () => {
      vi.advanceTimersByTime(RECORD_POLL_SLOW_MS);
    });
    expect(apiGet).toHaveBeenCalledTimes(2);
  });

  it('does not follow a match that is days away', async () => {
    answer(NOT_FROZEN);
    renderHook(() => useMatchHeadlineRecord('fotmob_1', '2026-10-25T16:45:00Z'));
    await flush();
    await act(async () => {
      vi.advanceTimersByTime(RECORD_POLL_SLOW_MS * 3);
    });
    expect(apiGet).toHaveBeenCalledTimes(1);
  });

  it('returns null and stays quiet when the request fails', async () => {
    apiGet.mockImplementation(() => ({ json: () => Promise.reject(new Error('network')) }));
    const { result } = renderHook(() => useMatchHeadlineRecord('fotmob_1', '2026-10-15T16:45:00Z'));
    await flush();
    expect(result.current).toBeNull();
  });

  it('does nothing without a match id', async () => {
    const { result } = renderHook(() => useMatchHeadlineRecord(null, null));
    await flush();
    expect(apiGet).not.toHaveBeenCalled();
    expect(result.current).toBeNull();
  });
});
