/**
 * CombineSlip — the body shared by the dashboard kombine panel and the
 * match-page kombine drawer: selections, the model's combined probability,
 * the combined price with its provenance, and an optional amount whose
 * payout is shown as small secondary text.
 *
 * Prices use ONLY the items' market odds; confidence never enters any figure.
 */

import { useState } from 'react';
import { TriangleAlert, X } from 'lucide-react';
import type { CombineItem } from '../../hooks/useCombine';
import { UNAVAILABLE_LABEL, formatOdds, formatProbability } from '../../utils/displayValue';
import {
  combinedModelProbability,
  combinedOdds,
  formatMoney,
  itemOddsProvenance,
  totalOddsProvenance,
} from './slipMath';
import './CombineSlip.css';

interface CombineSlipProps {
  items: CombineItem[];
  onRemove: (matchId: string) => void;
  onClear: () => void;
  /** Distinguishes the amount input when both surfaces are on one page. */
  idPrefix: string;
}

export function CombineSlip({ items, onRemove, onClear, idPrefix }: CombineSlipProps) {
  const [amountText, setAmountText] = useState('');

  const totalOdds = combinedOdds(items);
  const modelProbability = combinedModelProbability(items);
  const totalProvenance = totalOddsProvenance(items);
  const missingOdds = items.some((item) => itemOddsProvenance(item) === null);

  const amount = Number.parseFloat(amountText.replace(',', '.'));
  const hasAmount = Number.isFinite(amount) && amount > 0;
  const payout = hasAmount && totalOdds !== null ? amount * totalOdds : null;

  return (
    <div className="tx-slip-body">
      <ul className="tx-slip-body__items">
        {items.map((item) => {
          const provenance = itemOddsProvenance(item);
          return (
            <li key={item.matchId} className="tx-slip-item">
              <div className="tx-slip-item__info">
                <span className="tx-slip-item__teams">
                  {item.homeTeam} – {item.awayTeam}
                </span>
                <span className="tx-slip-item__pick">
                  {item.marketName}
                  {item.outcome ? `: ${item.outcome}` : ''}
                </span>
                <span className="tx-slip-item__meta">
                  Model {formatProbability(item.probability ?? null)}
                  {provenance && (
                    <>
                      {' · '}
                      <span className={provenance.unverified ? 'tx-slip-item__unverified' : undefined}>
                        {provenance.label}
                      </span>
                    </>
                  )}
                </span>
              </div>
              <span className="tx-slip-item__odds numeral">
                {provenance ? formatOdds(item.marketOdds) : <span className="tx-slip-item__muted">Oran yok</span>}
              </span>
              <button
                type="button"
                className="tx-slip-item__remove"
                onClick={() => onRemove(item.matchId)}
                aria-label={`Kaldır: ${item.homeTeam} – ${item.awayTeam}`}
                title="Kaldır"
              >
                <X size={16} strokeWidth={1.75} aria-hidden="true" />
              </button>
            </li>
          );
        })}
      </ul>

      <div className="tx-slip-body__summary">
        <div className="tx-slip-body__row">
          <span className="tx-slip-body__label">Model olasılığı</span>
          <span className="tx-slip-body__figure numeral">
            {modelProbability !== null ? formatProbability(modelProbability) : UNAVAILABLE_LABEL}
          </span>
        </div>
        {items.length > 1 && modelProbability !== null && (
          <p className="tx-slip-body__note">Seçimler birbirinden bağımsız sayılarak çarpıldı.</p>
        )}

        <div className="tx-slip-body__row">
          <span className="tx-slip-body__label">Toplam oran</span>
          <span className="tx-slip-body__value numeral">
            {totalOdds !== null ? formatOdds(totalOdds) : <span className="tx-slip-item__muted">Hesaplanamıyor</span>}
          </span>
        </div>
        {totalProvenance && (
          <p className={`tx-slip-body__note${totalProvenance.unverified ? ' tx-slip-item__unverified' : ''}`}>
            {totalProvenance.label}
          </p>
        )}
        {missingOdds && (
          <p className="tx-slip-body__warning">
            <TriangleAlert size={14} strokeWidth={1.75} aria-hidden="true" />
            Bazı seçimlerin oranı yok
          </p>
        )}
      </div>

      {totalOdds !== null && (
        <div className="tx-slip-body__amount">
          <label htmlFor={`${idPrefix}-amount`} className="tx-slip-body__amount-label">
            Miktar (isteğe bağlı, TL)
          </label>
          <input
            id={`${idPrefix}-amount`}
            type="text"
            inputMode="decimal"
            className="tx-slip-body__amount-input numeral"
            value={amountText}
            placeholder="—"
            onChange={(e) => setAmountText(e.target.value.replace(/[^0-9.,]/g, ''))}
          />
          {payout !== null && (
            <p className="tx-slip-body__payout">
              Olası ödeme {formatMoney(payout)}
              {totalProvenance?.unverified ? ' · doğrulanmamış orana dayanır' : ''}
            </p>
          )}
        </div>
      )}

      <button type="button" className="tx-slip-body__clear" onClick={onClear}>
        Tümünü temizle
      </button>
    </div>
  );
}
