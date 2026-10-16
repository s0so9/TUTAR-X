import { Fragment } from 'react';
import { Check } from 'lucide-react';
import type { RailOutcome, RailRow, RailSlot } from './railModel';
import { isModelMarketConflict, valueClassificationTone, MODEL_MARKET_CONFLICT_TOOLTIP } from '../../../utils/pickMarket';
import { pct } from './railModel';
import { marketLine } from './marketLine';

interface MarketRailProps {
  rows: RailRow[];
  selectedKey: string | null;
  pickKey: string | null;
  /** Outcome keys that came true (finished matches); null before the result */
  settled: Set<string> | null;
  onSelect: (outcome: RailOutcome) => void;
}

const SLOT_ORDER: RailSlot[] = ['left', 'centre', 'right'];

const FAMILY_CONFLICT_TOOLTIP =
  'Aynı pazar ailesinde model ile piyasa çelişiyor; bu sonuç da değer sayılmaz.';

function OutcomeMarks({ outcome, isPick, isSettled }: { outcome: RailOutcome; isPick: boolean; isSettled: boolean }) {
  const tone = valueClassificationTone(outcome.valueClassification);
  return (
    <span className="rail-cell__marks">
      {isPick && <span className="rail-mark rail-mark--pick">Seçim</span>}
      {tone === 'value' && !outcome.familyConflict && <span className="rail-mark rail-mark--value">Değer</span>}
      {tone === 'value' && outcome.familyConflict && (
        <span className="rail-mark rail-mark--conflict" title={FAMILY_CONFLICT_TOOLTIP}>
          Çelişkili aile
        </span>
      )}
      {isModelMarketConflict(outcome.valueClassification) && (
        <span className="rail-mark rail-mark--conflict" title={MODEL_MARKET_CONFLICT_TOOLTIP}>
          Çelişki
        </span>
      )}
      {isSettled && (
        <span className="rail-mark rail-mark--settled">
          <Check size={12} strokeWidth={2} aria-hidden="true" />
          Oldu
        </span>
      )}
    </span>
  );
}

function OutcomeCell({
  outcome,
  slot,
  selected,
  isPick,
  isSettled,
  onSelect,
}: {
  outcome: RailOutcome;
  slot: RailSlot;
  selected: boolean;
  isPick: boolean;
  isSettled: boolean;
  onSelect: (outcome: RailOutcome) => void;
}) {
  return (
    <button
      type="button"
      className={`rail-cell rail-cell--${slot}${selected ? ' rail-cell--selected' : ''}${isPick ? ' rail-cell--pick' : ''}`}
      aria-pressed={selected}
      aria-label={`${outcome.marketName}: ${outcome.outcomeName}, model ${pct(outcome.probability)}`}
      onClick={() => onSelect(outcome)}
    >
      <span className="rail-cell__short">{outcome.short}</span>
      <span className="rail-cell__model numeral">{pct(outcome.probability)}</span>
      {hasMarketData(outcome) && (
        <span className="rail-cell__market numeral">{keepMarketLineTogether(marketLine(outcome))}</span>
      )}
      <OutcomeMarks outcome={outcome} isPick={isPick} isSettled={isSettled} />
    </button>
  );
}

/** Market line only when there is a price or a market probability ("oran yok" everywhere is noise). */
function hasMarketData(outcome: RailOutcome): boolean {
  return outcome.odds !== null || outcome.marketProbability !== null;
}

/**
 * Narrow cells may wrap the market line; it may break only between the
 * probability and the price ("piyasa %4" / "· 26.00"), never inside either.
 */
function keepMarketLineTogether(line: string): string {
  const nbsp = String.fromCharCode(0xa0);
  return line.replace(/^(piyasa|oran) /, `$1${nbsp}`).replace(' · ', ` ·${nbsp}`);
}

/** Two stacked bands: the model's split on top, the market's below, meeting at the rail. */
function RowBands({ row }: { row: RailRow }) {
  const cells = SLOT_ORDER.map((slot) => row[slot]).filter((o): o is RailOutcome => o !== null);
  const model = cells.map((o) => o.probability ?? 0);
  const market = cells.map((o) => o.marketProbability);
  const modelTotal = model.reduce((a, b) => a + b, 0) || 1;
  const hasMarket = market.every((p) => p !== null);
  const marketTotal = hasMarket ? (market as number[]).reduce((a, b) => a + b, 0) || 1 : 1;
  const slots = SLOT_ORDER.filter((slot) => row[slot] !== null);

  return (
    <div className="rail-bands" aria-hidden="true">
      <div className="rail-band rail-band--model">
        {slots.map((slot, i) => (
          <span key={slot} className={`rail-band__seg rail-band__seg--${slot}`} style={{ flexGrow: model[i] / modelTotal }} />
        ))}
      </div>
      <div className={`rail-band rail-band--market${hasMarket ? '' : ' rail-band--empty'}`}>
        {hasMarket &&
          slots.map((slot, i) => (
            <span
              key={slot}
              className={`rail-band__seg rail-band__seg--${slot}`}
              style={{ flexGrow: (market[i] as number) / marketTotal }}
            />
          ))}
      </div>
    </div>
  );
}

export function MarketRail({ rows, selectedKey, pickKey, settled, onSelect }: MarketRailProps) {
  return (
    <div className="market-rail" role="group" aria-label="Pazarlar: model ve piyasa olasılıkları">
      {rows.map((row) => (
        <Fragment key={row.id}>
        {row.section && <p className="rail-section">{row.section}</p>}
        <div className="rail-row">
          {SLOT_ORDER.map((slot) => {
            const outcome = row[slot];
            if (slot === 'centre') {
              return (
                <div className="rail-key" key={slot}>
                  <span className="rail-key__label apparatus">{row.key}</span>
                  {row.keySub && <span className="rail-key__sub numeral">{row.keySub}</span>}
                  {outcome && (
                    <OutcomeCell
                      outcome={outcome}
                      slot="centre"
                      selected={selectedKey === outcome.key}
                      isPick={pickKey === outcome.key}
                      isSettled={settled?.has(outcome.key) ?? false}
                      onSelect={onSelect}
                    />
                  )}
                </div>
              );
            }
            return outcome ? (
              <OutcomeCell
                key={slot}
                outcome={outcome}
                slot={slot}
                selected={selectedKey === outcome.key}
                isPick={pickKey === outcome.key}
                isSettled={settled?.has(outcome.key) ?? false}
                onSelect={onSelect}
              />
            ) : (
              <div key={slot} className={`rail-cell rail-cell--${slot} rail-cell--empty`} />
            );
          })}
          <RowBands row={row} />
        </div>
        </Fragment>
      ))}
    </div>
  );
}
