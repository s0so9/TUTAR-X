import { describe, expect, it } from 'vitest';
import type { CombineItem } from '../../../hooks/useCombine';
import {
  combinedModelProbability,
  combinedOdds,
  formatMoney,
  itemOddsProvenance,
  totalOddsProvenance,
} from '../slipMath';

// Development fixture values only (not real football data).
function item(overrides: Partial<CombineItem>): CombineItem {
  return {
    matchId: 'dev_match_1',
    marketName: 'Karşılıklı Gol',
    outcome: 'KG Var',
    marketOdds: 1.8,
    confidence: null,
    homeTeam: 'Dev Ev',
    awayTeam: 'Dev Deplasman',
    probability: 0.5,
    oddsSource: 'manual_user_supplied',
    ...overrides,
  };
}

describe('kombine slip math', () => {
  it('multiplies market odds and returns null when one price is missing', () => {
    expect(combinedOdds([item({}), item({ matchId: 'dev_2', marketOdds: 2 })])).toBeCloseTo(3.6);
    expect(combinedOdds([item({}), item({ matchId: 'dev_2', marketOdds: null })])).toBeNull();
    expect(combinedOdds([])).toBeNull();
  });

  it('multiplies model probabilities and never substitutes a missing one', () => {
    expect(combinedModelProbability([item({}), item({ matchId: 'dev_2', probability: 0.4 })])).toBeCloseTo(0.2);
    expect(combinedModelProbability([item({}), item({ matchId: 'dev_2', probability: null })])).toBeNull();
  });

  it('labels user-entered odds as unverified on the item and on the total', () => {
    expect(itemOddsProvenance(item({}))).toEqual({
      label: 'Kullanıcı girişli oran (doğrulanmadı)',
      unverified: true,
    });
    expect(totalOddsProvenance([item({}), item({ matchId: 'dev_2', oddsSource: 'bookmaker_x' })])?.unverified).toBe(true);
    expect(totalOddsProvenance([item({ oddsSource: 'bookmaker_x' })])).toEqual({
      label: 'Oranlar kaynağından',
      unverified: false,
    });
    expect(itemOddsProvenance(item({ oddsSource: null }))?.unverified).toBe(true);
    expect(itemOddsProvenance(item({ marketOdds: null }))).toBeNull();
  });

  it('formats money with two decimals', () => {
    expect(formatMoney(180)).toBe('180.00 TL');
  });
});
