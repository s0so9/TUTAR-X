/**
 * Banko / Oranlı selection. Candidates below are TEST FIXTURES (made-up probabilities).
 */

import { describe, it, expect } from 'vitest';
import {
  ODDS_MIN_P,
  RULE_VERSION,
  bankoTier,
  matchCandidates,
  propsCandidates,
  selectHeadlinePicks,
  type PickCandidate,
} from '../headlinePicks';
import { buildRailRows } from '../../components/match/rail/railModel';
import type { MatchPredictionResponse } from '../../api/types';
import fixtures from './headlinePicks.fixtures.json';
import type { PropsResponse } from '../../api/props';

function c(key: string, p: number, extra: Partial<PickCandidate> = {}): PickCandidate {
  return {
    key,
    marketName: `Mock ${key}`,
    outcome: key,
    probability: p,
    fairOdds: 1 / p,
    odds: null,
    oddsSource: null,
    bankoEligible: true,
    source: 'match',
    ...extra,
  };
}

describe('selectHeadlinePicks', () => {
  it('banko is the surest outcome between 70 % and 95 %', () => {
    const picks = selectHeadlinePicks([c('A', 0.97), c('B', 0.91), c('C', 0.8), c('D', 0.6)]);
    expect(picks.banko?.key).toBe('B');
  });

  it('never makes a non-eligible market banko', () => {
    const picks = selectHeadlinePicks([c('CARDS', 0.9, { bankoEligible: false }), c('B', 0.75)]);
    expect(picks.banko?.key).toBe('B');
  });

  it('no banko below 70 %', () => {
    expect(selectHeadlinePicks([c('A', 0.69), c('B', 0.5)]).banko).toBeNull();
  });

  it('oranlı is the most likely outcome paying a fair 1.60 or more', () => {
    const picks = selectHeadlinePicks([c('A', 0.9), c('B', 0.66), c('C', 0.6), c('D', 0.5)]);
    // (A..D are their own families here)
    // B pays 1.52 (too little); C pays 1.67
    expect(picks.oranli?.key).toBe('C');
  });

  it('with bookmaker odds, oranlı needs odds >= 1.60 and at least a fair price', () => {
    const picks = selectHeadlinePicks([
      c('A', 0.9),
      c('B', 0.7, { odds: 1.65 }), // 0.7 x 1.65 = 1.155 -> qualifies
      c('C', 0.62, { odds: 1.5 }), // pays too little
      c('D', 0.55),
    ]);
    expect(picks.oranli?.key).toBe('B');
  });

  it('no oranlı when nothing pays enough with a reasonable chance', () => {
    expect(selectHeadlinePicks([c('A', 0.9), c('B', 0.4)]).oranli).toBeNull();
  });
});

describe('headline_v2 tiers and the oranlı floor', () => {
  it('is rule version headline_v2 with the 0.55 oranlı floor', () => {
    expect(RULE_VERSION).toBe('headline_v2');
    expect(ODDS_MIN_P).toBe(0.55);
  });

  it.each([
    [0.7, 'guclu'],
    [0.8499, 'guclu'],
    [0.85, 'banko'],
    [0.8999, 'banko'],
    [0.9, 'cok_guclu'],
    [0.95, 'cok_guclu'],
    [0.6999, null],
    [0.951, null],
    [Number.NaN, null],
    [null, null],
  ] as const)('bankoTier(%s) = %s', (p, tier) => {
    expect(bankoTier(p)).toBe(tier);
  });

  it('puts the tier of the banko on the result, null without a banko', () => {
    expect(selectHeadlinePicks([c('A', 0.86)]).bankoTier).toBe('banko');
    expect(selectHeadlinePicks([c('A', 0.6)]).bankoTier).toBeNull();
  });

  it('a güçlü banko still blocks its own family for the oranlı', () => {
    const picks = selectHeadlinePicks([c('HOME_OR_DRAW', 0.72), c('HOME_WIN', 0.6), c('BTTS_YES', 0.56)]);
    expect(picks.bankoTier).toBe('guclu');
    expect(picks.oranli?.key).toBe('BTTS_YES');
  });
});

describe('oranlı vs banko family', () => {
  it('never pairs 1X with home win: oranlı comes from the goals family', () => {
    const picks = selectHeadlinePicks([
      c('HOME_OR_DRAW', 0.81),
      c('HOME_WIN', 0.59),
      c('OVER_2_5', 0.58),
      c('BTTS_YES', 0.56),
    ]);
    expect(picks.banko?.key).toBe('HOME_OR_DRAW');
    expect(picks.oranli?.key).toBe('OVER_2_5');
  });

  it('a goals banko gets a result-family oranlı', () => {
    const picks = selectHeadlinePicks([c('OVER_1_5', 0.83), c('BTTS_YES', 0.62), c('HOME_OR_DRAW', 0.6)]);
    expect(picks.banko?.key).toBe('OVER_1_5');
    expect(picks.oranli?.key).toBe('HOME_OR_DRAW');
  });
});

describe('propsCandidates', () => {
  it('turns every line into an over and an under candidate and keeps the banko flag', () => {
    const props = {
      markets: [
        { key: 'total_yellow_cards', label_tr: 'Toplam sarı kart', group: 'Kartlar', scope: 'total', expected: 4.1, banko_eligible: false,
          lines: [{ line: 3.5, over: 0.58, under: 0.42 }] },
      ],
    } as unknown as PropsResponse;
    const out = propsCandidates(props);
    expect(out.map((o) => o.outcome)).toEqual(['3.5 Üst', '3.5 Alt']);
    expect(out.every((o) => o.bankoEligible === false)).toBe(true);
  });
});

/**
 * Parity with the backend port (backend/app/prediction/headline_picks.py): both implementations are
 * tested against the same fixtures. The Python test is backend/tests/test_headline_picks.py.
 */
describe('shared fixtures (parity with backend/app/prediction/headline_picks.py)', () => {
  interface CandidateCase {
    name: string;
    candidates: { key: string; probability: number; odds?: number; bankoEligible?: boolean }[];
    expected: { banko: string | null; oranli: string | null; banko_tier: string | null };
  }
  interface ResponseCase {
    name: string;
    teams: { home: string; away: string };
    prediction: unknown;
    expected_candidate_keys: string[];
    expected: {
      banko: { key: string; outcome: string; market: string; odds: number | null } | null;
      oranli: { key: string; outcome: string; market: string; odds: number | null } | null;
      banko_tier: string | null;
    };
  }
  const shared = fixtures as unknown as { candidate_cases: CandidateCase[]; response_cases: ResponseCase[] };

  it.each(shared.candidate_cases.map((x) => [x.name, x] as const))('candidates: %s', (_name, spec) => {
    const picks = selectHeadlinePicks(
      spec.candidates.map((x) => c(x.key, x.probability, { odds: x.odds ?? null, bankoEligible: x.bankoEligible ?? true })),
    );
    expect(picks.banko?.key ?? null).toBe(spec.expected.banko);
    expect(picks.oranli?.key ?? null).toBe(spec.expected.oranli);
    expect(picks.bankoTier).toBe(spec.expected.banko_tier);
  });

  it.each(shared.response_cases.map((x) => [x.name, x] as const))('prediction response: %s', (_name, spec) => {
    const rows = buildRailRows(spec.prediction as MatchPredictionResponse, spec.teams);
    const candidates = matchCandidates(rows);
    expect(candidates.map((x) => x.key)).toEqual(spec.expected_candidate_keys);
    const picks = selectHeadlinePicks(candidates);
    expect(picks.bankoTier).toBe(spec.expected.banko_tier);
    for (const kind of ['banko', 'oranli'] as const) {
      const expected = spec.expected[kind];
      const actual = picks[kind];
      if (expected === null) {
        expect(actual).toBeNull();
        continue;
      }
      expect(actual?.key).toBe(expected.key);
      expect(actual?.outcome).toBe(expected.outcome);
      expect(actual?.marketName).toBe(expected.market);
      expect(actual?.odds ?? null).toBe(expected.odds);
    }
  });
});
