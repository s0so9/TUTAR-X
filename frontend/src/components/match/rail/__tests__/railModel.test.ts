/**
 * Centre-rail row model tests.
 * The prediction below is a TEST FIXTURE (mock data), not real football data.
 */

import { describe, expect, it } from 'vitest';
import type { MarketAnalysisResponse, MatchPredictionResponse } from '../../../../api/types';
import { buildRailRows, describePassReason, pct, points, settledOutcomeKeys } from '../railModel';
import { marketLine } from '../marketLine';

function outcome(label: string, p: number, odds: number | null = null, valueClassification: string | null = null) {
  return {
    label,
    model_probability: p,
    calibrated_probability: p,
    fair_odds: 1 / p,
    real_odds: odds,
    bookmaker: odds ? 'manual_user_supplied' : null,
    value_classification: valueClassification,
    expected_value_percent: null,
  };
}

function market(market_type: string, line: number | null, outcomes: ReturnType<typeof outcome>[]): MarketAnalysisResponse {
  return { market_type, line, outcomes, bookmaker_comparison: null, bookmaker_overround: null, has_bookmaker_odds: true };
}

const MOCK_PREDICTION = {
  match_id: 'mock_1',
  home_win_probability: 0.5,
  draw_probability: 0.25,
  away_win_probability: 0.25,
  home_xg: 1.6,
  away_xg: 1.1,
  btts_probability: 0.55,
  predicted_score: '1-1',
  mensione_pick: null,
  prediction_version_id: null,
  easy_match: null,
  home_form: null,
  away_form: null,
  head_to_head: null,
  shot_markets: null,
  is_development_data: false,
  market_analysis: [
    market('match_result', null, [outcome('Home', 0.5, 2.0), outcome('Draw', 0.25, 4.0), outcome('Away', 0.25, 4.0)]),
    market('double_chance', null, [outcome('1X', 0.75, 1.3, 'VALUE'), outcome('12', 0.75, 1.4), outcome('X2', 0.5, 2.1)]),
    market('OVER_UNDER_2_5', 2.5, [outcome('Over 2.5 Goals', 0.6, 1.8), outcome('Under 2.5 Goals', 0.4, 2.2)]),
    market('btts', null, [outcome('Yes', 0.55, 1.9), outcome('No', 0.45, 2.0)]),
  ],
} as unknown as MatchPredictionResponse;

describe('buildRailRows', () => {
  const rows = buildRailRows(MOCK_PREDICTION, { home: 'Ev FK', away: 'Dep SK' });

  it('orders rows result, double chance, goal lines, btts', () => {
    expect(rows.map((r) => r.id)).toEqual(['result', 'double-chance', 'goals-2_5', 'btts']);
  });

  it('puts home / draw / away on left / centre / right with margin-free market probabilities', () => {
    const result = rows[0];
    expect(result.left?.key).toBe('HOME_WIN');
    expect(result.centre?.key).toBe('DRAW');
    expect(result.right?.outcomeName).toBe('Dep SK kazanır');
    // 1/2 + 1/4 + 1/4 = 1 → no margin in this fixture
    expect(result.left?.marketProbability).toBeCloseTo(0.5);
    expect(result.left?.impliedProbability).toBeCloseTo(0.5);
  });

  it('puts Alt on the left and Üst on the right of a goal line', () => {
    const goals = rows[2];
    expect(goals.keySub).toBe('2.5');
    expect(goals.left?.key).toBe('UNDER_2_5');
    expect(goals.right?.key).toBe('OVER_2_5');
  });

  it('never derives a market probability for overlapping double-chance outcomes', () => {
    expect(rows[1].left?.marketProbability).toBeNull();
    expect(rows[1].left?.odds).toBe(1.3);
  });

  it('keeps missing odds as null instead of zero', () => {
    const noOdds = buildRailRows(
      { ...MOCK_PREDICTION, market_analysis: [] } as MatchPredictionResponse,
      { home: 'H', away: 'A' },
    );
    expect(noOdds[0].left?.probability).toBe(0.5); // falls back to the top-level probability
    expect(noOdds[0].left?.odds).toBeNull();
    expect(noOdds[0].left?.marketProbability).toBeNull();
  });
});

describe('family conflicts', () => {
  it('stops value labels in a family that contains a model–market conflict', () => {
    const conflicted = {
      ...MOCK_PREDICTION,
      market_analysis: [
        market('match_result', null, [outcome('Home', 0.2, 2.7), outcome('Draw', 0.2, 3.5), outcome('Away', 0.6, 2.45, 'MODEL_MARKET_CONFLICT')]),
        market('double_chance', null, [outcome('1X', 0.4, 1.5), outcome('12', 0.8, 1.3, 'VALUE'), outcome('X2', 0.8, 1.45, 'VALUE')]),
        market('OVER_UNDER_2_5', 2.5, [outcome('Over 2.5 Goals', 0.6, 1.8, 'VALUE'), outcome('Under 2.5 Goals', 0.4, 2.2)]),
      ],
    } as unknown as MatchPredictionResponse;
    const rows = buildRailRows(conflicted, { home: 'H', away: 'A' });
    expect(rows[1].centre?.familyConflict).toBe(true); // 12
    expect(rows[1].right?.familyConflict).toBe(true); // X2
    expect(rows[0].right?.familyConflict).toBe(false); // the conflict itself
    expect(rows.find((r) => r.id === 'goals-2_5')?.right?.familyConflict).toBe(false); // other family untouched
  });
});

describe('settledOutcomeKeys', () => {
  it('marks every outcome a 2-1 home win settles', () => {
    const keys = settledOutcomeKeys(2, 1);
    for (const k of ['HOME_WIN', 'HOME_OR_DRAW', 'HOME_OR_AWAY', 'OVER_2_5', 'UNDER_3_5', 'BTTS_YES']) {
      expect(keys.has(k)).toBe(true);
    }
    expect(keys.has('DRAW')).toBe(false);
    expect(keys.has('OVER_3_5')).toBe(false);
  });

  it('treats 0-0 as draw, under every line and no BTTS', () => {
    const keys = settledOutcomeKeys(0, 0);
    expect(keys.has('DRAW')).toBe(true);
    expect(keys.has('UNDER_0_5')).toBe(true);
    expect(keys.has('BTTS_NO')).toBe(true);
  });
});

describe('formatting', () => {
  it('writes Turkish percentages and points, "veri yok" when missing', () => {
    expect(pct(0.771)).toBe('%77');
    expect(pct(0.771, 1)).toBe('%77.1');
    expect(pct(null)).toBe('veri yok');
    expect(points(0.0474)).toBe('+4.7 puan');
    expect(points(-0.02)).toBe('−2.0 puan');
    expect(points(undefined)).toBe('veri yok');
  });

  it('describes the market line with what is actually available', () => {
    const rows = buildRailRows(MOCK_PREDICTION, { home: 'H', away: 'A' });
    expect(marketLine(rows[0].left!)).toBe('piyasa %50 · 2.00');
    expect(marketLine(rows[1].left!)).toBe('oran 1.30');
    const bare = { ...rows[0].left!, odds: null, marketProbability: null };
    expect(marketLine(bare)).toBe('oran yok');
  });

  it('translates selector pass reasons', () => {
    expect(describePassReason('model_market_conflict')).toMatch(/çelişiyor/);
    expect(describePassReason('insufficient_value')).toMatch(/değer yok/);
    expect(describePassReason(undefined)).toMatch(/Eşikleri/);
  });
});
