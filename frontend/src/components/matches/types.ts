/**
 * Shared types for match list components.
 */

import type { MatchPredictionResponse, MatchResponse, MatchStatus } from '../../api/types';
import { normalizeMatch } from '../../utils/matchNormalizer';
import { isAvailableNumber } from '../../utils/displayValue';

export interface MatchRowTeam {
  name: string;
  logoUrl?: string | null;
  code?: string | null;
}

/** Model 1·X·2 probabilities (0-1) exactly as the prediction engine returned them. */
export interface MatchProbabilities {
  home: number | null;
  draw: number | null;
  away: number | null;
}

export interface MatchRowData {
  id: string;
  homeTeam: MatchRowTeam;
  awayTeam: MatchRowTeam;
  /** ISO8601 UTC kickoff time */
  scheduledAt: string;
  status: MatchStatus;
  homeScore: number | null;
  awayScore: number | null;
  minute?: number | null;
  competitionName?: string;
  /** Model 1·X·2 probabilities, only when a prediction is already loaded for this match. */
  probabilities?: MatchProbabilities | null;
}

/**
 * Convert an API match into row data. Team names go through the shared
 * normalizer so missing names render as "Takım bilgisi yok", never as raw IDs.
 */
export function toMatchRowData(match: MatchResponse, competitionName?: string): MatchRowData {
  const normalized = normalizeMatch(match);
  return {
    id: match.id,
    homeTeam: {
      name: normalized.homeTeam.name,
      logoUrl: normalized.homeTeam.logoUrl ?? null,
      code: normalized.homeTeam.code ?? null,
    },
    awayTeam: {
      name: normalized.awayTeam.name,
      logoUrl: normalized.awayTeam.logoUrl ?? null,
      code: normalized.awayTeam.code ?? null,
    },
    scheduledAt: match.scheduled_at,
    status: match.status,
    homeScore: match.home_score,
    awayScore: match.away_score,
    minute: match.minute,
    competitionName: competitionName ?? match.competition_name ?? undefined,
  };
}

/** Scores are only meaningful once a match has started. */
export function hasDisplayableScore(match: Pick<MatchRowData, 'status' | 'homeScore' | 'awayScore'>): boolean {
  return (
    (match.status === 'LIVE' || match.status === 'FINISHED') &&
    match.homeScore !== null &&
    match.awayScore !== null
  );
}

/**
 * 1·X·2 probabilities from a loaded prediction (values passed through unchanged).
 * Returns null when there is no prediction.
 */
export function probabilitiesFromPrediction(
  prediction:
    | Pick<MatchPredictionResponse, 'home_win_probability' | 'draw_probability' | 'away_win_probability'>
    | null
    | undefined
): MatchProbabilities | null {
  if (!prediction) return null;
  const pick = (value: number | null | undefined) => (isAvailableNumber(value) ? value : null);
  return {
    home: pick(prediction.home_win_probability),
    draw: pick(prediction.draw_probability),
    away: pick(prediction.away_win_probability),
  };
}

/** True when all three outcome probabilities are real numbers. */
export function hasCompleteProbabilities(
  probabilities: MatchProbabilities | null | undefined
): probabilities is { home: number; draw: number; away: number } {
  return (
    !!probabilities &&
    isAvailableNumber(probabilities.home) &&
    isAvailableNumber(probabilities.draw) &&
    isAvailableNumber(probabilities.away)
  );
}

/**
 * Language for a provider league name, so tracked small caps follow the right
 * casing rules ("Champions League" must not become "CHAMPİONS"; "Süper Lig"
 * keeps its dotted İ).
 */
export function leagueNameLang(name: string): 'tr' | 'en' {
  return /[çğışöüÇĞİŞÖÜ]|\bLig\b|\bKupas/.test(name) ? 'tr' : 'en';
}
