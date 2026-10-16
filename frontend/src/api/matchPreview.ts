/**
 * Pre-match analysis ("Maç analizi") client: GET /api/v1/matches/{match_id}/preview.
 *
 * Every number is a count or sum of real results / FotMob fields. Unknown values are
 * null (never 0) and come with a *_reason / missing_reason. Result letters are Turkish:
 * G = galibiyet, B = beraberlik, M = mağlubiyet.
 */

import { useEffect, useState } from 'react';
import { apiClient } from './client';

export type ResultLetter = 'G' | 'B' | 'M';
export type Venue = 'home' | 'away';

export interface PreviewMatch {
  match_id: string | null;
  date: string;
  competition: string | null;
  is_friendly: boolean;
  venue: Venue;
  opponent: string | null;
  opponent_id: string | null;
  goals_for: number | null;
  goals_against: number | null;
  result: ResultLetter | null;
  xg_for: number | null;
  xg_against: number | null;
  /** "fotmob_team_fixtures": newer than the local database, score only (no xG). */
  source: 'database' | 'fotmob_team_fixtures';
}

export interface FormWindow {
  scope: 'last5' | 'last5_venue';
  venue: Venue | null;
  played: number;
  /** Most recent first, e.g. "GGBMG"; null without matches. */
  results: string | null;
  wins: number | null;
  draws: number | null;
  losses: number | null;
  goals_for: number | null;
  goals_against: number | null;
  xg_for: number | null;
  xg_against: number | null;
  xg_matches: number;
  xg_missing_reason: string | null;
  matches: PreviewMatch[];
  missing_reason: string | null;
}

export interface RestInfo {
  previous_match: PreviewMatch | null;
  rest_days: number | null;
  matches_last_14_days: number | null;
  missing_reason: string | null;
}

export interface Absentee {
  id: string | null;
  name: string | null;
  reason: string | null;
  reason_code: string | null;
  expected_return: string | null;
  expected_return_date: string | null;
  started_previous_match: boolean | null;
}

export interface AbsenteesInfo {
  available: boolean;
  players: Absentee[];
  missing_reason: string | null;
}

export interface PlayerRef {
  id: string | null;
  name: string | null;
}

export interface RotationInfo {
  previous_match: PreviewMatch | null;
  previous_xi_source: 'local_raw_cache' | 'fotmob_match_details' | null;
  changes: number | null;
  came_in: PlayerRef[];
  dropped_out: PlayerRef[];
  missing_reason: string | null;
}

export interface LineupInfo {
  lineup_type: 'confirmed' | 'predicted' | 'last_starting11' | null;
  formation: string | null;
  starters_count: number;
  rotation: RotationInfo;
  missing_reason: string | null;
}

export interface PreviewSide {
  team_id: string | null;
  team_name: string | null;
  last5: FormWindow;
  venue_last5: FormWindow;
  rest: RestInfo;
  absentees: AbsenteesInfo;
  lineup: LineupInfo;
  /** False: the local database may lag and FotMob could not confirm it (no history-based sentence, rest is null). */
  history_verified: boolean;
  data_notes: string[];
}

export interface PreviewHighlight {
  id: string;
  kind: string;
  side: 'home' | 'away' | 'both';
  text: string;
  importance: number;
  facts: Record<string, unknown>;
}

export interface MatchPreviewResponse {
  match_id: string;
  provider_match_id: string | null;
  generated_at: string;
  kickoff: string | null;
  status: string | null;
  competition: string | null;
  home: PreviewSide;
  away: PreviewSide;
  highlights: PreviewHighlight[];
  database_latest_match_at: string | null;
  sources: string[];
  notes: string[];
}

export async function getMatchPreview(matchId: string, signal?: AbortSignal): Promise<MatchPreviewResponse> {
  return apiClient.get(`/matches/${encodeURIComponent(matchId)}/preview`, signal).json<MatchPreviewResponse>();
}

export type MatchPreviewState = 'idle' | 'loading' | 'ready' | 'unavailable';

/** Loads the analysis once per match. 404 / 503 / network errors end in "unavailable" (the card says so). */
export function useMatchPreview(
  matchId: string | null | undefined,
  enabled = true,
): { data: MatchPreviewResponse | null; state: MatchPreviewState } {
  const [result, setResult] = useState<{ data: MatchPreviewResponse | null; state: MatchPreviewState }>({
    data: null,
    state: 'idle',
  });
  useEffect(() => {
    if (!enabled || !matchId) {
      setResult({ data: null, state: 'idle' });
      return;
    }
    setResult({ data: null, state: 'loading' });
    const controller = new AbortController();
    getMatchPreview(matchId, controller.signal)
      .then((d) => {
        if (!controller.signal.aborted) setResult({ data: d, state: 'ready' });
      })
      .catch(() => {
        if (!controller.signal.aborted) setResult({ data: null, state: 'unavailable' });
      });
    return () => controller.abort();
  }, [matchId, enabled]);
  return result;
}
