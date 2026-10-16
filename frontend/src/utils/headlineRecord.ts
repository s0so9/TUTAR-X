/**
 * Display helpers for the frozen headline picks (api/headlineRecord.ts). Pure functions: every
 * number and label comes from the API payload; a missing value is said to be missing.
 */

import type { HeadlinePickItem, HeadlineResult, LineupType, MatchHeadlineRecord } from '../api/headlineRecord';

export interface ResultMark {
  /** What is printed: the two result marks of the product, or a dash for a void pick */
  symbol: string;
  /** Accessible and tooltip text */
  label: string;
}

/** null while the pick is not settled. */
export function resultMark(result: HeadlineResult): ResultMark | null {
  switch (result) {
    case 'won':
      return { symbol: '✅', label: 'Tuttu' };
    case 'lost':
      return { symbol: '❌', label: 'Tutmadı' };
    case 'void':
      return { symbol: '–', label: 'İptal (hit oranına dahil değil)' };
    default:
      return null;
  }
}

/** "%71", or "veri yok" while nothing is settled. */
export function formatRate(rate: number | null | undefined): string {
  if (typeof rate !== 'number' || !Number.isFinite(rate)) return 'veri yok';
  return `%${Math.round(rate * 100)}`;
}

/** "%81" for a probability in [0, 1]; "veri yok" when missing. */
export function formatProbability(p: number | null | undefined): string {
  if (typeof p !== 'number' || !Number.isFinite(p)) return 'veri yok';
  return `%${(p * 100).toFixed(0)}`;
}

/** "2–4"; "veri yok" when the pick has no final score (not played yet, or void). */
export function formatFinalScore(score: HeadlinePickItem['final_score']): string {
  if (!score || typeof score.home !== 'number' || typeof score.away !== 'number') return 'veri yok';
  return `${score.home}–${score.away}`;
}

const LINEUP_WORD: Record<Exclude<LineupType, null>, string> = {
  confirmed: 'resmi',
  predicted: 'tahmini',
  last_starting11: 'önceki maçın ilk 11\'i',
};

/** "resmi kadro" / "tahmini kadro" / mixed per side / "kadro bilgisi yok". */
export function describeLineup(lineup: HeadlinePickItem['lineup_type'] | null | undefined): string {
  const home = lineup?.home ?? null;
  const away = lineup?.away ?? null;
  if (home === null && away === null) return 'kadro bilgisi yok';
  if (home === away && home !== null) {
    return home === 'last_starting11' ? `kadro: ${LINEUP_WORD[home]}` : `${LINEUP_WORD[home]} kadro`;
  }
  const side = (value: LineupType) => (value === null ? 'bilgi yok' : LINEUP_WORD[value]);
  return `kadro: ev sahibi ${side(home)}, deplasman ${side(away)}`;
}

function describeTiming(pick: HeadlinePickItem): string {
  const manual = (pick.source ?? '').startsWith('manual_record');
  const minutes = pick.minutes_before_kickoff;
  if (typeof minutes !== 'number' || !Number.isFinite(minutes)) {
    return manual ? 'Elle kaydedildi' : 'Maç öncesi kaydedildi';
  }
  const rounded = Math.max(0, Math.round(minutes));
  if (manual) return `Maçtan ${rounded} dk önce elle kaydedildi`;
  return `Maçtan ${rounded} dk önce kaydedildi`;
}

/**
 * The one-line note under the Banko / Oranlı cards, e.g.
 * "Maçtan 20 dk önce kaydedildi · resmi kadro"; null when nothing was frozen for the match.
 */
export function describeFrozen(record: MatchHeadlineRecord | null | undefined): string | null {
  if (!record) return null;
  const reference = record.picks.banko ?? record.picks.oranli;
  if (!reference) return null;
  return `${describeTiming(reference)} · ${describeLineup(reference.lineup_type)}`;
}

// ------------------------------------------------------------------ "Ön tahmin" / "Kesin" (roadmap A1)

/**
 * Status of the pick a Banko / Oranlı card shows (roadmap A1: the owner bets on the "kesin" pick, and
 * "kesin" means the confirmed XI is in):
 *  - kesin: the frozen pick of its kind, frozen with confirmed line-ups on both sides; or, before any
 *    freeze, a pick computed from confirmed line-ups;
 *  - kaydedildi: the frozen pick of its kind, frozen without confirmed line-ups;
 *  - kayit_disi: the match was frozen, but this is not the frozen pick of its kind (the rule now gives
 *    another pick, or nothing of that kind was frozen); the tracker counts only the frozen one;
 *  - on_tahmin: nothing frozen yet, and the line-ups the pick was computed with are not confirmed.
 */
export type PickStatus = 'kesin' | 'kaydedildi' | 'kayit_disi' | 'on_tahmin';
export type PickStatusReason =
  | 'frozen'
  | 'frozen_unconfirmed'
  | 'differs_from_frozen'
  | 'not_frozen'
  | 'confirmed_lineups'
  | 'lineups_after_pick'
  | 'lineups_pending';

export interface PickStatusInfo {
  status: PickStatus;
  reason: PickStatusReason;
}

/** Line-up type per side as a source sends it (FotMob "standard" = confirmed). */
export interface SideLineups {
  home?: string | null;
  away?: string | null;
}

/** Same mapping as the backend (app/services/headline_tracking/sources.py normalise_lineup_type). */
function isConfirmedLineup(raw: string | null | undefined): boolean {
  const text = (raw ?? '').trim().toLowerCase();
  return text === 'confirmed' || text === 'standard';
}

function bothConfirmed(lineups: SideLineups | null | undefined): boolean {
  return !!lineups && isConfirmedLineup(lineups.home) && isConfirmedLineup(lineups.away);
}

/**
 * Whether the LIVE Banko / Oranlı on the match page (computed from the page's prediction) are final,
 * judged by the line-ups that prediction used. A frozen record is not considered here: whether a card
 * shows the frozen pick is decided per card (cardPickStatus).
 *  - the prediction used confirmed line-ups on both sides -> kesin;
 *  - otherwise on_tahmin; when the live centre already has confirmed line-ups the reason says the picks
 *    were computed before them. Predicted line-ups never make a pick final.
 */
export function headlinePickStatus({
  predictionLineups,
  centreLineups,
}: {
  /** prediction.squad_info.{home,away}.lineup_type: the line-ups the picks were computed with */
  predictionLineups: SideLineups | null | undefined;
  /** live centre lineups.{home,away}.lineup_type */
  centreLineups: SideLineups | null | undefined;
}): PickStatusInfo {
  if (bothConfirmed(predictionLineups)) return { status: 'kesin', reason: 'confirmed_lineups' };
  if (bothConfirmed(centreLineups)) return { status: 'on_tahmin', reason: 'lineups_after_pick' };
  return { status: 'on_tahmin', reason: 'lineups_pending' };
}

/** A frozen pick is kesin only when it was frozen with confirmed line-ups on both sides (roadmap A1). */
export function frozenPickStatus(frozen: HeadlinePickItem): PickStatusInfo {
  return bothConfirmed(frozen.lineup_type ?? null)
    ? { status: 'kesin', reason: 'frozen' }
    : { status: 'kaydedildi', reason: 'frozen_unconfirmed' };
}

export interface CardStatus {
  /** the pick the card leads with: its live pick, or the frozen one when there is no live pick */
  shown: PickStatusInfo;
  /** the frozen pick printed on its own "Kayıtlı seçim" line under a different live pick; else null */
  recorded: PickStatusInfo | null;
}

/**
 * Status of one card (Banko or Oranlı). Once the match was frozen, the frozen pick of the card's kind
 * decides:
 *  - the live pick is that frozen pick -> the frozen pick's status (kesin with confirmed line-ups; also
 *    kesin when the live prediction itself used confirmed line-ups);
 *  - the live pick is another pick -> kayit_disi, and the frozen pick's status goes on its own line;
 *  - no live pick -> the card shows the frozen pick only, with its status;
 *  - nothing of this kind was frozen -> the live pick is kayit_disi.
 * Before any freeze the live status (line-ups of the prediction) applies.
 */
export function cardPickStatus({
  livePickKey,
  frozen,
  matchFrozen,
  live,
}: {
  /** market key of the live pick; null when the rule gives none now */
  livePickKey: string | null;
  /** the frozen pick of the card's kind; null when none */
  frozen: HeadlinePickItem | null;
  /** the match has a frozen record (of either kind) */
  matchFrozen: boolean;
  /** status of the live picks (headlinePickStatus) */
  live: PickStatusInfo;
}): CardStatus {
  if (frozen) {
    const recorded = frozenPickStatus(frozen);
    if (livePickKey === null) return { shown: recorded, recorded: null };
    if (livePickKey !== frozen.market_key) {
      return { shown: { status: 'kayit_disi', reason: 'differs_from_frozen' }, recorded };
    }
    if (recorded.status !== 'kesin' && live.status === 'kesin') return { shown: live, recorded: null };
    return { shown: recorded, recorded: null };
  }
  if (matchFrozen && livePickKey !== null) return { shown: { status: 'kayit_disi', reason: 'not_frozen' }, recorded: null };
  return { shown: live, recorded: null };
}

export function pickStatusLabel(status: PickStatus): string {
  switch (status) {
    case 'kesin':
      return 'Kesin';
    case 'kaydedildi':
      return 'Kaydedildi';
    case 'kayit_disi':
      return 'Kayıtlı değil';
    default:
      return 'Ön tahmin';
  }
}

/**
 * One short line under the cards for a pick that is not final (shared by both cards); null when the
 * pick is final or the reason belongs inside its card (pickCardNote, or the "Kayıtlı seçim" line).
 */
export function pickStatusLine(info: PickStatusInfo): string | null {
  switch (info.reason) {
    case 'lineups_pending':
      return 'Kadrolar açıklanınca (maçtan ~20 dk önce) kesinleşir.';
    case 'lineups_after_pick':
      return 'Kadrolar açıklandı; bu seçim kadrolardan önce hesaplandı.';
    case 'frozen_unconfirmed':
      return 'Resmi kadrolar gelmeden kaydedildi; kesin sayılmaz.';
    default:
      return null;
  }
}

/** The lines under the cards for the cards that show a pick: each distinct line once, in card order. */
export function cardStatusLines(cards: CardStatus[]): string[] {
  const lines: string[] = [];
  for (const card of cards) {
    for (const info of [card.shown, card.recorded]) {
      const line = info ? pickStatusLine(info) : null;
      if (line && !lines.includes(line)) lines.push(line);
    }
  }
  return lines;
}

/** The note inside a card whose live pick was not recorded at all; null otherwise. */
export function pickCardNote(info: PickStatusInfo): string | null {
  return info.reason === 'not_frozen' ? 'Maç öncesi kayıtta bu seçim yoktu.' : null;
}

export interface MatchPickRow {
  match_id: string;
  home_team: string | null;
  away_team: string | null;
  competition_name: string | null;
  kickoff_at: string | null;
  banko: HeadlinePickItem | null;
  oranli: HeadlinePickItem | null;
  final_score: HeadlinePickItem['final_score'];
}

/** One row per match (Banko and Oranlı side by side), newest kick-off first. */
export function groupByMatch(picks: HeadlinePickItem[]): MatchPickRow[] {
  const rows = new Map<string, MatchPickRow>();
  for (const pick of picks) {
    let row = rows.get(pick.match_id);
    if (!row) {
      row = {
        match_id: pick.match_id,
        home_team: pick.home_team,
        away_team: pick.away_team,
        competition_name: pick.competition_name,
        kickoff_at: pick.kickoff_at,
        banko: null,
        oranli: null,
        final_score: null,
      };
      rows.set(pick.match_id, row);
    }
    row[pick.kind] = pick;
    if (pick.final_score && !row.final_score) row.final_score = pick.final_score;
  }
  const time = (row: MatchPickRow) => (row.kickoff_at ? Date.parse(row.kickoff_at) : Number.NEGATIVE_INFINITY);
  return [...rows.values()].sort((a, b) => time(b) - time(a) || a.match_id.localeCompare(b.match_id));
}

/** Short line-up word for a table cell. */
export function lineupWord(lineup: HeadlinePickItem['lineup_type'] | null | undefined): string {
  const home = lineup?.home ?? null;
  const away = lineup?.away ?? null;
  if (home === null && away === null) return 'veri yok';
  if (home === away) return home === 'confirmed' ? 'Resmi' : home === 'predicted' ? 'Tahmini' : 'Önceki ilk 11';
  return 'Karışık';
}
