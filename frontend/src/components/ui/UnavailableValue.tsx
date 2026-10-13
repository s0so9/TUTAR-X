/**
 * UnavailableValue - renders a formatted value, or an explicit "veri yok"
 * marker when the value is missing (never a fake 0).
 */

import { UNAVAILABLE_LABEL } from '../../utils/displayValue';
import './ui.css';

export interface UnavailableValueProps {
  /** Already-formatted value; null/undefined/"veri yok" renders the unavailable marker. */
  value: string | null | undefined;
  className?: string;
}

export function UnavailableValue({ value, className }: UnavailableValueProps) {
  if (value === null || value === undefined || value === UNAVAILABLE_LABEL) {
    return (
      <span
        className={`tx-unavailable${className ? ` ${className}` : ''}`}
        title="Bu değer için veri bulunmuyor"
      >
        {UNAVAILABLE_LABEL}
      </span>
    );
  }
  return <span className={className}>{value}</span>;
}
