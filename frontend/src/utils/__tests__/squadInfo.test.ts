/**
 * squadInfo display helpers. Inputs are test fixtures, not real football data.
 */

import { describe, it, expect } from 'vitest';
import {
  describeAbsenceReason,
  describeExpectedReturn,
  formatMarketValueEur,
  isPredictedLineup,
} from '../squadInfo';

describe('formatMarketValueEur', () => {
  it('formats millions and billions with € and M/B', () => {
    expect(formatMarketValueEur(645063664)).toBe('€645.1M');
    expect(formatMarketValueEur(8024831)).toBe('€8.0M');
    expect(formatMarketValueEur(1250000000)).toBe('€1.25B');
  });

  it('formats small values with K or plain euros', () => {
    expect(formatMarketValueEur(311799)).toBe('€312K');
    expect(formatMarketValueEur(500)).toBe('€500');
  });

  it('returns "veri yok" for missing values, never €0', () => {
    expect(formatMarketValueEur(null)).toBe('veri yok');
    expect(formatMarketValueEur(undefined)).toBe('veri yok');
    expect(formatMarketValueEur(Number.NaN)).toBe('veri yok');
    expect(formatMarketValueEur(-1)).toBe('veri yok');
  });
});

describe('describeAbsenceReason', () => {
  it('translates injury and suspension', () => {
    expect(describeAbsenceReason('injury')).toBe('Sakat');
    expect(describeAbsenceReason('INJURY')).toBe('Sakat');
    expect(describeAbsenceReason('suspension')).toBe('Cezalı');
  });

  it('shows other reasons as received and missing as "veri yok"', () => {
    expect(describeAbsenceReason('international_duty')).toBe('international_duty');
    expect(describeAbsenceReason(null)).toBe('veri yok');
    expect(describeAbsenceReason('')).toBe('veri yok');
  });
});

describe('describeExpectedReturn', () => {
  it('translates "<Early|Mid|Late> <Month> <Year>"', () => {
    expect(describeExpectedReturn('Late October 2026')).toBe('Ekim 2026 sonu');
    expect(describeExpectedReturn('Early November 2026')).toBe('Kasım 2026 başı');
    expect(describeExpectedReturn('Mid May 2027')).toBe('Mayıs 2027 ortası');
  });

  it('translates known phrases', () => {
    expect(describeExpectedReturn('Back in training')).toBe('Antrenmanlara döndü');
    expect(describeExpectedReturn('Doubtful')).toBe('Şüpheli');
    expect(describeExpectedReturn('About 1-2 weeks')).toBe('Yaklaşık 1-2 hafta');
    expect(describeExpectedReturn('Out for season')).toBe('Sezonu kapattı');
  });

  it('keeps unknown phrases exactly as received and marks missing as "veri yok"', () => {
    expect(describeExpectedReturn('After the international break')).toBe('After the international break');
    expect(describeExpectedReturn(null)).toBe('veri yok');
  });
});

describe('isPredictedLineup', () => {
  it('is true only for "predicted"', () => {
    expect(isPredictedLineup('predicted')).toBe(true);
    expect(isPredictedLineup('standard')).toBe(false);
    expect(isPredictedLineup(null)).toBe(false);
  });
});
