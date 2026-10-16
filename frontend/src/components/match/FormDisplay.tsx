/**
 * FormDisplay Component
 * 
 * Displays recent form as W/D/L indicators for last 5 matches.
 * Shows empty state if no form data available.
 */

import type { TeamFormResponse } from '../../api/types'
import { UnavailableValue } from '../ui'
import { formatNumber } from '../../utils/displayValue'
import './FormDisplay.css'

export type FormResult = 'W' | 'D' | 'L'

interface FormMatch {
  result: FormResult
  score?: string
  opponent?: string
  date?: string
}

interface FormDisplayProps {
  /** Team name */
  teamName: string
  /** Recent match results (newest first) */
  matches?: FormMatch[]
  /** Aggregated recent form from the prediction response (home_form / away_form) */
  summary?: TeamFormResponse | null
}

const RESULT_LABELS: Record<FormResult, string> = { W: 'Galibiyet', D: 'Beraberlik', L: 'Mağlubiyet' }
const RESULT_SHORT_LABELS: Record<FormResult, string> = { W: 'G', D: 'B', L: 'M' }

/** Parse a backend form string (e.g. "WWDLW") into indicators; unknown characters are skipped. */
function parseFormString(formString: string | null | undefined): FormMatch[] {
  if (!formString) return []
  return formString
    .toUpperCase()
    .split('')
    .filter((char): char is FormResult => char === 'W' || char === 'D' || char === 'L')
    .map((result) => ({ result }))
}

function FormSummary({ summary }: { summary: TeamFormResponse }) {
  const items: { label: string; value: number | null | undefined }[] = [
    { label: 'Galibiyet', value: summary.wins },
    { label: 'Beraberlik', value: summary.draws },
    { label: 'Mağlubiyet', value: summary.losses },
    { label: 'Puan', value: summary.points },
    { label: 'Atılan gol', value: summary.goals_for },
    { label: 'Yenilen gol', value: summary.goals_against },
  ]
  return (
    <div className="form-summary">
      <dl className="form-summary__grid">
        {items.map((item) => (
          <div key={item.label} className="form-summary__item">
            <dt className="form-summary__label">{item.label}</dt>
            <dd className="form-summary__value">
              <UnavailableValue value={formatNumber(item.value)} />
            </dd>
          </div>
        ))}
      </dl>
      <p className="form-summary__note">
        Analiz edilen maç: <UnavailableValue value={formatNumber(summary.matches_analyzed)} />
      </p>
    </div>
  )
}

export default function FormDisplay({
  teamName,
  matches,
  summary
}: FormDisplayProps) {
  const formMatches = matches && matches.length > 0 ? matches : parseFormString(summary?.form_string)

  // Aggregated summary without per-match results
  if (formMatches.length === 0 && summary) {
    return (
      <div className="form-display">
        <h5 className="form-display__title">{teamName} - Son Performans</h5>
        <FormSummary summary={summary} />
      </div>
    )
  }

  // Empty state - no form data available
  if (formMatches.length === 0) {
    return (
      <div className="form-display form-display--empty">
        <h5 className="form-display__title">{teamName} - Son Performans</h5>
        <div className="form-display__empty-state">
          <span className="empty-state-icon">📊</span>
          <span className="empty-state-text">Form verisi mevcut değil</span>
        </div>
      </div>
    )
  }

  // Take last 5 matches
  const recentMatches = formMatches.slice(0, 5)

  return (
    <div className="form-display">
      <h5 className="form-display__title">{teamName} - Son Performans</h5>
      
      <div className="form-indicators">
        {recentMatches.map((match, idx) => (
          <div
            key={idx}
            className={`form-indicator form-indicator--${match.result.toLowerCase()}`}
            title={match.opponent ? `${RESULT_LABELS[match.result]} - ${match.opponent}` : RESULT_LABELS[match.result]}
            aria-label={RESULT_LABELS[match.result]}
          >
            {RESULT_SHORT_LABELS[match.result]}
          </div>
        ))}
      </div>
      
      {summary && <FormSummary summary={summary} />}

      {/* Optional: Show match details if available */}
      {recentMatches.some(m => m.score || m.opponent) && (
        <div className="form-details">
          {recentMatches.map((match, idx) => (
            match.opponent || match.score ? (
              <div key={idx} className="form-detail-item">
                {match.opponent && <span className="form-detail-opponent">{match.opponent}</span>}
                {match.score && <span className="form-detail-score">{match.score}</span>}
              </div>
            ) : null
          ))}
        </div>
      )}
    </div>
  )
}
