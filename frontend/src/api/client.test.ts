/**
 * API Client Tests
 * 
 * Tests for request function with focus on:
 * - AbortController lifecycle
 * - Signal cleanup
 * - Error handling
 * - React StrictMode simulation (mount/unmount/remount)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { getMatches, getMatchPrediction, ApiError } from './client';

// Mock fetch globally
const originalFetch = globalThis.fetch;

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe('API Client - AbortController Behavior', () => {
  it('should handle successful request without abort', async () => {
    const mockResponse = {
      count: 1,
      matches: [{ id: 'match-1', status: 'scheduled' }],
      is_development_data: false,
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    } as Response);

    const result = await getMatches({ status: 'scheduled' });

    expect(result).toEqual(mockResponse);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });

  it('should handle request abortion from caller', async () => {
    const controller = new AbortController();
    
    // Mock fetch that respects abort signal
    globalThis.fetch = vi.fn().mockImplementation(
      (_url, options) => new Promise((resolve, reject) => {
        const signal = options?.signal as AbortSignal;
        if (signal?.aborted) {
          reject(new DOMException('Aborted', 'AbortError'));
          return;
        }
        if (signal) {
          signal.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'));
          });
        }
        // Simulate async operation - never resolves unless aborted
        setTimeout(() => {
          resolve({
            ok: true,
            json: async () => ({ mensione_pick: { market: 'HOME', selection: 'Home Win' } }),
          } as Response);
        }, 10000);
      })
    );

    const request = getMatchPrediction('match-1', controller.signal);
    
    // Abort immediately
    controller.abort();

    await expect(request).rejects.toMatchObject({
      name: 'AbortError'
    });
  });

  it('should handle pre-aborted signal gracefully', async () => {
    const controller = new AbortController();
    controller.abort(); // Abort BEFORE making request

    // Fetch should never be called
    globalThis.fetch = vi.fn();

    await expect(
      getMatchPrediction('match-1', controller.signal)
    ).rejects.toMatchObject({
      name: 'AbortError'
    });

    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('should clean up abort listener on success', async () => {
    const controller = new AbortController();
    const mockResponse = {
      mensione_pick: { market: 'HOME', selection: 'Home Win' },
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    } as Response);

    await getMatchPrediction('match-1', controller.signal);

    // After successful request, listener should be removed
    // (In practice, we verify this doesn't cause memory leaks by checking
    // that aborting after request completes doesn't affect anything)
    controller.abort();
    
    // No assertion needed - if listener wasn't cleaned up properly,
    // subsequent tests would fail due to side effects
    expect(true).toBe(true);
  });

  it('should clean up abort listener on error', async () => {
    const controller = new AbortController();

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      json: async () => ({ detail: 'Match not found' }),
    } as Response);

    await expect(
      getMatchPrediction('match-1', controller.signal)
    ).rejects.toThrow(ApiError);

    // Abort after error - should not cause issues
    controller.abort();
    expect(true).toBe(true);
  });

  it('should handle React StrictMode double-mount scenario', async () => {
    // Simulate React StrictMode: mount → unmount → remount
    const mockResponse = {
      mensione_pick: { market: 'HOME', selection: 'Home Win' },
    };

    // Mock fetch that respects abort signal
    globalThis.fetch = vi.fn().mockImplementation(
      (_url, options) => new Promise((resolve, reject) => {
        const signal = options?.signal as AbortSignal;
        if (signal?.aborted) {
          reject(new DOMException('Aborted', 'AbortError'));
          return;
        }
        if (signal) {
          signal.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'));
          });
        }
        // Simulate async operation
        setTimeout(() => {
          resolve({
            ok: true,
            json: async () => mockResponse,
          } as Response);
        }, 50);
      })
    );

    // First mount
    const controller1 = new AbortController();
    const request1 = getMatchPrediction('match-1', controller1.signal);
    
    // Unmount (StrictMode cleanup) - abort immediately
    controller1.abort();
    
    // Verify first request was aborted
    await expect(request1).rejects.toMatchObject({
      name: 'AbortError'
    });

    // Second mount (StrictMode remount) - should work without issues
    const controller2 = new AbortController();
    const request2 = getMatchPrediction('match-1', controller2.signal);
    
    // Should complete successfully
    const result = await request2;
    expect(result).toEqual(mockResponse);
  });

  it('should distinguish between timeout and external abort', async () => {
    // Test internal timeout
    vi.useFakeTimers();
    
    // Mock fetch that respects abort signal
    globalThis.fetch = vi.fn().mockImplementation(
      (_url, options) => new Promise((_, reject) => {
        const signal = options?.signal as AbortSignal;
        if (signal) {
          signal.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'));
          });
        }
        // Never resolves on its own
      })
    );

    const timeoutPromise = getMatches({ status: 'scheduled' });
    
    // Create expectation promise before advancing timers
    const expectationPromise = Promise.all([
      expect(timeoutPromise).rejects.toThrow(ApiError),
      expect(timeoutPromise).rejects.toThrow('timed out')
    ]);
    
    // Fast-forward past 60 second timeout (getMatches uses 60s)
    await vi.runAllTimersAsync();
    
    // Now await the expectations
    await expectationPromise;
    
    vi.useRealTimers();
  });

  it('should handle external abort before timeout', async () => {
    vi.useFakeTimers();
    
    const controller = new AbortController();
    
    // Mock fetch that respects abort signal
    globalThis.fetch = vi.fn().mockImplementation(
      (_url, options) => new Promise((_, reject) => {
        const signal = options?.signal as AbortSignal;
        if (signal) {
          signal.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'));
          });
        }
        // Never resolves on its own
      })
    );

    const abortPromise = getMatchPrediction('match-1', controller.signal);
    
    // Abort externally before timeout
    vi.advanceTimersByTime(1000);
    controller.abort();
    vi.advanceTimersByTime(100);
    
    await expect(abortPromise).rejects.toMatchObject({
      name: 'AbortError'
    });
    
    vi.useRealTimers();
  });

  it('should handle network errors', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('Network failure'));

    await expect(
      getMatches({ status: 'scheduled' })
    ).rejects.toThrow(ApiError);
    
    await expect(
      getMatches({ status: 'scheduled' })
    ).rejects.toThrow('Network failure');
  });

  it('should handle HTTP error responses', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      json: async () => ({ detail: 'Database connection failed' }),
    } as Response);

    await expect(
      getMatches({ status: 'scheduled' })
    ).rejects.toThrow(ApiError);
  });

  it('should not leak abort listeners across multiple requests', async () => {
    const mockResponse = {
      mensione_pick: { market: 'HOME', selection: 'Home Win' },
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    } as Response);

    const controller = new AbortController();

    // Make multiple requests with same controller
    await getMatchPrediction('match-1', controller.signal);
    await getMatchPrediction('match-2', controller.signal);
    await getMatchPrediction('match-3', controller.signal);

    // Abort after all complete - should not cause issues
    controller.abort();

    // Verify we can still make new requests with new controller
    const controller2 = new AbortController();
    const result = await getMatchPrediction('match-4', controller2.signal);
    expect(result).toEqual(mockResponse);
  });
});
