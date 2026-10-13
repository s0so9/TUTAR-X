/**
 * useOdds Hook - Bookmaker odds data fetching
 *
 * Provides functionality to fetch average market odds from TUTAR X backend.
 * Uses centralized API client for consistent URL handling across environments.
 */

import { useState, useEffect, useCallback } from 'react'
import { apiClient } from '../api/client'

export interface MarketOdds {
  provider_event_id: string
  match_id?: string
  market_key: string
  market_point?: number
  outcome_name: string
  average_odds: number
  bookmaker_count: number
  min_odds?: number
  max_odds?: number
  bookmakers: string[]
  individual_odds: number[]
  calculated_at: string
}

export interface MatchOdds {
  match_found: boolean
  home_team: string
  away_team: string
  commence_time?: string
  home_win?: MarketOdds
  draw?: MarketOdds
  away_win?: MarketOdds
  over_2_5?: MarketOdds
  under_2_5?: MarketOdds
  last_updated?: string
}

export interface OddsHealth {
  api_available: boolean
  api_quota_remaining?: number
  last_update?: string
  total_events_cached: number
  total_bookmakers: number
}

/**
 * Hook to fetch match odds by match ID
 */
export function useMatchOdds(matchId?: string) {
  const [odds, setOdds] = useState<MatchOdds | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchOdds = useCallback(async (id: string) => {
    setLoading(true)
    setError(null)

    try {
      // apiClient.get returns an object with .json() method
      const data = await apiClient.get(`/odds/match/${id}`).json<MatchOdds>()
      setOdds(data)
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Odds fetch failed'
      setError(errorMessage)
      console.error('Failed to fetch match odds:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!matchId) {
      setOdds(null)
      setError(null)
      return
    }

    // Fetch on mount or when matchId changes
    fetchOdds(matchId)
  }, [matchId, fetchOdds])

  const refetch = useCallback(() => {
    if (matchId) {
      fetchOdds(matchId)
    }
  }, [matchId, fetchOdds])

  return { odds, loading, error, refetch }
}

/**
 * Hook to search for match odds by team names
 */
export function useSearchOdds() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const searchOdds = async (
    homeTeam: string,
    awayTeam: string,
    sportKey: string = 'soccer_epl'
  ): Promise<MarketOdds[] | null> => {
    setLoading(true)
    setError(null)

    try {
      const params = new URLSearchParams({
        home_team: homeTeam,
        away_team: awayTeam,
        sport_key: sportKey
      })

      // apiClient.get returns an object with .json() method
      const data = await apiClient.get(`/odds/search?${params}`).json<MarketOdds[] | { match_found: false }>()

      if (!Array.isArray(data) && data.match_found === false) {
        return null
      }

      return data as MarketOdds[]
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Odds search failed'
      setError(errorMessage)
      console.error('Failed to search odds:', err)
      return null
    } finally {
      setLoading(false)
    }
  }

  return { searchOdds, loading, error }
}

/**
 * Hook to get odds system health
 */
export function useOddsHealth() {
  const [health, setHealth] = useState<OddsHealth | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchHealth = async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await apiClient.get('/api/v1/odds/health')
      const data: OddsHealth = await response.json()
      setHealth(data)
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Health check failed'
      setError(errorMessage)
      console.error('Failed to fetch odds health:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchHealth()
  }, [])

  return { health, loading, error, refetch: fetchHealth }
}

/**
 * Hook to trigger manual odds update (admin function)
 */
export function useManualOddsUpdate() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const updateOdds = async (sportKey?: string) => {
    setLoading(true)
    setError(null)

    try {
      const url = sportKey
        ? `/api/v1/odds/manual-update?sport_key=${sportKey}`
        : '/api/v1/odds/manual-update'

      const response = await apiClient.post(url)
      const data = await response.json()
      return data
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Manual update failed'
      setError(errorMessage)
      console.error('Failed to trigger manual odds update:', err)
      throw err
    } finally {
      setLoading(false)
    }
  }

  return { updateOdds, loading, error }
}

/**
 * Helper function to extract odds for specific outcome
 */
export function extractOddsForOutcome(
  odds: MatchOdds | null,
  market: 'h2h' | 'totals',
  outcome: string
): number | null {
  if (!odds || !odds.match_found) {
    return null
  }

  if (market === 'h2h') {
    switch (outcome.toLowerCase()) {
      case 'home':
      case '1':
        return odds.home_win?.average_odds || null
      case 'draw':
      case 'x':
        return odds.draw?.average_odds || null
      case 'away':
      case '2':
        return odds.away_win?.average_odds || null
      default:
        return null
    }
  }

  if (market === 'totals') {
    switch (outcome.toLowerCase()) {
      case 'over':
      case 'over 2.5':
        return odds.over_2_5?.average_odds || null
      case 'under':
      case 'under 2.5':
        return odds.under_2_5?.average_odds || null
      default:
        return null
    }
  }

  return null
}

/**
 * Helper function to get bookmaker count for specific outcome
 */
export function getBookmakerCount(
  odds: MatchOdds | null,
  market: 'h2h' | 'totals',
  outcome: string
): number {
  if (!odds || !odds.match_found) {
    return 0
  }

  let marketOdds: MarketOdds | undefined

  if (market === 'h2h') {
    switch (outcome.toLowerCase()) {
      case 'home':
      case '1':
        marketOdds = odds.home_win
        break
      case 'draw':
      case 'x':
        marketOdds = odds.draw
        break
      case 'away':
      case '2':
        marketOdds = odds.away_win
        break
    }
  }

  if (market === 'totals') {
    switch (outcome.toLowerCase()) {
      case 'over':
      case 'over 2.5':
        marketOdds = odds.over_2_5
        break
      case 'under':
      case 'under 2.5':
        marketOdds = odds.under_2_5
        break
    }
  }

  return marketOdds?.bookmaker_count || 0
}

/**
 * Helper to format odds update time
 */
export function formatOddsUpdateTime(timestamp?: string): string {
  if (!timestamp) {
    return 'Bilinmiyor'
  }

  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / (1000 * 60))
  const diffHours = Math.floor(diffMins / 60)

  if (diffMins < 1) {
    return 'Şimdi'
  } else if (diffMins < 60) {
    return `${diffMins} dakika önce`
  } else if (diffHours < 24) {
    return `${diffHours} saat önce`
  } else {
    return date.toLocaleDateString('tr-TR', {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit'
    })
  }
}
