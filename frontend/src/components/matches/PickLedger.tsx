/**
 * PickLedger - the model's picks as a dense ledger in the rail grammar.
 *
 * Each entry is one line: home | key | away, then the pick (outcome + market),
 * the model probability with its fair odds, the bookmaker price with its
 * provenance, and the value assessment with the confidence score. Every number
 * is shown as the engine/backend supplied it; missing values read "veri yok".
 * User-entered odds always carry "Oran doğrulanmadı"; a model–market conflict
 * is an ochre warning, never value.
 */

import { Link } from 'react-router-dom';
import { Check, Plus, TriangleAlert } from 'lucide-react';
import type { MatchStatus } from '../../api/types';
import { UNAVAILABLE_LABEL, formatOdds, formatProbability } from '../../utils/displayValue';
import {
  MODEL_MARKET_CONFLICT_TOOLTIP,
  describeValueClassification,
  valueClassificationTone,
} from '../../utils/pickMarket';
import { MatchKey } from './MatchKey';
import {
  MATCH_STATUS_TEXT,
  describeOddsProvenance,
  formatKickoffTime,
  matchLineTone,
} from './lineFormat';
import { hasDisplayableScore } from './types';
import './matches.css';

export interface PickLedgerEntry {
  matchId: string;
  homeTeam: string;
  awayTeam: string;
  /** ISO8601 UTC kickoff time */
  scheduledAt: string;
  status: MatchStatus;
  homeScore: number | null;
  awayScore: number | null;
  minute?: number | null;
  /** Turkish market label, e.g. "Alt/Üst 2.5 Gol" */
  marketName: string;
  /** Turkish outcome label, e.g. "Üst 2.5" */
  outcome: string;
  /** Model probability of the pick (0-1) */
  probability: number | null;
  fairOdds: number | null;
  /** Bookmaker price for the pick */
  odds: number | null;
  oddsSource: string | null;
  valueClassification: string | null;
  /** Engine confidence score (0-1) */
  confidence: number | null;
}

export interface PickLedgerProps {
  entries: PickLedgerEntry[];
  isInCombine: (matchId: string) => boolean;
  onToggleCombine: (entry: PickLedgerEntry) => void;
}

interface Assessment {
  tone: 'value' | 'warning' | 'negative' | 'neutral' | 'missing';
  label: string;
  title?: string;
}

function assess(code: string | null): Assessment {
  if (!code) return { tone: 'missing', label: UNAVAILABLE_LABEL };
  const tone = valueClassificationTone(code);
  return {
    tone,
    label: describeValueClassification(code),
    title: tone === 'warning' ? MODEL_MARKET_CONFLICT_TOOLTIP : undefined,
  };
}

function buildLabel(entry: PickLedgerEntry, kickoff: string | null, assessment: Assessment): string {
  const status = MATCH_STATUS_TEXT[entry.status] ?? MATCH_STATUS_TEXT.SCHEDULED;
  const provenance = describeOddsProvenance(entry.odds, entry.oddsSource);
  const when = hasDisplayableScore(entry)
    ? `skor ${entry.homeScore} - ${entry.awayScore}`
    : kickoff
      ? `başlama saati ${kickoff}`
      : 'başlama saati bilinmiyor';
  const parts = [
    `${entry.homeTeam} - ${entry.awayTeam}, ${when}, ${status.aria}.`,
    `Seçim: ${entry.marketName}, ${entry.outcome}.`,
    `Model olasılığı ${formatProbability(entry.probability)}, adil oran ${formatOdds(entry.fairOdds)}.`,
    `Oran ${formatOdds(entry.odds)}${provenance ? `, ${provenance.full}` : ''}.`,
    `Değerlendirme: ${assessment.label}${assessment.title ? ` (${assessment.title})` : ''}.`,
    `Güven ${formatProbability(entry.confidence, 0)}.`,
    'Maç detayına git',
  ];
  return parts.join(' ');
}

function PickLedgerRow({
  entry,
  inCombine,
  onToggleCombine,
}: {
  entry: PickLedgerEntry;
  inCombine: boolean;
  onToggleCombine: (entry: PickLedgerEntry) => void;
}) {
  const kickoff = formatKickoffTime(entry.scheduledAt);
  const assessment = assess(entry.valueClassification);
  const provenance = describeOddsProvenance(entry.odds, entry.oddsSource);
  const pairLabel = `${entry.homeTeam} - ${entry.awayTeam}, ${entry.outcome}`;
  const tone = matchLineTone(entry.status);

  return (
    <li className={`tx-ledger__row tx-line--${tone}`}>
      <Link
        to={`/matches/${entry.matchId}`}
        className="tx-line__link tx-ledger__link"
        aria-label={buildLabel(entry, kickoff, assessment)}
      >
        <span className="tx-line__side tx-line__side--home">
          <span className="tx-line__name" title={entry.homeTeam}>
            {entry.homeTeam}
          </span>
        </span>
        <span className="tx-line__key">
          <MatchKey
            status={entry.status}
            kickoff={kickoff}
            homeScore={entry.homeScore}
            awayScore={entry.awayScore}
            minute={entry.minute}
          />
        </span>
        <span className="tx-line__side tx-line__side--away">
          <span className="tx-line__name" title={entry.awayTeam}>
            {entry.awayTeam}
          </span>
        </span>

        <span className="tx-ledger__facts">
          <span className="tx-ledger__cell tx-ledger__cell--pick">
            <span className="tx-ledger__primary">{entry.outcome}</span>
            <span className="tx-ledger__secondary">{entry.marketName}</span>
          </span>

          <span className="tx-ledger__cell tx-ledger__cell--num">
            <span className="tx-ledger__primary">
              <span className="tx-ledger__inline-label">Model</span>
              <span className={entry.probability === null ? 'tx-ledger__missing' : undefined}>
                {formatProbability(entry.probability)}
              </span>
            </span>
            <span className="tx-ledger__secondary">Adil {formatOdds(entry.fairOdds)}</span>
          </span>

          <span className="tx-ledger__cell tx-ledger__cell--num">
            <span className="tx-ledger__primary">
              <span className="tx-ledger__inline-label">Oran</span>
              <span className={provenance ? undefined : 'tx-ledger__missing'}>{formatOdds(entry.odds)}</span>
            </span>
            {provenance && (
              <span
                className={`tx-ledger__secondary${provenance.unverified ? ' tx-ledger__secondary--unverified' : ''}`}
                title={provenance.full}
              >
                {provenance.compact}
              </span>
            )}
          </span>

          <span className={`tx-ledger__cell tx-ledger__cell--assess tx-ledger__cell--${assessment.tone}`}>
            <span className="tx-ledger__primary" title={assessment.title}>
              {assessment.tone === 'warning' && (
                <TriangleAlert size={16} strokeWidth={1.5} aria-hidden="true" className="tx-ledger__icon" />
              )}
              {assessment.label}
            </span>
            <span className="tx-ledger__secondary">Güven {formatProbability(entry.confidence, 0)}</span>
          </span>
        </span>
      </Link>

      <span className="tx-line__actions">
        <button
          type="button"
          className={`tx-ledger__combine${inCombine ? ' tx-ledger__combine--on' : ''}`}
          onClick={() => onToggleCombine(entry)}
          aria-pressed={inCombine}
          aria-label={inCombine ? `Kombineden çıkar: ${pairLabel}` : `Kombineye ekle: ${pairLabel}`}
          title={inCombine ? 'Kombineden çıkar' : 'Kombineye ekle'}
        >
          {inCombine ? (
            <Check size={16} strokeWidth={1.5} aria-hidden="true" />
          ) : (
            <Plus size={16} strokeWidth={1.5} aria-hidden="true" />
          )}
        </button>
      </span>
    </li>
  );
}

export function PickLedger({ entries, isInCombine, onToggleCombine }: PickLedgerProps) {
  return (
    <div className="tx-ledger">
      <div className="tx-ledger__heads" aria-hidden="true">
        <span className="tx-ledger__heads-grid">
          <span className="tx-ledger__head tx-ledger__head--home">Ev sahibi</span>
          <span className="tx-ledger__head tx-ledger__head--key">Saat</span>
          <span className="tx-ledger__head">Deplasman</span>
          <span className="tx-ledger__head">Seçim</span>
          <span className="tx-ledger__head tx-ledger__head--num">Model</span>
          <span className="tx-ledger__head tx-ledger__head--num">Oran</span>
          <span className="tx-ledger__head">Değerlendirme</span>
        </span>
        <span className="tx-ledger__head tx-ledger__head--action">Kombine</span>
      </div>
      <ul className="tx-ledger__list">
        {entries.map((entry) => (
          <PickLedgerRow
            key={entry.matchId}
            entry={entry}
            inCombine={isInCombine(entry.matchId)}
            onToggleCombine={onToggleCombine}
          />
        ))}
      </ul>
    </div>
  );
}
