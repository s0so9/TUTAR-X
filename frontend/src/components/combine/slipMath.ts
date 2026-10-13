/**
 * Kombine arithmetic shared by the dashboard panel and the match-page drawer.
 *
 * Prices come ONLY from the items' real market odds (never confidence or fair
 * odds). The combined model probability multiplies the items' own model
 * probabilities and therefore assumes the selections are independent; the UI
 * says so next to the figure.
 */

import type { CombineItem } from '../../hooks/useCombine';
import { isAvailableNumber } from '../../utils/displayValue';
import { MANUAL_ODDS_LABEL, isManualUserSuppliedOdds } from '../../utils/pickMarket';

/** Product of all decimal odds; null when any item has no valid price (> 1). */
export function combinedOdds(items: CombineItem[]): number | null {
  if (items.length === 0) return null;
  let product = 1;
  for (const item of items) {
    if (!isAvailableNumber(item.marketOdds) || item.marketOdds <= 1) return null;
    product *= item.marketOdds;
  }
  return product;
}

/** Product of the items' model probabilities; null when any item lacks one. */
export function combinedModelProbability(items: CombineItem[]): number | null {
  if (items.length === 0) return null;
  let product = 1;
  for (const item of items) {
    const p = item.probability;
    if (!isAvailableNumber(p) || p < 0 || p > 1) return null;
    product *= p;
  }
  return product;
}

/** Provenance line for one item's price, or null when it has no price. */
export function itemOddsProvenance(item: CombineItem): { label: string; unverified: boolean } | null {
  if (!isAvailableNumber(item.marketOdds) || item.marketOdds <= 1) return null;
  if (isManualUserSuppliedOdds(item.oddsSource)) return { label: MANUAL_ODDS_LABEL, unverified: true };
  const source = typeof item.oddsSource === 'string' ? item.oddsSource.trim() : '';
  return source
    ? { label: `Oran kaynağı: ${source}`, unverified: false }
    : { label: 'Oran kaynağı bilgisi yok', unverified: true };
}

/**
 * Provenance of the combined price: unverified as soon as one price is
 * user-entered or has no known source.
 */
export function totalOddsProvenance(items: CombineItem[]): { label: string; unverified: boolean } | null {
  const lines = items.map(itemOddsProvenance);
  if (lines.length === 0 || lines.some((l) => l === null)) return null;
  if (items.some((i) => isManualUserSuppliedOdds(i.oddsSource))) {
    return { label: `${MANUAL_ODDS_LABEL} içeriyor`, unverified: true };
  }
  if (lines.some((l) => l?.unverified)) return { label: 'Kaynağı bilinmeyen oran içeriyor', unverified: true };
  return { label: 'Oranlar kaynağından', unverified: false };
}

/** Money amount for the optional payout line, e.g. 180 -> "180.00 TL". */
export function formatMoney(value: number): string {
  return `${value.toFixed(2)} TL`;
}
