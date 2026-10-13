/**
 * Builds the centre-rail rows of the match page from a prediction response.
 *
 * Pure functions only: every number comes from the API response, nothing is
 * invented. Missing values stay null and are rendered as "veri yok".
 */

import type { MarketAnalysisResponse, MarketOutcomeResponse, MatchPredictionResponse } from '../../../api/types';

export type RailSlot = 'left' | 'centre' | 'right';

export interface RailOutcome {
  /** Backend selector key, e.g. HOME_WIN, OVER_2_5, BTTS_YES */
  key: string;
  /** Short label printed in the cell, e.g. "1", "Üst", "Var" */
  short: string;
  /** Turkish market name for the kombine and the apparatus */
  marketName: string;
  /** Turkish outcome text for the kombine and the apparatus */
  outcomeName: string;
  /** Model probability (calibrated when available) */
  probability: number | null;
  /** Market probability with the bookmaker margin removed; null without full odds */
  marketProbability: number | null;
  /** Raw bookmaker-implied probability (1 / odds, margin included) */
  impliedProbability: number | null;
  odds: number | null;
  oddsSource: string | null;
  fairOdds: number | null;
  expectedValuePercent: number | null;
  valueClassification: string | null;
  /**
   * Another outcome of the same family (1X2 + double chance, or goal lines +
   * both teams to score) is a model–market conflict. Mirrors the backend
   * selector's family propagation: such outcomes are never shown as value.
   */
  familyConflict: boolean;
}

export interface RailRow {
  id: string;
  /** Label printed on the rail key */
  key: string;
  /** Second line under the rail key (e.g. the line "2.5") */
  keySub?: string;
  left: RailOutcome | null;
  centre: RailOutcome | null;
  right: RailOutcome | null;
}

function modelProbability(outcome: MarketOutcomeResponse | undefined): number | null {
  if (!outcome) return null;
  const p = outcome.calibrated_probability ?? outcome.model_probability;
  return typeof p === 'number' && Number.isFinite(p) ? p : null;
}

function findMarket(
  markets: MarketAnalysisResponse[] | null | undefined,
  type: string,
  line?: number,
): MarketAnalysisResponse | undefined {
  return (markets ?? []).find(
    (m) => m.market_type === type && (line === undefined || m.line === line),
  );
}

function findOutcome(market: MarketAnalysisResponse | undefined, test: (label: string) => boolean) {
  return market?.outcomes.find((o) => test(o.label.trim().toLowerCase()));
}

/** Market probabilities with the margin removed, when every outcome has odds. */
function fairMarketProbabilities(outcomes: (MarketOutcomeResponse | undefined)[]): (number | null)[] {
  const odds = outcomes.map((o) => (o?.real_odds && o.real_odds > 1 ? o.real_odds : null));
  if (odds.some((x) => x === null)) return odds.map(() => null);
  const inverse = odds.map((x) => 1 / (x as number));
  const total = inverse.reduce((a, b) => a + b, 0);
  return inverse.map((x) => x / total);
}

function toOutcome(
  source: MarketOutcomeResponse | undefined,
  marketProbability: number | null,
  meta: { key: string; short: string; marketName: string; outcomeName: string },
  fallbackProbability: number | null = null,
): RailOutcome {
  const probability = modelProbability(source) ?? fallbackProbability;
  const odds = source?.real_odds && source.real_odds > 1 ? source.real_odds : null;
  return {
    ...meta,
    probability,
    marketProbability,
    impliedProbability: odds ? 1 / odds : null,
    odds,
    oddsSource: source?.bookmaker ?? null,
    fairOdds: probability && probability > 0 ? 1 / probability : null,
    expectedValuePercent: source?.expected_value_percent ?? null,
    valueClassification: source?.value_classification ?? null,
    familyConflict: false,
  };
}

/** Rows of the rail, top to bottom: result, double chance, goal lines, both teams to score. */
export function buildRailRows(
  prediction: MatchPredictionResponse,
  teams: { home: string; away: string },
): RailRow[] {
  const markets = prediction.market_analysis;
  const rows: RailRow[] = [];

  // Match result (1 · X · 2) — falls back to the top-level probabilities
  const result = findMarket(markets, 'match_result');
  const home = findOutcome(result, (l) => l === 'home');
  const draw = findOutcome(result, (l) => l === 'draw');
  const away = findOutcome(result, (l) => l === 'away');
  const [mHome, mDraw, mAway] = fairMarketProbabilities([home, draw, away]);
  rows.push({
    id: 'result',
    key: 'Maç sonucu',
    left: toOutcome(home, mHome, { key: 'HOME_WIN', short: '1', marketName: 'Maç Sonucu', outcomeName: `${teams.home} kazanır` }, prediction.home_win_probability),
    centre: toOutcome(draw, mDraw, { key: 'DRAW', short: 'X', marketName: 'Maç Sonucu', outcomeName: 'Beraberlik' }, prediction.draw_probability),
    right: toOutcome(away, mAway, { key: 'AWAY_WIN', short: '2', marketName: 'Maç Sonucu', outcomeName: `${teams.away} kazanır` }, prediction.away_win_probability),
  });

  // Double chance
  const dc = findMarket(markets, 'double_chance');
  if (dc) {
    const o1x = findOutcome(dc, (l) => l === '1x');
    const o12 = findOutcome(dc, (l) => l === '12');
    const ox2 = findOutcome(dc, (l) => l === 'x2');
    // Double-chance outcomes overlap, so no margin-free market probability is derived.
    rows.push({
      id: 'double-chance',
      key: 'Çifte şans',
      left: toOutcome(o1x, null, { key: 'HOME_OR_DRAW', short: '1X', marketName: 'Çifte Şans', outcomeName: `1X (${teams.home} veya beraberlik)` }),
      centre: toOutcome(o12, null, { key: 'HOME_OR_AWAY', short: '12', marketName: 'Çifte Şans', outcomeName: '12 (beraberlik olmaz)' }),
      right: toOutcome(ox2, null, { key: 'DRAW_OR_AWAY', short: 'X2', marketName: 'Çifte Şans', outcomeName: `X2 (beraberlik veya ${teams.away})` }),
    });
  }

  // Goal lines: Alt on the left, Üst on the right
  for (const line of [1.5, 2.5, 3.5]) {
    const market = findMarket(markets, `OVER_UNDER_${String(line).replace('.', '_')}`, line);
    if (!market) continue;
    const under = findOutcome(market, (l) => l.startsWith('under'));
    const over = findOutcome(market, (l) => l.startsWith('over'));
    const [mUnder, mOver] = fairMarketProbabilities([under, over]);
    const suffix = String(line).replace('.', '_');
    rows.push({
      id: `goals-${suffix}`,
      key: 'Gol',
      keySub: line.toFixed(1),
      left: toOutcome(under, mUnder, { key: `UNDER_${suffix}`, short: 'Alt', marketName: `Alt/Üst ${line.toFixed(1)} Gol`, outcomeName: `Alt ${line.toFixed(1)}` }),
      centre: null,
      right: toOutcome(over, mOver, { key: `OVER_${suffix}`, short: 'Üst', marketName: `Alt/Üst ${line.toFixed(1)} Gol`, outcomeName: `Üst ${line.toFixed(1)}` }),
    });
  }

  // Both teams to score: Yok on the left, Var on the right
  const btts = findMarket(markets, 'btts');
  const no = findOutcome(btts, (l) => l === 'no');
  const yes = findOutcome(btts, (l) => l === 'yes');
  const [mNo, mYes] = fairMarketProbabilities([no, yes]);
  const yesFallback = Number.isFinite(prediction.btts_probability) ? prediction.btts_probability : null;
  rows.push({
    id: 'btts',
    key: 'Karşılıklı gol',
    left: toOutcome(no, mNo, { key: 'BTTS_NO', short: 'Yok', marketName: 'Karşılıklı Gol', outcomeName: 'KG Yok' }, yesFallback === null ? null : 1 - yesFallback),
    centre: null,
    right: toOutcome(yes, mYes, { key: 'BTTS_YES', short: 'Var', marketName: 'Karşılıklı Gol', outcomeName: 'KG Var' }, yesFallback),
  });

  markFamilyConflicts(rows);
  return rows;
}

const RESULT_FAMILY = new Set(['result', 'double-chance']);

function isConflict(outcome: RailOutcome | null): boolean {
  return (outcome?.valueClassification ?? '').toUpperCase() === 'MODEL_MARKET_CONFLICT';
}

/** Flags every outcome whose family (result or goals) contains a conflict. */
export function markFamilyConflicts(rows: RailRow[]): void {
  const families = [
    rows.filter((r) => RESULT_FAMILY.has(r.id)),
    rows.filter((r) => !RESULT_FAMILY.has(r.id)),
  ];
  for (const family of families) {
    const outcomes = family.flatMap((r) => [r.left, r.centre, r.right]).filter((o): o is RailOutcome => o !== null);
    if (outcomes.some(isConflict)) {
      for (const o of outcomes) o.familyConflict = !isConflict(o);
    }
  }
}

/** Final-score outcome keys that came true, for marking settled rows. */
export function settledOutcomeKeys(homeScore: number, awayScore: number): Set<string> {
  const keys = new Set<string>();
  const total = homeScore + awayScore;
  if (homeScore > awayScore) keys.add('HOME_WIN');
  else if (homeScore === awayScore) keys.add('DRAW');
  else keys.add('AWAY_WIN');
  if (homeScore >= awayScore) keys.add('HOME_OR_DRAW');
  if (homeScore !== awayScore) keys.add('HOME_OR_AWAY');
  if (homeScore <= awayScore) keys.add('DRAW_OR_AWAY');
  for (const line of [0.5, 1.5, 2.5, 3.5, 4.5]) {
    const suffix = String(line).replace('.', '_');
    keys.add(total > line ? `OVER_${suffix}` : `UNDER_${suffix}`);
  }
  keys.add(homeScore > 0 && awayScore > 0 ? 'BTTS_YES' : 'BTTS_NO');
  return keys;
}

/** Turkish text for the selector's pass reasons. Unknown reasons fall back to a neutral sentence. */
export function describePassReason(reason: string | null | undefined): string {
  switch ((reason ?? '').trim().toLowerCase()) {
    case 'model_market_conflict':
      return 'Model ile piyasa bu maçta çelişiyor; görünen "değer" büyük olasılıkla model hatası.';
    case 'insufficient_value':
      return 'Oranlarda inanılır bir değer yok.';
    case 'negative_value':
      return 'Bütün pazarlarda oranlar modelin aleyhine.';
    case 'high_uncertainty':
      return 'Belirsizlik çok yüksek.';
    case 'weak_agreement':
      return 'Hiçbir pazar olasılık eşiğini geçmiyor.';
    case 'low_confidence':
      return 'Güven eşiğin altında.';
    default:
      return 'Eşikleri geçen bir pazar yok.';
  }
}

/** Turkish percentage ("%77"), or "veri yok" when missing. */
export function pct(value: number | null | undefined, digits = 0): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'veri yok';
  return `%${(value * 100).toFixed(digits)}`;
}

/** Signed percentage-point difference ("+4.7 puan"), or "veri yok". */
export function points(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'veri yok';
  const v = value * 100;
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)} puan`;
}
