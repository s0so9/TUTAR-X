/**
 * Display helpers for numeric values that may be missing.
 *
 * Project rule: missing data must be shown explicitly as unavailable,
 * never substituted with 0. These helpers return UNAVAILABLE_LABEL
 * ("veri yok") for null / undefined / non-finite values.
 */

export const UNAVAILABLE_LABEL = 'veri yok';

/** True when the value is a real, finite number. */
export function isAvailableNumber(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

/**
 * Format a 0-1 probability as a Turkish percentage string (sign before the
 * number), e.g. 0.6734 -> "%67.3". Same style as the match page rail.
 * Returns "veri yok" when the value is missing.
 */
export function formatProbability(
  value: number | null | undefined,
  fractionDigits = 1
): string {
  if (!isAvailableNumber(value)) return UNAVAILABLE_LABEL;
  return `%${(value * 100).toFixed(fractionDigits)}`;
}

/**
 * Format decimal odds, e.g. 1.8 -> "1.80".
 * Returns "veri yok" when the value is missing or not a valid decimal price (<= 1).
 */
export function formatOdds(value: number | null | undefined, fractionDigits = 2): string {
  if (!isAvailableNumber(value) || value <= 1) return UNAVAILABLE_LABEL;
  return value.toFixed(fractionDigits);
}

/** Format any number with fixed digits, or "veri yok" when missing. */
export function formatNumber(value: number | null | undefined, fractionDigits = 0): string {
  if (!isAvailableNumber(value)) return UNAVAILABLE_LABEL;
  return value.toFixed(fractionDigits);
}
