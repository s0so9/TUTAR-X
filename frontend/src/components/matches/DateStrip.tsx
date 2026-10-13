/**
 * DateStrip - a quiet row of day tabs (2 days back, today, 4 days ahead),
 * previous/next-day buttons and a native date input for any other day.
 * The selected day is underlined in the rubric.
 * Dates are exchanged as local YYYY-MM-DD strings (same format as the API filter).
 */

import { useMemo } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { formatDateForAPI } from '../../api/client';
import './matches.css';

export interface DateStripProps {
  /** Selected date as YYYY-MM-DD (local time). */
  selectedDate: string;
  onDateChange: (date: string) => void;
  /** Days shown before today (default 2). */
  daysBefore?: number;
  /** Days shown after today (default 4). */
  daysAfter?: number;
}

function parseLocalDate(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return Number.isNaN(date.getTime()) ? null : date;
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function relativeLabel(offset: number, date: Date): string {
  if (offset === 0) return 'Bugün';
  if (offset === -1) return 'Dün';
  if (offset === 1) return 'Yarın';
  return date.toLocaleDateString('tr-TR', { weekday: 'short' });
}

export function DateStrip({
  selectedDate,
  onDateChange,
  daysBefore = 2,
  daysAfter = 4,
}: DateStripProps) {
  const todayKey = formatDateForAPI(new Date());

  const days = useMemo(() => {
    const today = parseLocalDate(todayKey) ?? new Date();
    const result: { key: string; label: string; dayText: string; fullLabel: string }[] = [];
    for (let offset = -daysBefore; offset <= daysAfter; offset++) {
      const date = addDays(today, offset);
      result.push({
        key: formatDateForAPI(date),
        label: relativeLabel(offset, date),
        dayText: date.toLocaleDateString('tr-TR', { day: 'numeric', month: 'short' }),
        fullLabel: date.toLocaleDateString('tr-TR', {
          weekday: 'long',
          day: 'numeric',
          month: 'long',
          year: 'numeric',
        }),
      });
    }
    return result;
  }, [todayKey, daysBefore, daysAfter]);

  const shiftSelected = (delta: number) => {
    const current = parseLocalDate(selectedDate) ?? new Date();
    onDateChange(formatDateForAPI(addDays(current, delta)));
  };

  return (
    <div className="tx-date-strip">
      <button
        type="button"
        className="tx-date-strip__nav"
        onClick={() => shiftSelected(-1)}
        aria-label="Önceki gün"
        title="Önceki gün"
      >
        <ChevronLeft size={16} strokeWidth={1.5} aria-hidden="true" />
      </button>

      <div className="tx-date-strip__days" role="group" aria-label="Tarih seçimi">
        {days.map((day) => {
          const isSelected = day.key === selectedDate;
          return (
            <button
              key={day.key}
              type="button"
              className={`tx-date-strip__day${isSelected ? ' tx-date-strip__day--selected' : ''}${
                day.key === todayKey ? ' tx-date-strip__day--today' : ''
              }`}
              aria-pressed={isSelected}
              aria-label={day.fullLabel}
              onClick={() => onDateChange(day.key)}
            >
              <span className="tx-date-strip__label">{day.label}</span>
              <span className="tx-date-strip__date">{day.dayText}</span>
            </button>
          );
        })}
      </div>

      <button
        type="button"
        className="tx-date-strip__nav"
        onClick={() => shiftSelected(1)}
        aria-label="Sonraki gün"
        title="Sonraki gün"
      >
        <ChevronRight size={16} strokeWidth={1.5} aria-hidden="true" />
      </button>

      <label className="tx-date-strip__picker">
        <span className="sr-only">Başka bir tarih seç</span>
        <input
          type="date"
          className="tx-date-strip__input"
          value={selectedDate}
          onChange={(event) => {
            if (event.target.value) onDateChange(event.target.value);
          }}
        />
      </label>
    </div>
  );
}
