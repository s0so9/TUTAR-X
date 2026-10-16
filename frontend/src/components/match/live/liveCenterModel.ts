/**
 * Pure helpers for the live match centre: ordering, grouping, formatting and
 * geometry. No value is invented here — every helper returns null (or the
 * "veri yok" label) when the source did not send the number.
 */

import type {
  LiveCenterPeriod,
  LiveCenterResponse,
  LiveCenterStatus,
  LiveEvent,
  LiveLineupPlayer,
  LiveLineupType,
  LiveShot,
  LiveStatGroup,
  LiveStatItem,
  LiveStats,
} from '../../../types/liveCenter';

export const UNAVAILABLE = 'veri yok';

/* ----------------------------------------------------------------- status */

export const IN_PLAY_STATUSES: ReadonlySet<LiveCenterStatus> = new Set(['LIVE', 'HALF_TIME', 'EXTRA_TIME', 'PENALTIES']);

export function isInPlay(status: LiveCenterStatus | null | undefined): boolean {
  return !!status && IN_PLAY_STATUSES.has(status);
}

/** Ball is rolling (not the half-time break): drives the pulse. */
export function isRunning(status: LiveCenterStatus | null | undefined): boolean {
  return status === 'LIVE' || status === 'EXTRA_TIME' || status === 'PENALTIES';
}

export function hasKickedOff(status: LiveCenterStatus | null | undefined): boolean {
  return isInPlay(status) || status === 'FINISHED' || status === 'ABANDONED';
}

const STATUS_LABELS: Record<LiveCenterStatus, string> = {
  SCHEDULED: 'Başlamadı',
  LIVE: 'Canlı',
  HALF_TIME: 'Devre arası',
  FINISHED: 'Maç sonu',
  POSTPONED: 'Ertelendi',
  CANCELLED: 'İptal',
  ABANDONED: 'Yarıda kaldı',
  EXTRA_TIME: 'Uzatmalar',
  PENALTIES: 'Penaltılar',
};

export function statusLabel(status: LiveCenterStatus): string {
  return STATUS_LABELS[status] ?? status;
}

const PERIOD_LABELS: Record<LiveCenterPeriod, string> = {
  '1H': '1. yarı',
  HT: 'Devre arası',
  '2H': '2. yarı',
  ET: 'Uzatma',
  PEN: 'Penaltılar',
  FT: 'Maç sonu',
};

export function periodLabel(period: LiveCenterPeriod | null | undefined): string | null {
  return period ? PERIOD_LABELS[period] ?? null : null;
}

/** "67'", "45+2'", or null when the source sent no minute. */
export function formatMinute(minute: number | null | undefined, addedTime?: number | null): string | null {
  if (typeof minute !== 'number' || !Number.isFinite(minute)) return null;
  return addedTime ? `${minute}+${addedTime}'` : `${minute}'`;
}

/** The clock line under the score. */
export function clockLabel(data: Pick<LiveCenterResponse, 'status' | 'minute' | 'added_time'>): string {
  if (data.status === 'LIVE' || data.status === 'EXTRA_TIME') {
    return formatMinute(data.minute, data.added_time) ?? statusLabel(data.status);
  }
  return statusLabel(data.status);
}

export function formatScorePair(score: { home: number | null; away: number | null } | null | undefined): string | null {
  if (!score || typeof score.home !== 'number' || typeof score.away !== 'number') return null;
  return `${score.home}–${score.away}`;
}

/* ----------------------------------------------------------------- events */

const PERIOD_RANK: Record<LiveCenterPeriod, number> = { '1H': 0, HT: 1, '2H': 2, ET: 3, PEN: 4, FT: 5 };

function periodRankOf(e: LiveEvent): number {
  if (e.period && e.period in PERIOD_RANK) return PERIOD_RANK[e.period];
  const m = typeof e.minute === 'number' ? e.minute : null;
  if (m === null) return 5;
  if (m <= 45) return 0;
  if (m <= 90) return 2;
  if (m <= 120) return 3;
  return 4;
}

/**
 * Chronological order (kick-off first): period, then period-end markers after
 * the events of their period, then minute, added time and source order.
 */
export function sortEvents(events: readonly LiveEvent[] | null | undefined): LiveEvent[] {
  if (!events) return [];
  return events
    .map((e, i) => ({ e, i }))
    .sort((a, b) => {
      const pa = periodRankOf(a.e);
      const pb = periodRankOf(b.e);
      if (pa !== pb) return pa - pb;
      const ea = a.e.type === 'period_end' ? 1 : 0;
      const eb = b.e.type === 'period_end' ? 1 : 0;
      if (ea !== eb) return ea - eb;
      const ma = typeof a.e.minute === 'number' ? a.e.minute : Number.MAX_SAFE_INTEGER;
      const mb = typeof b.e.minute === 'number' ? b.e.minute : Number.MAX_SAFE_INTEGER;
      if (ma !== mb) return ma - mb;
      const aa = a.e.added_time ?? 0;
      const ab = b.e.added_time ?? 0;
      if (aa !== ab) return aa - ab;
      return a.i - b.i;
    })
    .map(({ e }) => e);
}

export const GOAL_TYPES: ReadonlySet<LiveEvent['type']> = new Set(['goal', 'own_goal', 'penalty_goal']);

export function isGoalEvent(e: LiveEvent): boolean {
  return GOAL_TYPES.has(e.type);
}

/** Label for a period-end marker. */
export function periodEndLabel(e: LiveEvent): string {
  const code = (e.detail ?? '').trim().toUpperCase();
  if (code === 'HT') return 'Devre arası';
  if (code === 'FT') return 'Maç sonu';
  if (code === 'AET' || code === 'ET') return 'Uzatmalar sonu';
  if (code === 'PEN' || code === 'AP') return 'Penaltılar sonu';
  switch (e.period) {
    case '1H':
    case 'HT':
      return 'Devre arası';
    case '2H':
      return 'Normal süre sonu';
    case 'ET':
      return 'Uzatmalar sonu';
    case 'PEN':
      return 'Penaltılar sonu';
    case 'FT':
      return 'Maç sonu';
    default:
      return 'Periyot sonu';
  }
}

export function eventKey(e: LiveEvent, index: number): string {
  return e.id !== null && e.id !== undefined && e.id !== '' ? String(e.id) : `idx-${index}`;
}

/* ------------------------------------------------------------------ stats */

export const STAT_GROUP_ORDER: readonly LiveStatGroup[] = ['Genel', 'Şutlar', 'Pas', 'Savunma', 'Disiplin'];

export type StatHalf = 'all' | 'first_half' | 'second_half';

export const STAT_HALVES: readonly { key: StatHalf; label: string }[] = [
  { key: 'all', label: 'Tüm maç' },
  { key: 'first_half', label: '1. yarı' },
  { key: 'second_half', label: '2. yarı' },
];

export function statsForHalf(stats: LiveStats | null | undefined, half: StatHalf): LiveStatItem[] | null {
  if (!stats) return null;
  const items = stats[half];
  return Array.isArray(items) && items.length > 0 ? items : null;
}

export interface StatGroupBlock {
  group: string;
  items: LiveStatItem[];
}

/** Groups in the fixed order Genel → Disiplin (unknown groups after, as first seen); items keep source order. */
export function groupStats(items: readonly LiveStatItem[] | null | undefined): StatGroupBlock[] {
  if (!items || items.length === 0) return [];
  const byGroup = new Map<string, LiveStatItem[]>();
  for (const item of items) {
    const g = item.group || 'Genel';
    const list = byGroup.get(g);
    if (list) list.push(item);
    else byGroup.set(g, [item]);
  }
  const known = STAT_GROUP_ORDER.filter((g) => byGroup.has(g));
  const extra = [...byGroup.keys()].filter((g) => !(STAT_GROUP_ORDER as readonly string[]).includes(g));
  return [...known, ...extra].map((group) => ({ group, items: byGroup.get(group) as LiveStatItem[] }));
}

function isNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v);
}

/** Turkish percent sign placement in source text: "185 (70%)" → "185 (%70)". */
function turkishPercent(text: string): string {
  return text.replace(/(\d+(?:[.,]\d+)?)\s?%/g, '%$1');
}

export function formatStatValue(item: LiveStatItem, side: 'home' | 'away'): string {
  const v = item[side];
  // Percent stats read from the number ("%34"); the source text of e.g. pass accuracy
  // is "210 (74%)", which already shows on the accurate-passes row.
  if (item.unit === 'percent' && isNum(v)) return `%${Number.isInteger(v) ? v : v.toFixed(1)}`;
  const text = side === 'home' ? item.home_text : item.away_text;
  if (text !== null && text !== undefined && text !== '') return turkishPercent(text);
  if (!isNum(v)) return UNAVAILABLE;
  switch (item.unit) {
    case 'percent':
      return `%${Number.isInteger(v) ? v : v.toFixed(1)}`;
    case 'decimal':
      return v.toFixed(2);
    default:
      return Number.isInteger(v) ? String(v) : v.toFixed(1);
  }
}

/** Bar shares (0–1 each) or null when either side is missing. */
export function statShares(item: LiveStatItem): { home: number; away: number } | null {
  const h = item.home;
  const a = item.away;
  if (!isNum(h) || !isNum(a) || h < 0 || a < 0) return null;
  const total = h + a;
  if (total <= 0) return { home: 0, away: 0 };
  return { home: h / total, away: a / total };
}

export function statLeader(item: LiveStatItem): 'home' | 'away' | null {
  if (!isNum(item.home) || !isNum(item.away) || item.home === item.away) return null;
  return item.home > item.away ? 'home' : 'away';
}

/* ---------------------------------------------------------------- missing */

const SECTION_ALIASES: Record<string, string[]> = {
  events: ['events', 'event', 'timeline', 'incidents'],
  lineups: ['lineups', 'lineup', 'line_ups', 'squads', 'lineups.home', 'lineups.away'],
  stats: ['stats', 'statistics', 'stat'],
  first_half: ['first_half', 'stats.first_half', 'stats_first_half', 'stats.halves'],
  second_half: ['second_half', 'stats.second_half', 'stats_second_half', 'stats.halves'],
  shotmap: ['shotmap', 'shot_map', 'shots'],
  momentum: ['momentum'],
  unavailable: ['unavailable', 'injuries'],
  coach: ['coach', 'coaches'],
};

/** Reason the endpoint gave for a missing section, or null. */
export function missingReason(data: Pick<LiveCenterResponse, 'missing'> | null | undefined, section: string): string | null {
  const list = data?.missing;
  if (!Array.isArray(list)) return null;
  const names = SECTION_ALIASES[section] ?? [section];
  const hit = list.find((m) => names.includes(String(m.section).toLowerCase()));
  if (!hit) return null;
  return hit.message_tr || MISSING_REASON_TR[hit.reason] || hit.reason;
}

/** Turkish text for the endpoint's reason codes when it sends no message_tr. */
const MISSING_REASON_TR: Record<string, string> = {
  not_started: 'Maç henüz başlamadı.',
  not_provided: 'Kaynak (FotMob) bu bölümü göndermedi.',
  lineup_not_announced: 'Kadro henüz açıklanmadı.',
  no_layout: 'Kaynak saha dizilimi göndermedi.',
  shotmap_not_covered: 'Kaynak şut haritası göndermedi.',
  momentum_not_provided: 'Kaynak baskı grafiği göndermedi.',
  half_stats_not_provided: 'Kaynak devre bazlı istatistik göndermedi.',
  events_not_provided: 'Kaynak olay akışı göndermedi.',
};

/* ---------------------------------------------------------------- lineups */

const LINEUP_TYPE_LABELS: Record<LiveLineupType, string> = {
  confirmed: 'Kesin kadro',
  predicted: 'Tahmini kadro',
  last_starting11: 'Son maçtaki ilk 11',
};

export function lineupTypeLabel(t: LiveLineupType | null | undefined): string | null {
  return t ? LINEUP_TYPE_LABELS[t] ?? null : null;
}

const NAME_SUFFIXES = new Set(['júnior', 'junior', 'jr', 'jr.', 'filho', 'neto', 'sobrinho']);

/** Compact pitch label: surname, keeping suffixes such as "Júnior" with the word before. */
export function shortPlayerName(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length <= 1) return name.trim();
  const last = parts[parts.length - 1];
  if (NAME_SUFFIXES.has(last.toLowerCase())) return parts.slice(-2).join(' ');
  return last;
}

export type RatingTone = 'top' | 'good' | 'mid' | 'low';

export function ratingTone(rating: number): RatingTone {
  if (rating >= 8) return 'top';
  if (rating >= 7) return 'good';
  if (rating >= 6) return 'mid';
  return 'low';
}

export interface PitchSpot {
  player: LiveLineupPlayer;
  /** 0 = own goal line, 1 = halfway line */
  depth: number;
  /** 0–1 across the pitch in the team's own frame */
  lateral: number;
}

/**
 * Pitch positions from the source grid. Returns null when any starter lacks a
 * grid (the UI then lists the starters instead of guessing a shape).
 */
export function pitchLayout(starters: readonly LiveLineupPlayer[] | null | undefined): PitchSpot[] | null {
  if (!starters || starters.length === 0) return null;
  if (starters.some((p) => !p.grid || !isNum(p.grid.row) || !isNum(p.grid.col))) return null;
  const rows = [...new Set(starters.map((p) => (p.grid as NonNullable<LiveLineupPlayer['grid']>).row))].sort((a, b) => a - b);
  const gk = starters.find((p) => p.position === 'GK');
  const gkRow = gk?.grid?.row;
  if (rows.length > 1 && gkRow === rows[rows.length - 1]) rows.reverse();
  const n = rows.length;
  const spots: PitchSpot[] = [];
  rows.forEach((row, rank) => {
    const line = starters
      .filter((p) => p.grid?.row === row)
      .sort((a, b) => (a.grid?.col ?? 0) - (b.grid?.col ?? 0));
    const depth = n === 1 ? 0.5 : 0.08 + (rank / (n - 1)) * 0.82;
    line.forEach((player, i) => {
      spots.push({ player, depth, lateral: (i + 0.5) / line.length });
    });
  });
  return spots;
}

/* ---------------------------------------------------------------- shotmap */

export const PITCH_LENGTH = 105;
export const PITCH_WIDTH = 68;

/** Detects the coordinate frame once per map: fractions (0–1) or FotMob metres (105 × 68). */
export function shotFrame(shots: readonly LiveShot[]): 'fraction' | 'metres' {
  const coords = shots.filter((s) => isNum(s.x) && isNum(s.y));
  if (coords.length > 0 && coords.every((s) => s.x >= 0 && s.x <= 1 && s.y >= 0 && s.y <= 1)) return 'fraction';
  return 'metres';
}

/**
 * Point on a horizontal full pitch in metres (0–105 × 0–68). Home attacks to
 * the right, away to the left (rotated 180°). Null when the source sent no
 * coordinates.
 */
export function shotPoint(shot: LiveShot, frame: 'fraction' | 'metres'): { x: number; y: number } | null {
  if (!isNum(shot.x) || !isNum(shot.y)) return null;
  const fx = frame === 'fraction' ? shot.x : shot.x / PITCH_LENGTH;
  const fy = frame === 'fraction' ? shot.y : shot.y / PITCH_WIDTH;
  const cx = Math.min(1, Math.max(0, fx));
  const cy = Math.min(1, Math.max(0, fy));
  const px = shot.side === 'home' ? cx : 1 - cx;
  const py = shot.side === 'home' ? cy : 1 - cy;
  return { x: px * PITCH_LENGTH, y: py * PITCH_WIDTH };
}

export function shotRadius(xg: number | null): number {
  if (!isNum(xg) || xg <= 0) return 0.9;
  return 0.9 + Math.sqrt(Math.min(xg, 1)) * 2.6;
}

const OUTCOME_LABELS: Record<LiveShot['outcome'], string> = {
  goal: 'Gol',
  saved: 'Kurtarıldı',
  missed: 'Auta gitti',
  blocked: 'Engellendi',
  post: 'Direk',
};

export function shotOutcomeLabel(o: LiveShot['outcome']): string {
  return OUTCOME_LABELS[o] ?? o;
}

const SITUATION_LABELS: Record<string, string> = {
  regularplay: 'Akan oyun',
  openplay: 'Akan oyun',
  fastbreak: 'Hızlı hücum',
  setpiece: 'Duran top',
  fromcorner: 'Korner',
  corner: 'Korner',
  freekick: 'Serbest vuruş',
  directfreekick: 'Direkt serbest vuruş',
  penalty: 'Penaltı',
  throwinsetpiece: 'Taç',
};

const BODY_PART_LABELS: Record<string, string> = {
  leftfoot: 'Sol ayak',
  rightfoot: 'Sağ ayak',
  header: 'Kafa',
  head: 'Kafa',
  otherbodyparts: 'Diğer',
  other: 'Diğer',
};

function normaliseCode(s: string): string {
  return s.toLowerCase().replace(/[\s_-]/g, '');
}

export function shotSituationLabel(s: string | null | undefined): string | null {
  if (!s) return null;
  return SITUATION_LABELS[normaliseCode(s)] ?? s;
}

export function shotBodyPartLabel(s: string | null | undefined): string | null {
  if (!s) return null;
  return BODY_PART_LABELS[normaliseCode(s)] ?? s;
}

export interface ShotTotals {
  shots: number;
  goals: number;
  /** Sum over shots that carry xG; null when none does. */
  xg: number | null;
  /** Shots without an xG value (named in the UI, never counted as 0). */
  xgMissing: number;
}

export function shotTotals(shots: readonly LiveShot[], side: 'home' | 'away'): ShotTotals {
  const own = shots.filter((s) => s.side === side);
  const withXg = own.filter((s) => isNum(s.xg));
  return {
    shots: own.length,
    goals: own.filter((s) => s.outcome === 'goal').length,
    xg: withXg.length > 0 ? withXg.reduce((sum, s) => sum + (s.xg as number), 0) : null,
    xgMissing: own.length - withXg.length,
  };
}

/* --------------------------------------------------------------- momentum */

export function momentumSeries(points: readonly { minute: number; value: number }[] | null | undefined) {
  if (!points) return [];
  return points
    .filter((p) => isNum(p.minute) && isNum(p.value))
    .map((p) => ({ minute: p.minute, value: Math.max(-100, Math.min(100, p.value)) }))
    .sort((a, b) => a.minute - b.minute);
}
