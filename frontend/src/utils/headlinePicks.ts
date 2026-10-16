/**
 * The two headline picks of a match, rule "headline_v2" (owner, 2026-10-15; research:
 * docs/research/2026-10-15-accuracy-roadmap.md, Paket 1):
 *
 *  - Banko slot: the outcome the model is surest about, whatever it pays. Only
 *    outcomes between 70 % and 95 % qualify (above 95 % bookmakers barely
 *    price the market; below 70 % it is not a banko). Cards and total corners
 *    are never banko (audit of the props model). The slot carries a tier:
 *    "cok_guclu" p >= 0.90, "banko" 0.85 <= p < 0.90, "guclu" 0.70 <= p < 0.85
 *    (shown, but not called a banko).
 *  - Oranlı: an outcome that still pays well (bookmaker odds >= 1.60 when the
 *    odds are known and the model sees at least a fair price, otherwise a fair
 *    model price >= 1.60) with p >= 0.55 and the highest model probability among
 *    those, from a different market family than the Banko slot pick, whatever its
 *    tier (no "1X" + "home win" pair).
 *
 * Rule "headline_v1" (2026-10-14) was the same without tiers and with the Oranlı
 * floor p >= 0.45; its frozen records keep that rule_version.
 *
 * Candidates are the match markets of the rail (1X2, double chance, total
 * goals 1.5/2.5/3.5, both teams to score) and the cards/corners/shots lines.
 * Pure functions: every number comes from the API responses.
 *
 * KEEP IN SYNC with the backend port that freezes and settles these picks:
 * backend/app/prediction/headline_picks.py. Both are tested against the same fixtures
 * (src/utils/__tests__/headlinePicks.fixtures.json); change the rule in both places.
 */

import type { RailRow } from '../components/match/rail/railModel';
import type { PropsResponse } from '../api/props';

export const RULE_VERSION = 'headline_v2';
/** The rule before headline_v2; its frozen records stay viewable on the Sonuçlar page. */
export const PREVIOUS_RULE_VERSION = 'headline_v1';

// Banko slot bounds (unchanged since headline_v1).
export const BANKO_MIN_P = 0.7;
export const BANKO_MAX_P = 0.95;
// Tier floors. Test hit rates: backend/data/research/sel_test.json -> C_rules.banko_bands (see headlineEvidence.ts).
export const TIER_BANKO_MIN_P = 0.85;
export const TIER_COK_GUCLU_MIN_P = 0.9;
export const ODDS_MIN_PRICE = 1.6;
// Oranlı floor 0.45 -> 0.55: sel_test.json -> C_rules.oranli_current.fair_min_p0.55 (hit 0.6064, n 1758).
export const ODDS_MIN_P = 0.55;

/** Tier of the Banko slot pick, strongest first: cok_guclu >= 0.90, banko 0.85-0.90, guclu 0.70-0.85. */
export type BankoTier = 'cok_guclu' | 'banko' | 'guclu';
export const BANKO_TIERS: readonly BankoTier[] = ['cok_guclu', 'banko', 'guclu'];

export interface PickCandidate {
  key: string;
  marketName: string;
  outcome: string;
  probability: number;
  /** 1 / probability */
  fairOdds: number;
  /** Bookmaker price when known */
  odds: number | null;
  oddsSource: string | null;
  bankoEligible: boolean;
  source: 'match' | 'props';
}

export interface HeadlinePicks {
  banko: PickCandidate | null;
  oranli: PickCandidate | null;
  /** Tier of the Banko slot pick (bankoTier(banko.probability)); null without a banko. */
  bankoTier: BankoTier | null;
}

function valid(p: number | null | undefined): p is number {
  return typeof p === 'number' && Number.isFinite(p) && p > 0 && p < 1;
}

/**
 * Tier of a Banko slot probability (banko_tier() of headline_picks.py); null outside the slot
 * (0.70-0.95) or when p is not a number.
 */
export function bankoTier(p: number | null | undefined): BankoTier | null {
  if (typeof p !== 'number' || !Number.isFinite(p) || p < BANKO_MIN_P || p > BANKO_MAX_P) return null;
  if (p >= TIER_COK_GUCLU_MIN_P) return 'cok_guclu';
  if (p >= TIER_BANKO_MIN_P) return 'banko';
  return 'guclu';
}

export function matchCandidates(rows: RailRow[]): PickCandidate[] {
  const out: PickCandidate[] = [];
  for (const row of rows) {
    for (const o of [row.left, row.centre, row.right]) {
      if (!o || !valid(o.probability)) continue;
      out.push({
        key: o.key,
        marketName: o.marketName,
        outcome: o.outcomeName,
        probability: o.probability,
        fairOdds: 1 / o.probability,
        odds: typeof o.odds === 'number' && o.odds > 1 ? o.odds : null,
        oddsSource: o.oddsSource,
        bankoEligible: true,
        source: 'match',
      });
    }
  }
  return out;
}

export function propsCandidates(props: PropsResponse | null | undefined): PickCandidate[] {
  if (!props) return [];
  const out: PickCandidate[] = [];
  for (const m of props.markets) {
    for (const l of m.lines) {
      for (const [side, p] of [
        ['Üst', l.over],
        ['Alt', l.under],
      ] as const) {
        if (!valid(p)) continue;
        out.push({
          key: `${m.key}:${m.scope}:${l.line}:${side}`,
          marketName: m.label_tr,
          outcome: `${l.line} ${side}`,
          probability: p,
          fairOdds: 1 / p,
          odds: null,
          oddsSource: null,
          bankoEligible: m.banko_eligible !== false,
          source: 'props',
        });
      }
    }
  }
  return out;
}

/**
 * Market family: match result + double chance ("result"), goal lines and both teams
 * to score ("goals"), anything else by its own key. Oranlı never comes from the
 * banko's family — "1X" and "home win" would be the same bet twice.
 */
export function pickFamily(key: string): string {
  if (/^(HOME_WIN|DRAW|AWAY_WIN|HOME_OR_DRAW|HOME_OR_AWAY|DRAW_OR_AWAY)$/.test(key)) return 'result';
  if (/^(OVER|UNDER)_\d+_\d+$/.test(key) || key.startsWith('BTTS_')) return 'goals';
  return key.split(':')[0];
}

export function selectHeadlinePicks(candidates: PickCandidate[]): HeadlinePicks {
  const byP = [...candidates].sort((a, b) => b.probability - a.probability);
  const banko =
    byP.find((c) => c.bankoEligible && c.probability >= BANKO_MIN_P && c.probability <= BANKO_MAX_P) ?? null;
  const bankoFamily = banko ? pickFamily(banko.key) : null;
  const otherFamily = byP.filter((c) => pickFamily(c.key) !== bankoFamily);

  const priced = otherFamily.filter(
    (c) => c.odds !== null && c.odds >= ODDS_MIN_PRICE && c.probability >= ODDS_MIN_P && c.probability * c.odds >= 1,
  );
  const fair = otherFamily.filter((c) => c.fairOdds >= ODDS_MIN_PRICE && c.probability >= ODDS_MIN_P);
  const oranli = (priced[0] ?? fair[0] ?? null) as PickCandidate | null;
  return {
    banko,
    oranli: oranli && banko && oranli.key === banko.key ? null : oranli,
    bankoTier: banko ? bankoTier(banko.probability) : null,
  };
}
