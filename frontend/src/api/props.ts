/**
 * Cards / corners / shots client: GET /api/v1/matches/{match_id}/props.
 */

import { useEffect, useState } from 'react';
import { apiClient } from './client';

export interface PropLine {
  line: number;
  over: number;
  under: number;
}

export interface PropMarket {
  key: string;
  label_tr: string;
  group: string;
  scope: 'home' | 'away' | 'total';
  expected: number;
  lines: PropLine[];
  /** False for markets that must never be shown as banko (cards, total corners). */
  banko_eligible?: boolean;
}

export interface PropRecent {
  stat: string;
  label_tr: string;
  for_last5: number | null;
  against_last5: number | null;
  n: number | null;
}

export interface PropsResponse {
  match_id: string;
  model_version: string;
  trained_through: string | null;
  home_team: string | null;
  away_team: string | null;
  competition_id: string | null;
  referee: string | null;
  referee_used: boolean;
  unknown_teams: string[];
  markets: PropMarket[];
  recent: { home?: PropRecent[]; away?: PropRecent[] };
  note: string;
}

export async function getMatchProps(matchId: string, signal?: AbortSignal): Promise<PropsResponse> {
  return apiClient.get(`/matches/${encodeURIComponent(matchId)}/props`, signal).json<PropsResponse>();
}

/** Loads the props once per match; null while loading or when the model is not available. */
export function useMatchProps(matchId: string | null | undefined, enabled = true): PropsResponse | null {
  const [data, setData] = useState<PropsResponse | null>(null);
  useEffect(() => {
    setData(null);
    if (!enabled || !matchId) return;
    const controller = new AbortController();
    getMatchProps(matchId, controller.signal)
      .then((d) => {
        if (!controller.signal.aborted) setData(d);
      })
      .catch(() => {
        // 503 (model not deployed) or a network error: the section stays hidden
      });
    return () => controller.abort();
  }, [matchId, enabled]);
  return data;
}
