/**
 * Formatting helpers shared by the rail-line list surfaces
 * (match centre, dashboard ledger, live list).
 */

import type { MatchStatus } from '../../api/types';
import { MANUAL_ODDS_LABEL, isManualUserSuppliedOdds } from '../../utils/pickMarket';

export type MatchLineTone = 'scheduled' | 'live' | 'finished' | 'off';

/** Visible key note and accessible status text per match status. */
export const MATCH_STATUS_TEXT: Record<MatchStatus, { note: string | null; aria: string }> = {
  SCHEDULED: { note: null, aria: 'Yaklaşan maç' },
  LIVE: { note: 'Canlı', aria: 'Canlı maç' },
  FINISHED: { note: 'MS', aria: 'Maç sonu' },
  POSTPONED: { note: 'Ert.', aria: 'Maç ertelendi' },
  CANCELLED: { note: 'İptal', aria: 'Maç iptal edildi' },
  SUSPENDED: { note: 'Askıda', aria: 'Maç askıya alındı' },
};

export function matchLineTone(status: MatchStatus): MatchLineTone {
  if (status === 'LIVE') return 'live';
  if (status === 'FINISHED') return 'finished';
  if (status === 'SCHEDULED') return 'scheduled';
  return 'off';
}

/** Kickoff time in Europe/Istanbul, e.g. "22:00"; null for an invalid date. */
export function formatKickoffTime(isoDate: string): string | null {
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleTimeString('tr-TR', {
    timeZone: 'Europe/Istanbul',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Live minute as the source sent it ("67'", "90+3'"); null when the source has no minute. */
export function formatLiveMinute(
  minute: number | null | undefined,
  addedTime?: number | null
): string | null {
  if (minute === null || minute === undefined || !Number.isFinite(minute)) return null;
  return addedTime ? `${minute}+${addedTime}'` : `${minute}'`;
}

/** Compact whole-number percentage for dense list columns (full value goes in the tooltip). */
export function formatCompactPercent(value: number): string {
  return `${Math.round(value * 100)}`;
}

export interface OddsProvenance {
  /** Short apparatus label shown under the odds figure. */
  compact: string;
  /** Full label for tooltips and screen readers. */
  full: string;
  /** True for user-entered odds that nobody has verified. */
  unverified: boolean;
}

/**
 * Where a bookmaker price came from. User-entered odds are always labelled
 * unverified; other sources are named as the backend sent them.
 * Returns null when there is no price at all.
 */
export function describeOddsProvenance(
  odds: number | null | undefined,
  source: string | null | undefined
): OddsProvenance | null {
  if (odds === null || odds === undefined || !Number.isFinite(odds) || odds <= 1) return null;
  if (isManualUserSuppliedOdds(source)) {
    return { compact: 'Kullanıcı oranı · doğrulanmadı', full: MANUAL_ODDS_LABEL, unverified: true };
  }
  const name = typeof source === 'string' ? source.trim() : '';
  if (!name) {
    return { compact: 'Kaynak bilgisi yok', full: 'Oran kaynağı bilgisi yok', unverified: false };
  }
  return { compact: `Kaynak: ${name}`, full: `Oran kaynağı: ${name}`, unverified: false };
}
