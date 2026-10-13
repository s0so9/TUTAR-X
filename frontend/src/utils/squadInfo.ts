/**
 * Display helpers for squad availability (prediction.squad_info, source FotMob).
 *
 * These only format / translate values supplied by the backend; they never
 * create numbers. Missing values are shown as UNAVAILABLE_LABEL ("veri yok").
 */

import { UNAVAILABLE_LABEL, isAvailableNumber } from './displayValue';

/**
 * Format a EUR market value compactly, e.g.
 *   645063664 -> "€645.1M", 1250000000 -> "€1.25B", 850000 -> "€850K".
 * Returns "veri yok" for missing / non-finite / negative values.
 */
export function formatMarketValueEur(value: number | null | undefined): string {
  if (!isAvailableNumber(value) || value < 0) return UNAVAILABLE_LABEL;
  if (value >= 1e9) return `€${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `€${(value / 1e6).toFixed(1)}M`;
  if (value >= 1e3) return `€${Math.round(value / 1e3)}K`;
  return `€${Math.round(value)}`;
}

const ABSENCE_REASON_LABELS: Record<string, string> = {
  injury: 'Sakat',
  injured: 'Sakat',
  suspension: 'Cezalı',
  suspended: 'Cezalı',
};

/** Turkish label for an absence reason; unknown codes are shown as received. */
export function describeAbsenceReason(reason: string | null | undefined): string {
  if (typeof reason !== 'string' || reason.trim() === '') return UNAVAILABLE_LABEL;
  return ABSENCE_REASON_LABELS[reason.trim().toLowerCase()] ?? reason;
}

/** True when the provider marked the starting XI as a predicted (pre-kickoff) lineup. */
export function isPredictedLineup(lineupType: string | null | undefined): boolean {
  return typeof lineupType === 'string' && lineupType.trim().toLowerCase() === 'predicted';
}

const MONTHS_TR: Record<string, string> = {
  january: 'Ocak',
  february: 'Şubat',
  march: 'Mart',
  april: 'Nisan',
  may: 'Mayıs',
  june: 'Haziran',
  july: 'Temmuz',
  august: 'Ağustos',
  september: 'Eylül',
  october: 'Ekim',
  november: 'Kasım',
  december: 'Aralık',
};

const MONTH_PART_TR: Record<string, string> = {
  early: 'başı',
  mid: 'ortası',
  late: 'sonu',
};

const RETURN_PHRASES_TR: Record<string, string> = {
  'back in training': 'Antrenmanlara döndü',
  'day to day': 'Günlük takip',
  doubtful: 'Şüpheli',
  'a few days': 'Birkaç gün',
  'a few weeks': 'Birkaç hafta',
  'a few months': 'Birkaç ay',
  'about a week': 'Yaklaşık 1 hafta',
  'about a month': 'Yaklaşık 1 ay',
  'out for season': 'Sezonu kapattı',
  unknown: 'Bilinmiyor',
};

/**
 * Translate the provider's expected-return text to Turkish where the phrase is
 * known ("Late October 2026" -> "Ekim 2026 sonu", "Back in training" ->
 * "Antrenmanlara döndü"). Unknown phrases are returned exactly as received.
 */
export function describeExpectedReturn(text: string | null | undefined): string {
  if (typeof text !== 'string' || text.trim() === '') return UNAVAILABLE_LABEL;
  const raw = text.trim();
  const lower = raw.toLowerCase();

  const known = RETURN_PHRASES_TR[lower];
  if (known) return known;

  const monthMatch = /^(early|mid|late)\s+([a-z]+)\s+(\d{4})$/.exec(lower);
  if (monthMatch && MONTHS_TR[monthMatch[2]]) {
    return `${MONTHS_TR[monthMatch[2]]} ${monthMatch[3]} ${MONTH_PART_TR[monthMatch[1]]}`;
  }

  const rangeMatch = /^about\s+(\d+(?:-\d+)?)\s+(day|days|week|weeks|month|months)$/.exec(lower);
  if (rangeMatch) {
    const unit = rangeMatch[2].startsWith('day') ? 'gün' : rangeMatch[2].startsWith('week') ? 'hafta' : 'ay';
    return `Yaklaşık ${rangeMatch[1]} ${unit}`;
  }

  return raw;
}
