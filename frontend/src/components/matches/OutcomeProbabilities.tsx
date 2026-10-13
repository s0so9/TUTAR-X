/**
 * OutcomeProbabilities - compact model 1·X·2 column for a rail line.
 *
 * Shows whole-number percentages in the series colours (home ink, draw ash,
 * away slate); the full engine values are in the tooltip. A row whose
 * prediction is not loaded shows a quiet "–" (tooltip and screen-reader text
 * say it is not loaded yet); a prediction with a missing
 * outcome says "veri yok" - never a 0.
 */

import { formatProbability } from '../../utils/displayValue';
import { hasCompleteProbabilities } from './types';
import type { MatchProbabilities } from './types';
import { formatCompactPercent } from './lineFormat';
import './matches.css';

export interface OutcomeProbabilitiesProps {
  probabilities: MatchProbabilities | null | undefined;
}

export function OutcomeProbabilities({ probabilities }: OutcomeProbabilitiesProps) {
  if (!probabilities) {
    return (
      <span
        className="tx-probs tx-probs--note"
        title="Bu maçın tahmini henüz yüklenmedi; maç sayfasında hesaplanır."
      >
        <span aria-hidden="true">–</span>
        <span className="sr-only">Tahmin yüklenmedi</span>
      </span>
    );
  }

  if (!hasCompleteProbabilities(probabilities)) {
    return (
      <span className="tx-probs tx-probs--note" title="Bu değer için veri bulunmuyor">
        veri yok
      </span>
    );
  }

  const { home, draw, away } = probabilities;
  const max = Math.max(home, draw, away);
  const cell = (side: 'home' | 'draw' | 'away', value: number) => (
    <span className={`tx-probs__cell tx-probs__cell--${side}${value === max ? ' tx-probs__cell--lead' : ''}`}>
      {formatCompactPercent(value)}
    </span>
  );

  return (
    <span
      className="tx-probs"
      title={`Model: Ev ${formatProbability(home)} · Beraberlik ${formatProbability(draw)} · Deplasman ${formatProbability(away)}`}
    >
      {cell('home', home)}
      {cell('draw', draw)}
      {cell('away', away)}
    </span>
  );
}
