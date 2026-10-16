/**
 * Match Data Normalization Utilities
 * 
 * Ensures consistent team name resolution across the frontend.
 */

import type { MatchResponse } from '../api/types';

export interface NormalizedTeam {
  id: string;
  name: string;
  shortName?: string;
  code?: string;
  logoUrl?: string;
}

export interface NormalizedMatch {
  id: string;
  homeTeam: NormalizedTeam;
  awayTeam: NormalizedTeam;
  scheduledAt: string;
  status: string;
  homeScore: number | null;
  awayScore: number | null;
  competitionId: string;
  competitionName?: string;  // Optional competition name from provider
  seasonId: string;
  round: number | null;
  raw: MatchResponse; // Keep original for any edge cases
}

/**
 * Normalize team information from API response.
 * Priority:
 * 1. Use nested team object with name if available
 * 2. Fall back to team ID if nested object is missing
 * 3. Display "Takım bilgisi yok" only if both are unavailable
 */
function normalizeTeam(teamId: string, teamInfo: MatchResponse['home_team']): NormalizedTeam {
  // If nested team object exists with a name, use it
  if (teamInfo && teamInfo.name && teamInfo.name.trim()) {
    return {
      id: teamInfo.id,
      name: teamInfo.name,
      shortName: teamInfo.short_name ?? undefined,
      code: teamInfo.code ?? undefined,
      logoUrl: teamInfo.logo_url ?? undefined,
    };
  }

  // If only ID is available, check if it looks like a dev pattern
  // that can be formatted nicely
  const devMatch = teamId.match(/^dev_team_(.+)$/);
  if (devMatch) {
    const name = devMatch[1];
    const formattedName = name.charAt(0).toUpperCase() + name.slice(1);
    return {
      id: teamId,
      name: formattedName,
    };
  }

  // If team info is completely missing but we have an ID
  if (teamId && teamId.trim()) {
    // Check if it looks like a numeric ID (don't display numbers as names)
    if (/^\d+$/.test(teamId)) {
      return {
        id: teamId,
        name: 'Takım bilgisi yok',
      };
    }
    
    // If we reach here, we have an opaque provider ID with no team info
    // Never display a raw identifier as a team name
    return {
      id: teamId,
      name: 'Takım bilgisi yok',
    };
  }

  // Last resort: no team info at all
  return {
    id: teamId || 'unknown',
    name: 'Takım bilgisi yok',
  };
}

/**
 * Normalize a match response into a consistent UI format.
 */
export function normalizeMatch(match: MatchResponse): NormalizedMatch {
  return {
    id: match.id,
    homeTeam: normalizeTeam(match.home_team_id, match.home_team),
    awayTeam: normalizeTeam(match.away_team_id, match.away_team),
    scheduledAt: match.scheduled_at,
    status: match.status,
    homeScore: match.home_score,
    awayScore: match.away_score,
    competitionId: match.competition_id,
    competitionName: match.competition_name ?? undefined,
    seasonId: match.season_id,
    round: match.round,
    raw: match,
  };
}

/**
 * Normalize multiple matches.
 */
export function normalizeMatches(matches: MatchResponse[]): NormalizedMatch[] {
  return matches.map(normalizeMatch);
}
