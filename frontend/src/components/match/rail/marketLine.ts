import type { RailOutcome } from './railModel';
import { pct } from './railModel';

/** "piyasa %76 · 1.22", "oran 1.05" (no margin-free probability) or "oran yok". */
export function marketLine(outcome: RailOutcome): string {
  const odds = outcome.odds !== null ? outcome.odds.toFixed(2) : null;
  if (outcome.marketProbability !== null) {
    return `piyasa ${pct(outcome.marketProbability)}${odds ? ` · ${odds}` : ''}`;
  }
  return odds ? `oran ${odds}` : 'oran yok';
}
