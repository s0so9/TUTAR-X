import { Plus, Minus } from 'lucide-react';
import type { MensionePickResponse } from '../../../api/types';
import type { RailOutcome } from './railModel';
import { describePassReason, pct, points } from './railModel';
import {
  describePickMarket,
  describeValueClassification,
  isManualUserSuppliedOdds,
  isModelMarketConflict,
  MANUAL_ODDS_LABEL,
  MODEL_MARKET_CONFLICT_TOOLTIP,
  VALUE_EVIDENCE_NOTE,
  valueClassificationTone,
} from '../../../utils/pickMarket';
import { formatOdds } from '../../../utils/displayValue';

/** Signed Turkish percentage with a true minus sign ("+%4.2", "−%5.5"), or "veri yok". */
function formatSignedPercent(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'veri yok';
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}%${Math.abs(value).toFixed(1)}`;
}

function oddsSourceLabel(source: string | null | undefined): string {
  if (!source) return 'Oran yok';
  if (isManualUserSuppliedOdds(source)) return MANUAL_ODDS_LABEL;
  return source;
}

function ValueEvidenceNote() {
  return <p className="margin-note__caveat">{VALUE_EVIDENCE_NOTE}</p>;
}

function ClassificationTag({ code, familyConflict = false }: { code: string | null | undefined; familyConflict?: boolean }) {
  if (!code) return <span className="margin-tag margin-tag--neutral">Oran yok</span>;
  const tone = valueClassificationTone(code);
  if (tone === 'value' && familyConflict) {
    return (
      <span
        className="margin-tag margin-tag--warning"
        title="Aynı pazar ailesinde model ile piyasa çelişiyor; bu sonuç da değer sayılmaz."
      >
        Çelişkili aile
      </span>
    );
  }
  return (
    <span
      className={`margin-tag margin-tag--${tone}`}
      title={isModelMarketConflict(code) ? MODEL_MARKET_CONFLICT_TOOLTIP : undefined}
    >
      {describeValueClassification(code)}
    </span>
  );
}

function Ledger({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="margin-ledger">
      {rows.map(([term, value]) => (
        <div className="margin-ledger__row" key={term}>
          <dt className="ledger-term">{term}</dt>
          <dd className="numeral">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

interface PickNoteProps {
  pick: MensionePickResponse | null | undefined;
  teams: { home: string; away: string };
  inCombine: boolean;
  onToggleCombine: () => void;
  /** Pick outcome settled after the final whistle: true landed, false missed, null open */
  landed: boolean | null;
  onFocusPick: () => void;
}

export function PickNote({ pick, teams, inCombine, onToggleCombine, landed, onFocusPick }: PickNoteProps) {
  if (!pick) {
    return (
      <section className="margin-note" aria-labelledby="pick-note-title">
        <h2 id="pick-note-title" className="margin-note__title">TUTAR X seçimi</h2>
        <p className="margin-note__body">Bu maç için seçim verisi yok.</p>
      </section>
    );
  }

  if (pick.pass_decision) {
    return (
      <section className="margin-note" aria-labelledby="pick-note-title">
        <h2 id="pick-note-title" className="margin-note__title">TUTAR X seçimi</h2>
        <p className="margin-note__verdict">Pas</p>
        <p className="margin-note__body">{describePassReason(pick.pass_reason)}</p>
      </section>
    );
  }

  const label = describePickMarket(pick.market, pick.selection, teams);
  const edge = typeof pick.edge === 'number' ? pick.edge : null;

  return (
    <section className="margin-note margin-note--pick" aria-labelledby="pick-note-title">
      <h2 id="pick-note-title" className="margin-note__title">TUTAR X seçimi</h2>
      <button type="button" className="margin-note__pick" onClick={onFocusPick}>
        <span className="margin-note__market apparatus">{label.marketName}</span>
        <span className="margin-note__outcome">{label.outcome}</span>
      </button>
      {landed !== null && (
        <p className={`margin-note__result margin-note__result--${landed ? 'won' : 'lost'}`}>
          {landed ? 'Tuttu' : 'Tutmadı'}
        </p>
      )}
      <Ledger
        rows={[
          ['Model', pct(pick.probability ?? null, 1)],
          ['Oran', formatOdds(pick.bookmaker_odds ?? null)],
          ['Fark', points(edge)],
          ['Güven', pct(pick.confidence ?? null)],
        ]}
      />
      <div className="margin-note__tags">
        <ClassificationTag code={pick.value_classification ?? null} />
      </div>
      {valueClassificationTone(pick.value_classification) === 'value' && <ValueEvidenceNote />}
      <p className="margin-note__source">Oran kaynağı: {oddsSourceLabel(pick.odds_source)}</p>
      <button
        type="button"
        className={`margin-action${inCombine ? ' margin-action--on' : ''}`}
        onClick={onToggleCombine}
        aria-pressed={inCombine}
      >
        {inCombine ? <Minus size={15} strokeWidth={1.5} aria-hidden="true" /> : <Plus size={15} strokeWidth={1.5} aria-hidden="true" />}
        {inCombine ? 'Kombineden çıkar' : 'Kombineye ekle'}
      </button>
    </section>
  );
}

interface OutcomeApparatusProps {
  outcome: RailOutcome;
  inCombine: boolean;
  onToggleCombine: () => void;
  onClose: () => void;
}

export function OutcomeApparatus({ outcome, inCombine, onToggleCombine, onClose }: OutcomeApparatusProps) {
  const gap =
    outcome.probability !== null && outcome.impliedProbability !== null
      ? outcome.probability - outcome.impliedProbability
      : null;
  return (
    <section className="margin-note margin-note--apparatus" aria-labelledby="apparatus-title" key={outcome.key}>
      <div className="margin-note__head">
        <h2 id="apparatus-title" className="margin-note__title">{outcome.marketName}</h2>
        <button type="button" className="margin-close" onClick={onClose} aria-label="Detayı kapat">
          Kapat
        </button>
      </div>
      <p className="margin-note__outcome">{outcome.outcomeName}</p>
      <Ledger
        rows={[
          ['Model', pct(outcome.probability, 1)],
          ['Piyasa (marjsız)', pct(outcome.marketProbability, 1)],
          ['Oran', formatOdds(outcome.odds)],
          ['Adil oran', formatOdds(outcome.fairOdds)],
          ['Fark (oran dahil)', points(gap)],
          ['Beklenen getiri', formatSignedPercent(outcome.expectedValuePercent)],
        ]}
      />
      <div className="margin-note__tags">
        <ClassificationTag code={outcome.valueClassification} familyConflict={outcome.familyConflict} />
      </div>
      {outcome.valueClassification &&
        !outcome.familyConflict &&
        valueClassificationTone(outcome.valueClassification) === 'value' && <ValueEvidenceNote />}
      <p className="margin-note__source">Oran kaynağı: {oddsSourceLabel(outcome.oddsSource)}</p>
      <button
        type="button"
        className={`margin-action${inCombine ? ' margin-action--on' : ''}`}
        onClick={onToggleCombine}
        aria-pressed={inCombine}
      >
        {inCombine ? <Minus size={15} strokeWidth={1.5} aria-hidden="true" /> : <Plus size={15} strokeWidth={1.5} aria-hidden="true" />}
        {inCombine ? 'Kombineden çıkar' : 'Kombineye ekle'}
      </button>
    </section>
  );
}
