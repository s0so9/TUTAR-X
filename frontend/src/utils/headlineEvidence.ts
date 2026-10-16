/**
 * Past test rates of the headline rule (headline_v2) for the match page and the kombine.
 *
 * These are BACKTEST figures from the research, never live results and never a promise. Every number
 * is copied from backend/data/research/sel_test.json (test split 2026-02-01 .. 2026-10-12, 3,402
 * matches in 20 competitions; the Banko / Oranlı rules were frozen before the test split was opened,
 * docs/research/2026-10-15-accuracy-roadmap.md section 3 "Phase 1, package 1"). Each constant carries
 * the key path it was read from (`source`); src/utils/__tests__/headlineEvidence.test.ts reads the
 * file and fails when a value drifts. Rates are shown only where they were measured: tested
 * competitions, Banko slot picks that are not a single 1X2 outcome, Oranlı picks on the fair path.
 */

import type { CombineItem } from '../hooks/useCombine';
import type { BankoTier, PickCandidate } from './headlinePicks';
import { BANKO_MAX_P, TIER_BANKO_MIN_P } from './headlinePicks';

/** Key path inside backend/data/research/sel_test.json (keys may contain dots, hence an array). */
export type ResearchKey = readonly string[];

export interface TestRate {
  /** hit rate in [0, 1] as stored in the research file */
  hit: number;
  /** number of picks it was measured on */
  n: number;
  source: ResearchKey;
}

export interface BandRate extends TestRate {
  /** Banko slot probability band [lo, hi); the last band includes 0.95 */
  lo: number;
  hi: number;
}

/**
 * FotMob league ids of the 20 test competitions (17 leagues + Champions League 42, Europa League 73,
 * Conference League 10216): the keys of sel_test.json -> C_rules.per_comp_R1. The 13 competitions the
 * tracker follows (backend/app/config.py featured_competition_ids, also
 * review_roadmap_feasibility.json -> featured_ids) are a subset; both are checked by the test.
 */
export const TESTED_COMPETITION_IDS: readonly string[] = [
  '10216', '122', '135', '38', '40', '42', '46', '47', '48', '53',
  '54', '55', '57', '59', '61', '64', '69', '71', '73', '87',
];
export const TESTED_COMPETITIONS_SOURCE: ResearchKey = ['C_rules', 'per_comp_R1'];

/** UEFA club competitions of the test split (roadmap B1 "Scope": FotMob ids 42, 73, 10216). */
export const UEFA_COMPETITION_IDS: readonly string[] = ['42', '73', '10216'];

/** Banko slot hit rate per probability band (sel_test.json -> C_rules.banko_bands). */
export const BANKO_BAND_RATES: readonly BandRate[] = [
  // sel_test.json -> C_rules.banko_bands["0.70-0.75"]: hit 0.7544, n 456
  { lo: 0.7, hi: 0.75, hit: 0.7544, n: 456, source: ['C_rules', 'banko_bands', '0.70-0.75'] },
  // sel_test.json -> C_rules.banko_bands["0.75-0.80"]: hit 0.7855, n 1669
  { lo: 0.75, hi: 0.8, hit: 0.7855, n: 1669, source: ['C_rules', 'banko_bands', '0.75-0.80'] },
  // sel_test.json -> C_rules.banko_bands["0.80-0.85"]: hit 0.8513, n 787
  { lo: 0.8, hi: 0.85, hit: 0.8513, n: 787, source: ['C_rules', 'banko_bands', '0.80-0.85'] },
  // sel_test.json -> C_rules.banko_bands["0.85-0.90"]: hit 0.8845, n 329 (= tier "banko")
  { lo: 0.85, hi: 0.9, hit: 0.8845, n: 329, source: ['C_rules', 'banko_bands', '0.85-0.90'] },
  // sel_test.json -> C_rules.banko_bands["0.90-0.95"]: hit 0.9317, n 161 (= tier "cok_guclu", 0.95 included)
  { lo: 0.9, hi: 0.95, hit: 0.9317, n: 161, source: ['C_rules', 'banko_bands', '0.90-0.95'] },
];

/** UEFA Bankos with p >= 0.85 on test, a small sample (sel_test.json -> C_rules.euro.R1_banko85). */
// sel_test.json -> C_rules.euro.R1_banko85: hit 0.8571, n 35
export const UEFA_STRONG_BANKO_RATE: TestRate = { hit: 0.8571, n: 35, source: ['C_rules', 'euro', 'R1_banko85'] };

/** UEFA matches in the test split (sel_test.json -> test_rows_euro: 171). */
// sel_test.json -> test_rows_euro: 171
export const UEFA_TEST_MATCHES = 171;
export const UEFA_TEST_MATCHES_SOURCE: ResearchKey = ['test_rows_euro'];

/**
 * Oranlı of headline_v2 on test: p >= 0.55, family exclusion against the 0.70-0.95 Banko slot (the
 * "current" Banko of the research), fair-price path (sel_test.json -> C_rules.oranli_current.fair_min_p0.55).
 * The priced path (bookmaker odds) was not measured at p >= 0.55.
 */
// sel_test.json -> C_rules.oranli_current.fair_min_p0.55: hit 0.6064, n 1758
export const ORANLI_TEST_RATE: TestRate = {
  hit: 0.6064,
  n: 1758,
  source: ['C_rules', 'oranli_current', 'fair_min_p0.55'],
};

export interface KombineRate extends TestRate {
  /** days with at least k Bankos (p >= 0.85) on test; n = days here */
  days: number;
  /** the model's expected all-legs rate on those days (product of the leg probabilities): model_expected */
  expected: number;
}

/**
 * Same-day coupons of k Bankos with p >= 0.85 on test: share of the day's k-combinations in which every
 * leg landed, days weighted equally (sel_test.json -> E_kombine.R1_banko85.k2 .. k5, all_hit_rate / days /
 * model_expected). For 3-5 legs the landed rate is above the model's expectation over few, overlapping
 * days; the roadmap (B4) says to treat it as noisy, not as the expectation.
 */
export const KOMBINE_TEST_RATES: Readonly<Record<2 | 3 | 4 | 5, KombineRate>> = {
  // sel_test.json -> E_kombine.R1_banko85.k2: all_hit_rate 0.7887, days 90, model_expected 0.7918
  2: { hit: 0.7887, n: 90, days: 90, expected: 0.7918, source: ['E_kombine', 'R1_banko85', 'k2'] },
  // sel_test.json -> E_kombine.R1_banko85.k3: all_hit_rate 0.7542, days 63, model_expected 0.6985
  3: { hit: 0.7542, n: 63, days: 63, expected: 0.6985, source: ['E_kombine', 'R1_banko85', 'k3'] },
  // sel_test.json -> E_kombine.R1_banko85.k4: all_hit_rate 0.6979, days 55, model_expected 0.6209
  4: { hit: 0.6979, n: 55, days: 55, expected: 0.6209, source: ['E_kombine', 'R1_banko85', 'k4'] },
  // sel_test.json -> E_kombine.R1_banko85.k5: all_hit_rate 0.6582, days 40, model_expected 0.5494
  5: { hit: 0.6582, n: 40, days: 40, expected: 0.5494, source: ['E_kombine', 'R1_banko85', 'k5'] },
};

/** Single 1X2 outcomes: rare and noisy as a Banko on test (C_rules.by_type.R1_banko85.MS1: n 2). */
export const SINGLE_OUTCOME_KEYS: readonly string[] = ['HOME_WIN', 'DRAW', 'AWAY_WIN'];

// ------------------------------------------------------------------------------------------------ helpers

/** "%88" (whole percent, as everywhere on the match page). */
export function formatTestRate(hit: number): string {
  return `%${Math.round(hit * 100)}`;
}

/** "1.758" (Turkish thousands separator). */
export function formatCount(n: number): string {
  return n.toLocaleString('tr-TR');
}

function bandPercent(p: number): string {
  return `${Math.round(p * 100)}`;
}

/** FotMob league id of the match ("47"; a "fotmob_47" form is accepted), null when unknown. */
export function normaliseCompetitionId(id: string | null | undefined): string | null {
  if (typeof id !== 'string') return null;
  const trimmed = id.trim().replace(/^fotmob_/, '');
  return trimmed === '' ? null : trimmed;
}

export function isTestedCompetition(id: string | null | undefined): boolean {
  const cid = normaliseCompetitionId(id);
  return cid !== null && TESTED_COMPETITION_IDS.includes(cid);
}

export function isUefaCompetition(id: string | null | undefined): boolean {
  const cid = normaliseCompetitionId(id);
  return cid !== null && UEFA_COMPETITION_IDS.includes(cid);
}

/**
 * The FotMob league id the match page rates its picks against: the live centre's parent league id, then
 * the frozen record's; undefined while the live centre is still loading (nothing claimed yet). The match
 * endpoint's own competition_id is used only when it is one of the tested league ids: it can be a stage id
 * (943230 for a Champions League league-phase match), a database UUID or "unknown", none of which says the
 * competition was not tested. Otherwise null ("Yarışma bilinmiyor").
 */
export function evidenceCompetitionId({
  centre,
  record,
  match,
  centrePending,
}: {
  centre: string | null | undefined;
  record: string | null | undefined;
  match: string | null | undefined;
  centrePending: boolean;
}): string | null | undefined {
  const known = normaliseCompetitionId(centre) ?? normaliseCompetitionId(record);
  if (known !== null) return known;
  if (centrePending) return undefined;
  return isTestedCompetition(match) ? normaliseCompetitionId(match) : null;
}

/** The test band of a Banko slot probability; null outside 0.70-0.95. */
export function bandFor(p: number): BandRate | null {
  if (!Number.isFinite(p) || p > BANKO_MAX_P) return null;
  return BANKO_BAND_RATES.find((b, i) => p >= b.lo && (p < b.hi || i === BANKO_BAND_RATES.length - 1)) ?? null;
}

export const UNKNOWN_COMPETITION_LINE = 'Yarışma bilinmiyor: geçmiş test oranı gösterilmiyor.';
export const UNTESTED_LINE = 'Bu ligde test edilmedi.';
export const SINGLE_OUTCOME_LINE = 'Tek sonuç: daha riskli.';

/**
 * The lines under the Banko slot pick: its band's past test rate in the tested competitions, otherwise
 * why there is none. Never a rate for a single 1X2 outcome or outside the tested competitions.
 */
export function bankoEvidenceLines(
  pick: PickCandidate | null,
  tier: BankoTier | null,
  competitionId: string | null | undefined,
): string[] {
  if (!pick || !tier) return [];
  const single = SINGLE_OUTCOME_KEYS.includes(pick.key);
  if (normaliseCompetitionId(competitionId) === null) return [UNKNOWN_COMPETITION_LINE];
  if (!isTestedCompetition(competitionId)) return single ? [UNTESTED_LINE, SINGLE_OUTCOME_LINE] : [UNTESTED_LINE];
  if (single) return [SINGLE_OUTCOME_LINE];
  const band = bandFor(pick.probability);
  if (!band) return [];
  const lines = [
    `Geçmiş testte bu güçteki seçimler ${formatTestRate(band.hit)} tuttu (model %${bandPercent(band.lo)}–${bandPercent(
      band.hi,
    )}, n ${formatCount(band.n)}).`,
  ];
  if (isUefaCompetition(competitionId)) {
    lines.push(
      tier === 'guclu'
        ? `Avrupa kupalarında test örneklemi küçük (${formatCount(UEFA_TEST_MATCHES)} maç).`
        : `Avrupa kupalarında örneklem küçük: %${bandPercent(TIER_BANKO_MIN_P)} ve üstü seçimler ${formatTestRate(
            UEFA_STRONG_BANKO_RATE.hit,
          )} tuttu (n ${formatCount(UEFA_STRONG_BANKO_RATE.n)}).`,
    );
  }
  return lines;
}

/** The line under the Oranlı pick: the rule's past test rate where it was measured. */
export function oranliEvidenceLines(pick: PickCandidate | null, competitionId: string | null | undefined): string[] {
  if (!pick) return [];
  if (normaliseCompetitionId(competitionId) === null) return [UNKNOWN_COMPETITION_LINE];
  if (!isTestedCompetition(competitionId)) return [UNTESTED_LINE];
  if (pick.odds !== null) return ['Gerçek oranlı seçimler için geçmiş test oranı yok.'];
  return [
    `Bu kuraldaki seçimler geçmiş testte ${formatTestRate(ORANLI_TEST_RATE.hit)} tuttu (n ${formatCount(
      ORANLI_TEST_RATE.n,
    )}).`,
  ];
}

/**
 * Whether a kombine leg is what the research combined (E_kombine.R1_banko85): the Banko slot pick of a
 * tested competition, not a single 1X2 outcome, with a model probability between 0.85 and 0.95. Legs
 * stored before the market key / competition / slot were kept never qualify.
 */
function isMeasuredKombineLeg(item: CombineItem): boolean {
  const p = item.probability;
  return (
    item.headlineSlot === 'banko' &&
    typeof item.marketKey === 'string' &&
    !SINGLE_OUTCOME_KEYS.includes(item.marketKey) &&
    isTestedCompetition(item.competitionId) &&
    typeof p === 'number' &&
    p >= TIER_BANKO_MIN_P &&
    p <= BANKO_MAX_P
  );
}

/**
 * The kombine's past-test line: only for 2-5 legs that are all measured Banko legs (isMeasuredKombineLeg);
 * null otherwise. Where the landed rate was above the model's expectation (3-5 legs) it says so: few days,
 * may be chance.
 */
export function kombineTestLine(items: CombineItem[]): string | null {
  const k = items.length;
  if (k < 2 || k > 5) return null;
  if (!items.every(isMeasuredKombineLeg)) return null;
  const rate = KOMBINE_TEST_RATES[k as 2 | 3 | 4 | 5];
  const line = `Geçmiş test: aynı gün oynanan ${k} maçlık %${bandPercent(TIER_BANKO_MIN_P)}+ kuponlar ${formatTestRate(
    rate.hit,
  )} oranında tuttu (${formatCount(rate.days)} gün).`;
  if (rate.hit <= rate.expected) return line;
  return `${line} Bu oran modelin beklentisinin (${formatTestRate(
    rate.expected,
  )}) üstünde ve az güne dayanıyor; tesadüf olabilir.`;
}
