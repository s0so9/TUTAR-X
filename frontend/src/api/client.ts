/**
 * API Client
 * 
 * Centralized HTTP client for backend API calls.
 */

import { Capacitor, CapacitorHttp } from '@capacitor/core';
import type {
  MatchListResponse,
  MatchDetailResponse,
  MatchPredictionResponse,
  LiveMatchesResponse,
  CompetitionListResponse,
} from './types';

// Production-safe API base URL configuration
const PRODUCTION_API_BASE_URL = 'https://tutar-x-api.vercel.app/api/v1';
// Local backend (uvicorn) default port for web builds without VITE_API_BASE_URL.
const LOCAL_API_BASE_URL = 'http://127.0.0.1:8003/api/v1';
// Same-origin path used by the Vite dev server; vite.config.ts proxies /api to 127.0.0.1:8003.
const DEV_PROXY_API_BASE_URL = '/api/v1';

/**
 * Resolve the API base URL.
 *
 * Order: native (Capacitor) build -> production URL; then VITE_API_BASE_URL;
 * then the Vite dev proxy during `npm run dev`; otherwise the local backend on 8003.
 */
export function getApiBaseUrl(): string {
  if (Capacitor.isNativePlatform()) {
    return PRODUCTION_API_BASE_URL;
  }
  const configured = import.meta.env.VITE_API_BASE_URL;
  if (configured) {
    return configured.replace(/\/+$/, '');
  }
  if (import.meta.env.DEV) {
    return DEV_PROXY_API_BASE_URL;
  }
  return LOCAL_API_BASE_URL;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
    public detail?: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Make an HTTP request to the API with timeout.
 * 
 * @param endpoint - API endpoint path
 * @param options - Fetch options including optional signal for cancellation
 */
async function nativeRequest<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${getApiBaseUrl()}${endpoint}`;
  const timeoutMs = endpoint.includes('/prediction') ? 20000 : 30000;

  if (options?.signal?.aborted) {
    throw new DOMException('Request was aborted', 'AbortError');
  }

  const headerEntries = options?.headers
    ? Object.entries(options.headers as Record<string, string>)
    : [];
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...Object.fromEntries(headerEntries),
  };

  const response = await CapacitorHttp.request({
    url,
    method: (options?.method as string) || 'GET',
    headers,
    connectTimeout: timeoutMs,
    readTimeout: timeoutMs,
  });

  if (options?.signal?.aborted) {
    throw new DOMException('Request was aborted', 'AbortError');
  }

  if (response.status < 200 || response.status >= 300) {
    let detail = `HTTP ${response.status}`;
    const data = response.data as { detail?: string } | string | undefined;
    if (data && typeof data === 'object' && data.detail) {
      detail = data.detail;
    }
    throw new ApiError(`API request failed: ${detail}`, response.status, detail);
  }

  return response.data as T;
}

async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  if (Capacitor.isNativePlatform()) {
    try {
      return await nativeRequest<T>(endpoint, options);
    } catch (error) {
      if (error instanceof ApiError) {
        throw error;
      }
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw error;
      }
      if (error instanceof Error && error.name === 'AbortError') {
        throw error;
      }
      throw new ApiError(
        'Sunucuya bağlanılamadı. İnternet bağlantınızı kontrol edin.',
        undefined,
        'Unable to connect to the backend server'
      );
    }
  }

  const url = `${getApiBaseUrl()}${endpoint}`;

  // Create abort controller for timeout
  const controller = new AbortController();
  
  // Use shorter timeout for prediction endpoints (20 seconds), standard for others (30 seconds)
  const timeoutMs = endpoint.includes('/prediction') ? 20000 : 30000;
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  // Track if this was aborted by caller vs timeout
  let abortedByCaller = false;

  // If caller provided an AbortSignal, listen to it
  const callerSignal = options?.signal;
  let callerAbortHandler: (() => void) | undefined;
  
  if (callerSignal) {
    if (callerSignal.aborted) {
      clearTimeout(timeoutId);
      throw new DOMException('Request was aborted', 'AbortError');
    }
    
    callerAbortHandler = () => {
      abortedByCaller = true;
      clearTimeout(timeoutId);
      controller.abort();
    };
    
    callerSignal.addEventListener('abort', callerAbortHandler);
  }
  
  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    
    // Clean up listener
    if (callerSignal && callerAbortHandler) {
      callerSignal.removeEventListener('abort', callerAbortHandler);
    }

    if (!response.ok) {
      let detail = `HTTP ${response.status}: ${response.statusText}`;
      
      try {
        const errorData = await response.json();
        detail = errorData.detail || detail;
      } catch {
        // Ignore JSON parse errors for error responses
      }

      throw new ApiError(
        `API request failed: ${detail}`,
        response.status,
        detail
      );
    }

    return await response.json();
  } catch (error) {
    clearTimeout(timeoutId);
    
    // Clean up listener
    if (callerSignal && callerAbortHandler) {
      callerSignal.removeEventListener('abort', callerAbortHandler);
    }

    if (error instanceof ApiError) {
      throw error;
    }

    // Handle abort - check if it's from caller or timeout
    if (error instanceof DOMException && error.name === 'AbortError') {
      if (abortedByCaller || (callerSignal && callerSignal.aborted)) {
        // Re-throw the original AbortError when caller aborted
        throw error;
      } else {
        // Internal timeout - convert to ApiError
        throw new ApiError(
          'Request timed out - server response too slow',
          undefined,
          'The server took too long to respond'
        );
      }
    }

    // Also handle Error with name 'AbortError' (for compatibility)
    if (error instanceof Error && error.name === 'AbortError') {
      if (abortedByCaller || (callerSignal && callerSignal.aborted)) {
        // Re-throw the original AbortError when caller aborted
        throw error;
      } else {
        // Internal timeout - convert to ApiError
        throw new ApiError(
          'Request timed out - server response too slow',
          undefined,
          'The server took too long to respond'
        );
      }
    }

    // Network or other errors
    throw new ApiError(
      error instanceof Error ? error.message : 'Network error occurred',
      undefined,
      'Unable to connect to the backend server'
    );
  }
}

/**
 * Get list of available competitions.
 */
export async function getCompetitions(): Promise<CompetitionListResponse> {
  return request<CompetitionListResponse>('/competitions');
}

/** Match lists show only the competitions whose data is collected and trained on. */
const FEATURED_SCOPE = 'featured';

/**
 * Get list of matches.
 */
export async function getMatches(params?: {
  competition_id?: string;
  season_id?: string;
  team_id?: string;
  from_date?: string;
  to_date?: string;
  status?: string;
  scheduled_after?: string;  // ISO8601 UTC datetime
  limit?: number;
  offset?: number;
  /** 'featured' (default): the 10 big leagues + UCL/UEL/UECL; 'all': every competition. */
  scope?: 'featured' | 'all';
}, signal?: AbortSignal): Promise<MatchListResponse> {
  const searchParams = new URLSearchParams();
  
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && key !== 'scope') {
        searchParams.append(key, String(value));
      }
    });
  }
  searchParams.append('scope', params?.scope ?? FEATURED_SCOPE);

  const query = searchParams.toString();
  const endpoint = query ? `/matches?${query}` : '/matches';

  return request<MatchListResponse>(endpoint, { signal });
}

/**
 * Get upcoming matches (shortcut).
 */
export async function getUpcomingMatches(days: number = 7, limit?: number): Promise<MatchListResponse> {
  // Use local date to avoid UTC/local timezone mismatches
  const today = new Date();
  const fromDate = formatDateForAPI(today);
  
  const futureDate = new Date(today);
  futureDate.setDate(futureDate.getDate() + days);
  const toDate = formatDateForAPI(futureDate);

  return getMatches({
    from_date: fromDate,
    to_date: toDate,
    status: 'SCHEDULED',
    limit,
  });
}

/**
 * Format a Date object to YYYY-MM-DD string using local timezone.
 */
export function formatDateForAPI(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/**
 * Get a single match by ID.
 */
export async function getMatch(matchId: string): Promise<MatchDetailResponse> {
  return request<MatchDetailResponse>(`/matches/${matchId}`);
}

/**
 * Get prediction for a match.
 * 
 * @param matchId - Match ID
 * @param signal - Optional AbortSignal for request cancellation
 */
export async function getMatchPrediction(
  matchId: string,
  signal?: AbortSignal
): Promise<MatchPredictionResponse> {
  return request<MatchPredictionResponse>(`/matches/${matchId}/prediction`, { signal });
}

/**
 * Get live matches with provider health and data quality information.
 */
export async function getLiveMatches(): Promise<LiveMatchesResponse> {
  return request<LiveMatchesResponse>(`/matches/live?scope=${FEATURED_SCOPE}`);
}

/**
 * Get live match detail for a specific match.
 * Returns LiveMatchState when match is live, null otherwise.
 */
export async function getLiveMatchDetail(matchId: string): Promise<import('../types/live').LiveMatchState | null> {
  try {
    const response = await getMatch(matchId);
    
    // Only return live state if match is actually live
    if (response.match.status !== 'LIVE') {
      return null;
    }
    
    // Transform MatchResponse to LiveMatchState
    return {
      matchId: response.match.id,
      status: response.match.status.toUpperCase() as import('../types/live').MatchStatusType,
      minute: response.match.minute ?? undefined,
      addedTime: response.match.added_time ?? undefined,
      homeScore: response.match.home_score ?? undefined,
      awayScore: response.match.away_score ?? undefined,
      homeTeam: response.match.home_team ? {
        id: response.match.home_team.id,
        name: response.match.home_team.name,
        code: response.match.home_team.code ?? undefined,
        logo: response.match.home_team.logo_url ?? undefined,
      } : undefined,
      awayTeam: response.match.away_team ? {
        id: response.match.away_team.id,
        name: response.match.away_team.name,
        code: response.match.away_team.code ?? undefined,
        logo: response.match.away_team.logo_url ?? undefined,
      } : undefined,
      homeStats: response.match.home_statistics ? transformStatsToLiveStats(response.match.home_statistics) : undefined,
      awayStats: response.match.away_statistics ? transformStatsToLiveStats(response.match.away_statistics) : undefined,
    };
  } catch (error) {
    console.error('[API] getLiveMatchDetail error:', error);
    throw error;
  }
}

/**
 * Transform MatchStatisticsResponse to LiveStats
 */
function transformStatsToLiveStats(stats: import('./types').MatchStatisticsResponse): import('../types/live').LiveStats {
  return {
    shots: stats.shots_total ?? undefined,
    shotsOnTarget: stats.shots_on_target ?? undefined,
    // shotsOutsideBox: No reliable mapping available - shots_off_target means missed target, not outside box
    shotsOutsideBox: undefined,  // CORRECTED: Do not use shots_off_target
    xG: stats.xg ?? undefined,
    possession: stats.possession_percentage ?? undefined,
    corners: stats.corners ?? undefined,
    fouls: stats.fouls_committed ?? undefined,
    offsides: stats.offsides ?? undefined,
    yellowCards: stats.yellow_cards ?? undefined,
    redCards: stats.red_cards ?? undefined,
    passes: stats.passes_attempted ?? undefined,
    passAccuracy: stats.pass_accuracy ?? undefined,
    tackles: stats.tackles ?? undefined,
    interceptions: stats.interceptions ?? undefined,
    saves: stats.saves ?? undefined,
  };
}

/**
 * Future: Get live events for a match (placeholder)
 */
export async function getLiveEvents(matchId: string): Promise<import('../types/live').LiveEvent[]> {
  // TODO: Implement when backend endpoint exists
  console.warn(`[API] getLiveEvents not implemented for match ${matchId} - backend endpoint not available`);
  return [];
}

/**
 * Future: Get live shots with coordinates for a match (placeholder)
 */
export async function getLiveShots(matchId: string): Promise<import('../types/live').LiveShot[]> {
  // TODO: Implement when backend endpoint exists
  console.warn(`[API] getLiveShots not implemented for match ${matchId} - backend endpoint not available`);
  return [];
}

/**
 * Future: Get live prediction for a match (placeholder)
 */
export async function getLivePrediction(matchId: string): Promise<import('../types/live').LivePrediction | null> {
  // TODO: Implement when backend endpoint exists
  console.warn(`[API] getLivePrediction not implemented for match ${matchId} - backend endpoint not available`);
  return null;
}

/**
 * Future: Get live markets for a match (placeholder)
 */
export async function getLiveMarkets(matchId: string): Promise<import('../types/live').LiveMarket[]> {
  // TODO: Implement when backend endpoint exists
  console.warn(`[API] getLiveMarkets not implemented for match ${matchId} - backend endpoint not available`);
  return [];
}

/**
 * Centralized API client object for consistent usage across components.
 * Wraps the request function for GET and POST methods.
 */
export const apiClient = {
  /**
   * Make a GET request to the API.
   * Returns a promise-like object with .json() method for type safety.
   */
  get: (endpoint: string, signal?: AbortSignal) => {
    return {
      json: <T>() => request<T>(endpoint, { method: 'GET', signal })
    };
  },

  /**
   * Make a POST request to the API.
   * Returns a promise-like object with .json() method for type safety.
   */
  post: (endpoint: string, body?: unknown, signal?: AbortSignal) => {
    return {
      json: <T>() => request<T>(endpoint, {
        method: 'POST',
        body: body ? JSON.stringify(body) : undefined,
        signal
      })
    };
  },

  /**
   * Make a PUT request to the API.
   * Returns a promise-like object with .json() method for type safety.
   */
  put: (endpoint: string, body?: unknown, signal?: AbortSignal) => {
    return {
      json: <T>() => request<T>(endpoint, {
        method: 'PUT',
        body: body ? JSON.stringify(body) : undefined,
        signal
      })
    };
  },

  /**
   * Make a DELETE request to the API.
   * Returns a promise-like object with .json() method for type safety.
   */
  delete: (endpoint: string, signal?: AbortSignal) => {
    return {
      json: <T>() => request<T>(endpoint, { method: 'DELETE', signal })
    };
  }
};
