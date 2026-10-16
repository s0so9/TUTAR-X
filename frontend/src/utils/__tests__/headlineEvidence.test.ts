/**
 * Past test rates of the headline rule: every constant must equal the research file it cites
 * (backend/data/research/sel_test.json), and the lines must only show a rate where one was measured.
 * Picks and kombine items below are TEST FIXTURES (made-up probabilities).
 */

import { describe, expect, it } from 'vitest';
import selTest from '../../../../backend/data/research/sel_test.json';
import feasibility from '../../../../backend/data/research/review_roadmap_feasibility.json';
import type { CombineItem } from '../../hooks/useCombine';
import type { PickCandidate } from '../headlinePicks';
import {
  BANKO_BAND_RATES,
  KOMBINE_TEST_RATES,
  ORANLI_TEST_RATE,
  SINGLE_OUTCOME_LINE,
  TESTED_COMPETITIONS_SOURCE,
  TESTED_COMPETITION_IDS,
  UEFA_COMPETITION_IDS,
  UEFA_STRONG_BANKO_RATE,
  UEFA_TEST_MATCHES,
  UEFA_TEST_MATCHES_SOURCE,
  UNKNOWN_COMPETITION_LINE,
  UNTESTED_LINE,
  bandFor,
  bankoEvidenceLines,
  evidenceCompetitionId,
  isTestedCompetition,
  kombineTestLine,
  normaliseCompetitionId,
  oranliEvidenceLines,
  type ResearchKey,
} from '../headlineEvidence';

function at(path: ResearchKey): unknown {
  let node: unknown = selTest;
  for (const key of path) {
    expect(node, `missing ${path.join(' > ')}`).toBeTypeOf('object');
    node = (node as Record<string, unknown>)[key];
  }
  return node;
}

function pick(key: string, p: number, odds: number | null = null): PickCandidate {
  return {
    key,
    marketName: 'Mock pazar',
    outcome: key,
    probability: p,
    fairOdds: 1 / p,
    odds,
    oddsSource: null,
    bankoEligible: true,
    source: 'match',
  };
}

/** A kombine leg added from the Banko card of a tested league (Premier League 47) unless overridden. */
function leg(matchId: string, probability: number | null, over: Partial<CombineItem> = {}): CombineItem {
  return {
    matchId,
    marketName: 'Mock pazar',
    outcome: 'Mock',
    marketOdds: null,
    confidence: null,
    homeTeam: 'Mock Ev',
    awayTeam: 'Mock Dep',
    probability,
    oddsSource: null,
    marketKey: 'HOME_OR_DRAW',
    competitionId: '47',
    headlineSlot: 'banko',
    ...over,
  };
}

describe('constants equal backend/data/research/sel_test.json', () => {
  it('banko bands', () => {
    expect(BANKO_BAND_RATES).toHaveLength(Object.keys(at(['C_rules', 'banko_bands']) as object).length);
    for (const band of BANKO_BAND_RATES) {
      const row = at(band.source) as { hit: number; n: number };
      expect(band.hit).toBe(row.hit);
      expect(band.n).toBe(row.n);
      // the key names the band
      expect(band.source[2]).toBe(`${band.lo.toFixed(2)}-${band.hi.toFixed(2)}`);
    }
  });

  it('UEFA, Oranlı and kombine rates', () => {
    for (const rate of [UEFA_STRONG_BANKO_RATE, ORANLI_TEST_RATE]) {
      const row = at(rate.source) as { hit: number; n: number };
      expect(rate.hit).toBe(row.hit);
      expect(rate.n).toBe(row.n);
    }
    expect(UEFA_TEST_MATCHES).toBe(at(UEFA_TEST_MATCHES_SOURCE));
    for (const rate of Object.values(KOMBINE_TEST_RATES)) {
      const row = at(rate.source) as { all_hit_rate: number; days: number; model_expected: number };
      expect(rate.hit).toBe(row.all_hit_rate);
      expect(rate.days).toBe(row.days);
      expect(rate.expected).toBe(row.model_expected);
    }
  });

  it('the tested competitions are the 20 of the test split; the 13 tracked ones are a subset', () => {
    const tested = Object.keys(at(TESTED_COMPETITIONS_SOURCE) as object).sort();
    expect([...TESTED_COMPETITION_IDS].sort()).toEqual(tested);
    expect(tested).toHaveLength(20);
    expect(UEFA_COMPETITION_IDS.every((id) => tested.includes(id))).toBe(true);
    // review_roadmap_feasibility.json -> featured_ids = backend/app/config.py featured_competition_ids
    // (the backend test test_headline_evidence.py checks that equality)
    expect(feasibility.featured_ids).toHaveLength(13);
    expect(feasibility.featured_ids.every((id) => tested.includes(id))).toBe(true);
  });
});

describe('bands and competitions', () => {
  it.each([
    [0.7, 0.7],
    [0.7499, 0.7],
    [0.75, 0.75],
    [0.8499, 0.8],
    [0.85, 0.85],
    [0.8999, 0.85],
    [0.9, 0.9],
    [0.95, 0.9],
  ])('p %s falls in the band starting at %s', (p, lo) => {
    expect(bandFor(p)?.lo).toBe(lo);
  });

  it('no band outside the Banko slot', () => {
    expect(bandFor(0.6999)).toBeNull();
    expect(bandFor(0.951)).toBeNull();
    expect(bandFor(Number.NaN)).toBeNull();
  });

  it('reads FotMob ids with or without the prefix', () => {
    expect(normaliseCompetitionId('fotmob_47')).toBe('47');
    expect(normaliseCompetitionId(' ')).toBeNull();
    expect(isTestedCompetition('47')).toBe(true);
    expect(isTestedCompetition('fotmob_10216')).toBe(true);
    expect(isTestedCompetition('268')).toBe(false); // Brazil Série A: not in the test split
    expect(isTestedCompetition(null)).toBe(false);
  });

  it('which competition id the match page rates against', () => {
    // the live centre's parent league id first, then the frozen record's
    expect(evidenceCompetitionId({ centre: '42', record: '73', match: '943230', centrePending: false })).toBe('42');
    expect(evidenceCompetitionId({ centre: null, record: '73', match: '943230', centrePending: false })).toBe('73');
    // still looking it up: nothing claimed yet
    expect(evidenceCompetitionId({ centre: null, record: null, match: '47', centrePending: true })).toBeUndefined();
    // the match endpoint's own id only when it is a tested league id: a Champions League stage id (943230),
    // a database UUID or "unknown" is no league id, so the competition is unknown (null), never "test edilmedi"
    expect(evidenceCompetitionId({ centre: null, record: null, match: '47', centrePending: false })).toBe('47');
    expect(evidenceCompetitionId({ centre: null, record: null, match: '943230', centrePending: false })).toBeNull();
    expect(
      evidenceCompetitionId({ centre: null, record: null, match: '1db4c075-92ec-43d2-b153-7597e7a620ca', centrePending: false }),
    ).toBeNull();
    expect(evidenceCompetitionId({ centre: null, record: null, match: 'unknown', centrePending: false })).toBeNull();
    expect(evidenceCompetitionId({ centre: null, record: null, match: null, centrePending: false })).toBeNull();
  });
});

describe('Banko evidence lines', () => {
  it('a tested league shows the band rate with its n', () => {
    expect(bankoEvidenceLines(pick('HOME_OR_DRAW', 0.87), 'banko', '47')).toEqual([
      'Geçmiş testte bu güçteki seçimler %88 tuttu (model %85–90, n 329).',
    ]);
    expect(bankoEvidenceLines(pick('OVER_1_5', 0.93), 'cok_guclu', '71')).toEqual([
      'Geçmiş testte bu güçteki seçimler %93 tuttu (model %90–95, n 161).',
    ]);
    expect(bankoEvidenceLines(pick('OVER_1_5', 0.77), 'guclu', '87')).toEqual([
      'Geçmiş testte bu güçteki seçimler %79 tuttu (model %75–80, n 1.669).',
    ]);
  });

  it('UEFA adds the smaller sample', () => {
    expect(bankoEvidenceLines(pick('HOME_OR_DRAW', 0.87), 'banko', '42')).toEqual([
      'Geçmiş testte bu güçteki seçimler %88 tuttu (model %85–90, n 329).',
      'Avrupa kupalarında örneklem küçük: %85 ve üstü seçimler %86 tuttu (n 35).',
    ]);
    expect(bankoEvidenceLines(pick('DRAW_OR_AWAY', 0.72), 'guclu', '10216')[1]).toBe(
      'Avrupa kupalarında test örneklemi küçük (171 maç).',
    );
  });

  it('no rate outside the tested competitions or for a single 1X2 outcome', () => {
    expect(bankoEvidenceLines(pick('HOME_OR_DRAW', 0.87), 'banko', '268')).toEqual([UNTESTED_LINE]);
    expect(bankoEvidenceLines(pick('HOME_WIN', 0.87), 'banko', '47')).toEqual([SINGLE_OUTCOME_LINE]);
    expect(bankoEvidenceLines(pick('AWAY_WIN', 0.9), 'cok_guclu', '268')).toEqual([UNTESTED_LINE, SINGLE_OUTCOME_LINE]);
    expect(bankoEvidenceLines(pick('DRAW', 0.71), 'guclu', '42')).toEqual([SINGLE_OUTCOME_LINE]);
    expect(bankoEvidenceLines(pick('HOME_OR_DRAW', 0.87), 'banko', null)).toEqual([UNKNOWN_COMPETITION_LINE]);
    expect(bankoEvidenceLines(null, null, '47')).toEqual([]);
  });
});

describe('Oranlı evidence line', () => {
  it('the fair-path rate in a tested league', () => {
    expect(oranliEvidenceLines(pick('OVER_2_5', 0.58), '47')).toEqual([
      'Bu kuraldaki seçimler geçmiş testte %61 tuttu (n 1.758).',
    ]);
  });

  it('no rate for a priced pick, an untested league or an unknown one', () => {
    expect(oranliEvidenceLines(pick('OVER_2_5', 0.58, 1.9), '47')).toEqual([
      'Gerçek oranlı seçimler için geçmiş test oranı yok.',
    ]);
    expect(oranliEvidenceLines(pick('OVER_2_5', 0.58), '268')).toEqual([UNTESTED_LINE]);
    expect(oranliEvidenceLines(pick('OVER_2_5', 0.58), undefined)).toEqual([UNKNOWN_COMPETITION_LINE]);
    expect(oranliEvidenceLines(null, '47')).toEqual([]);
  });
});

describe('kombine past-test line', () => {
  it.each([
    [2, '%79', 90, ''],
    // 3-5 legs landed above the model's expectation over few days (roadmap B4): said so
    [3, '%75', 63, ' Bu oran modelin beklentisinin (%70) üstünde ve az güne dayanıyor; tesadüf olabilir.'],
    [4, '%70', 55, ' Bu oran modelin beklentisinin (%62) üstünde ve az güne dayanıyor; tesadüf olabilir.'],
    [5, '%66', 40, ' Bu oran modelin beklentisinin (%55) üstünde ve az güne dayanıyor; tesadüf olabilir.'],
  ])('%s legs of 85-95 %% Banko picks', (k, rate, days, caveat) => {
    const items = Array.from({ length: k }, (_, i) => leg(`m${i}`, 0.86 + i * 0.02));
    expect(kombineTestLine(items)).toBe(
      `Geçmiş test: aynı gün oynanan ${k} maçlık %85+ kuponlar ${rate} oranında tuttu (${days} gün).${caveat}`,
    );
  });

  it('nothing for single 1X2 outcomes, untested competitions or picks that are not a Banko', () => {
    // the measured coupons are Banko slot picks of the 20 test competitions (E_kombine.R1_banko85)
    expect(kombineTestLine([leg('a', 0.9, { marketKey: 'HOME_WIN' }), leg('b', 0.88)])).toBeNull();
    expect(kombineTestLine([leg('a', 0.9, { marketKey: 'AWAY_WIN' }), leg('b', 0.86, { marketKey: 'HOME_WIN' })])).toBeNull();
    expect(kombineTestLine([leg('a', 0.88, { competitionId: '268' }), leg('b', 0.88)])).toBeNull();
    expect(kombineTestLine([leg('a', 0.88, { competitionId: null }), leg('b', 0.88)])).toBeNull();
    expect(kombineTestLine([leg('a', 0.88, { headlineSlot: 'oranli' }), leg('b', 0.88)])).toBeNull();
    expect(kombineTestLine([leg('a', 0.88, { headlineSlot: null }), leg('b', 0.88)])).toBeNull();
    // an item stored before these fields existed (no market key, no competition, no slot)
    const bare: CombineItem = { ...leg('a', 0.88) };
    delete bare.marketKey;
    delete bare.competitionId;
    delete bare.headlineSlot;
    expect(kombineTestLine([bare, leg('b', 0.88)])).toBeNull();
    // tested competition with the FotMob prefix still counts
    expect(kombineTestLine([leg('a', 0.88, { competitionId: 'fotmob_42' }), leg('b', 0.88)])).not.toBeNull();
  });

  it('nothing for 1 or 6 legs, a weaker leg, a leg above 95 % or a missing probability', () => {
    expect(kombineTestLine([leg('a', 0.9)])).toBeNull();
    expect(kombineTestLine(Array.from({ length: 6 }, (_, i) => leg(`m${i}`, 0.9)))).toBeNull();
    expect(kombineTestLine([leg('a', 0.9), leg('b', 0.8499)])).toBeNull();
    expect(kombineTestLine([leg('a', 0.9), leg('b', 0.96)])).toBeNull();
    expect(kombineTestLine([leg('a', 0.9), leg('b', null)])).toBeNull();
    expect(kombineTestLine([leg('a', 0.85), leg('b', 0.95)])).not.toBeNull(); // bounds included
  });
});
