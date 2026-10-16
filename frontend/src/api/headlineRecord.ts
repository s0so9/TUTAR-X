/**
 * Track record of the headline picks (Banko / Oranlı) the backend freezes shortly before kick-off.
 *
 *   GET /api/v1/track-record/headline?days=30&rule_version=headline_v2&competition_id=42
 *   GET /api/v1/matches/{match_id}/headline-record
 *
 * Contract: backend/app/api/v1/endpoints/track_record.py. Missing values are null, never 0.
 */

import { useCallback, useEffect, useState } from 'react';
import { apiClient } from './client';
import type { BankoTier } from '../utils/headlinePicks';

export type HeadlineKind = 'banko' | 'oranli';
/** null = not settled yet */
export type HeadlineResult = 'won' | 'lost' | 'void' | null;
export type LineupType = 'confirmed' | 'predicted' | 'last_starting11' | null;

export interface HeadlinePickItem {
  id: string;
  match_id: string;
  kind: HeadlineKind;
  stage: string;
  home_team: string | null;
  away_team: string | null;
  competition_id: string | null;
  competition_name: string | null;
  kickoff_at: string | null;
  frozen_at: string | null;
  minutes_before_kickoff: number | null;
  market_key: string;
  /** compact label, e.g. "1X", "2.5 Üst", "KG Var" */
  label: string;
  selection_text: string | null;
  market_name: string | null;
  probability: number | null;
  fair_odds: number | null;
  /** bookmaker odds at freeze time; null = none known */
  odds: number | null;
  lineup_type: { home: LineupType; away: LineupType; source: string | null };
  model_1x2: { home: number | null; draw: number | null; away: number | null } | null;
  result: HeadlineResult;
  final_score: { home: number | null; away: number | null; extra_time?: boolean | null } | null;
  settled_at: string | null;
  source: string | null;
  rule_version: string | null;
  /** Banko tier derived from the stored probability; null for the Oranlı (absent before headline_v2) */
  tier?: BankoTier | null;
}

export interface KindSummary {
  won: number;
  lost: number;
  void: number;
  pending: number;
  /** won + lost */
  settled: number;
  /** won / (won + lost); null while nothing is settled */
  hit_rate: number | null;
}

export interface KindPair {
  /** every frozen Banko slot pick, the güçlü (0.70-0.85, not a Banko) ones included */
  banko: KindSummary;
  oranli: KindSummary;
  /** the Bankos with p >= 0.85 only (tiers banko + cok_guclu); absent before headline_v2 */
  banko_strong?: KindSummary;
}

/** The Banko picks of the period per tier (derived from the stored probability). */
export type BankoTierSummaries = Record<BankoTier, KindSummary>;

/** Every recorded Banko with p >= min_probability of the rule version (all time, all competitions). */
export interface BankoProgress extends KindSummary {
  rule_version: string;
  min_probability: number;
  /** recorded Bankos needed before a ~90 % hit rate can be checked */
  target: number;
}

export interface CompetitionRow extends KindPair {
  competition_id: string | null;
  competition_name: string | null;
  total: number;
}

export interface WeekRow extends KindPair {
  /** Monday (UTC) of the week of the kick-off, YYYY-MM-DD */
  week_start: string;
}

export interface HeadlineTrackRecord {
  generated_at: string;
  days: number;
  competition_id: string | null;
  /** The fields below are absent when the backend predates headline_v2. */
  /** rule version shown ("all" = every version) */
  rule_version?: string;
  current_rule_version?: string;
  available_rule_versions?: string[];
  summary: KindPair;
  banko_tiers?: BankoTierSummaries;
  banko_progress?: BankoProgress;
  by_competition: CompetitionRow[];
  by_week: WeekRow[];
  available_competitions: { id: string; name: string }[];
  picks: HeadlinePickItem[];
  note: string;
}

export interface MatchHeadlineRecord {
  match_id: string;
  frozen: boolean;
  picks: { banko: HeadlinePickItem | null; oranli: HeadlinePickItem | null };
}

export async function getHeadlineTrackRecord(
  days: number,
  competitionId: string | null,
  ruleVersion: string | null = null,
  signal?: AbortSignal,
): Promise<HeadlineTrackRecord> {
  const query = new URLSearchParams({ days: String(days) });
  if (ruleVersion) query.set('rule_version', ruleVersion);
  if (competitionId) query.set('competition_id', competitionId);
  return apiClient.get(`/track-record/headline?${query.toString()}`, signal).json<HeadlineTrackRecord>();
}

export async function getMatchHeadlineRecord(matchId: string, signal?: AbortSignal): Promise<MatchHeadlineRecord> {
  return apiClient.get(`/matches/${encodeURIComponent(matchId)}/headline-record`, signal).json<MatchHeadlineRecord>();
}

function isAbort(err: unknown): boolean {
  return (err instanceof DOMException || err instanceof Error) && err.name === 'AbortError';
}

export type LoadState = 'loading' | 'ready' | 'error';

/**
 * The track record for a period, a rule version and an optional competition; reloads when one changes.
 * The last answer stays in `data` while the next one loads (or after it failed); `dataRuleVersion` is the
 * rule version that answer was requested for, so a page never shows one version's figures under another.
 */
export function useHeadlineTrackRecord(days: number, competitionId: string | null, ruleVersion: string | null = null) {
  const [loaded, setLoaded] = useState<{ data: HeadlineTrackRecord; ruleVersion: string | null } | null>(null);
  const [state, setState] = useState<LoadState>('loading');
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState('loading');
    getHeadlineTrackRecord(days, competitionId, ruleVersion, controller.signal)
      .then((d) => {
        if (controller.signal.aborted) return;
        setLoaded({ data: d, ruleVersion });
        setState('ready');
      })
      .catch((err) => {
        if (controller.signal.aborted || isAbort(err)) return;
        setState('error');
      });
    return () => controller.abort();
  }, [days, competitionId, ruleVersion, reloadKey]);

  const reload = useCallback(() => setReloadKey((k) => k + 1), []);
  return { data: loaded?.data ?? null, dataRuleVersion: loaded?.ruleVersion ?? null, state, reload };
}

export const RECORD_POLL_MS = 60_000;
/** More than this long before kick-off nothing is frozen yet: look again only every 5 minutes. */
export const RECORD_NEAR_KICKOFF_MS = 3 * 3_600_000;
export const RECORD_POLL_SLOW_MS = 300_000;
/** A match is followed from this long before kick-off until this long after it. */
export const RECORD_FOLLOW_BEFORE_KICKOFF_MS = 48 * 3_600_000;
export const RECORD_FOLLOW_AFTER_KICKOFF_MS = 6 * 3_600_000;

/**
 * The frozen Banko / Oranlı of one match. While the match is upcoming or only just over, the record
 * is re-read every minute until both picks are frozen and settled (the backend freezes ~20 minutes
 * before kick-off and settles shortly after full time); an old match is read once. A failed request
 * leaves the page without the note; nothing is guessed.
 */
export function useMatchHeadlineRecord(
  matchId: string | null | undefined,
  kickoffAt: string | null | undefined,
): MatchHeadlineRecord | null {
  const [record, setRecord] = useState<MatchHeadlineRecord | null>(null);

  useEffect(() => {
    setRecord(null);
    if (!matchId) return;
    const controller = new AbortController();
    const kickoff = kickoffAt ? Date.parse(kickoffAt) : NaN;
    // follow from 2 days before kick-off (slowly) until 6 hours after it; other matches are read once
    const sinceKickoff = Date.now() - kickoff;
    const follow =
      Number.isFinite(kickoff) && sinceKickoff > -RECORD_FOLLOW_BEFORE_KICKOFF_MS && sinceKickoff < RECORD_FOLLOW_AFTER_KICKOFF_MS;
    const interval = sinceKickoff < -RECORD_NEAR_KICKOFF_MS ? RECORD_POLL_SLOW_MS : RECORD_POLL_MS;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const load = () => {
      getMatchHeadlineRecord(matchId, controller.signal)
        .then((d) => {
          if (controller.signal.aborted) return;
          setRecord(d);
          const open = [d.picks.banko, d.picks.oranli].some((p) => p !== null && p.result === null);
          if (follow && (!d.frozen || open)) timer = setTimeout(load, interval);
        })
        .catch(() => {
          // endpoint not available or network error: the match page simply shows no note
        });
    };
    load();
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [matchId, kickoffAt]);

  return record;
}
