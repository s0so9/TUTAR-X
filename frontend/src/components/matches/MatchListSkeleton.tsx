/**
 * MatchListSkeleton - loading state for rail-line lists: a drawing hairline
 * plus static hairline placeholders in the shape of the lines to come.
 */

import './matches.css';

export interface MatchListSkeletonProps {
  /** Number of placeholder lines (default 6). */
  rows?: number;
  /** Screen-reader / visible status text. */
  label?: string;
}

export function MatchListSkeleton({ rows = 6, label = 'Maçlar yükleniyor' }: MatchListSkeletonProps) {
  return (
    <div className="tx-list-skeleton" role="status" aria-live="polite">
      <div className="tx-list-skeleton__status">
        <span className="loading-spinner" aria-hidden="true" />
        <span className="tx-list-skeleton__label">{label}</span>
      </div>
      <ul className="tx-list-skeleton__lines" aria-hidden="true">
        {Array.from({ length: rows }, (_, index) => (
          <li key={index} className="tx-list-skeleton__line">
            <span className="tx-list-skeleton__side tx-list-skeleton__side--home">
              <span className="tx-list-skeleton__bar" style={{ width: `${48 + ((index * 17) % 36)}%` }} />
            </span>
            <span />
            <span className="tx-list-skeleton__side">
              <span className="tx-list-skeleton__bar" style={{ width: `${44 + ((index * 23) % 40)}%` }} />
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
