/**
 * CombinePanel - kombine panel docked bottom-right on the dashboard.
 * Collapses to a one-line bar; the body (CombineSlip) is shared with the
 * match-page drawer so both show the same figures in the same format.
 * Uses ONLY real market odds - never confidence, fair odds, or fabricated values.
 */

import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import type { CombineItem } from '../../hooks/useCombine';
import { formatOdds } from '../../utils/displayValue';
import { CombineSlip } from './CombineSlip';
import { combinedOdds } from './slipMath';
import './CombinePanel.css';

interface CombinePanelProps {
  /** Combined selections */
  combineItems: CombineItem[];
  /** Remove item callback */
  onRemoveItem: (matchId: string) => void;
  /** Clear all callback */
  onClearAll: () => void;
}

function startsCollapsed(): boolean {
  // Phones start with the one-line bar so the list stays readable.
  return typeof window !== 'undefined' && window.matchMedia?.('(max-width: 768px)').matches === true;
}

export default function CombinePanel({ combineItems, onRemoveItem, onClearAll }: CombinePanelProps) {
  const [collapsed, setCollapsed] = useState<boolean>(startsCollapsed);

  if (combineItems.length === 0) {
    return null;
  }

  const totalOdds = combinedOdds(combineItems);

  return (
    <>
      {/* In-flow room so the docked panel never hides the last line of the page */}
      <div
        className={`combine-panel__spacer${collapsed ? ' combine-panel__spacer--collapsed' : ''}`}
        aria-hidden="true"
      />
      <aside
        className={`combine-panel${collapsed ? ' combine-panel--collapsed' : ''}`}
        aria-label="Kombine"
      >
        <button
          type="button"
          className="combine-panel__bar"
          onClick={() => setCollapsed((c) => !c)}
          aria-expanded={!collapsed}
          aria-controls="combine-panel-body"
        >
          <span className="combine-panel__title">Kombine</span>
          <span className="combine-panel__count">{combineItems.length} seçim</span>
          {collapsed && (
            <span className="combine-panel__bar-odds numeral">
              {totalOdds !== null ? `Oran ${formatOdds(totalOdds)}` : 'Oran hesaplanamıyor'}
            </span>
          )}
          <span className="combine-panel__chevron" aria-hidden="true">
            {collapsed ? <ChevronUp size={16} strokeWidth={1.5} /> : <ChevronDown size={16} strokeWidth={1.5} />}
          </span>
          <span className="sr-only">{collapsed ? 'Kombineyi aç' : 'Kombineyi küçült'}</span>
        </button>

        {!collapsed && (
          <div id="combine-panel-body" className="combine-panel__body">
            <CombineSlip items={combineItems} onRemove={onRemoveItem} onClear={onClearAll} idPrefix="combine-panel" />
          </div>
        )}
      </aside>
    </>
  );
}
