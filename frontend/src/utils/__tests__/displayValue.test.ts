/**
 * displayValue helper tests - missing data must render as "veri yok", never 0.
 */

import { describe, it, expect } from 'vitest';
import {
  UNAVAILABLE_LABEL,
  formatNumber,
  formatOdds,
  formatProbability,
  isAvailableNumber,
} from '../displayValue';

describe('displayValue', () => {
  it('uses the Turkish unavailable label', () => {
    expect(UNAVAILABLE_LABEL).toBe('veri yok');
  });

  it('formats probabilities exactly from the supplied value', () => {
    expect(formatProbability(0.6734)).toBe('%67.3');
    expect(formatProbability(0.879, 0)).toBe('%88');
    expect(formatProbability(0)).toBe('%0.0');
  });

  it('renders missing probabilities as "veri yok" instead of 0.0%', () => {
    expect(formatProbability(null)).toBe('veri yok');
    expect(formatProbability(undefined)).toBe('veri yok');
    expect(formatProbability(Number.NaN)).toBe('veri yok');
  });

  it('formats decimal odds and rejects missing / invalid prices', () => {
    expect(formatOdds(1.8)).toBe('1.80');
    expect(formatOdds(null)).toBe('veri yok');
    expect(formatOdds(undefined)).toBe('veri yok');
    expect(formatOdds(0)).toBe('veri yok');
    expect(formatOdds(1)).toBe('veri yok');
  });

  it('formats plain numbers and keeps real zeros', () => {
    expect(formatNumber(0)).toBe('0');
    expect(formatNumber(4)).toBe('4');
    expect(formatNumber(null)).toBe('veri yok');
    expect(isAvailableNumber(0)).toBe(true);
    expect(isAvailableNumber(null)).toBe(false);
  });
});
