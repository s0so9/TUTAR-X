/**
 * HeadToHead Component
 * 
 * Displays recent head-to-head meetings between two teams.
 * Shows empty state if no H2H data available.
 */

import type { HeadToHeadResponse } from '../../api/types'
import { UnavailableValue } from '../ui'
import { formatNumber } from '../../utils/displayValue'
import './HeadToHead.css'

interface H2HMatch {
  date: string
  homeTeam: string
  awayTeam: string
  score: string
  competition?: string
}

interface HeadToHeadProps {
  /** Home team name */
  homeTeam: string
  /** Away team name */
  awayTeam: string
  /** Recent head-to-head matches */
  matches?: H2HMatch[]
  /** Aggregated H2H record from the prediction response (head_to_head), home-team perspective */
  summary?: HeadToHeadResponse | null
}

function H2HSummary({
  summary,
  homeTeam,
  awayTeam
}: {
  summary: HeadToHeadResponse
  homeTeam: string
  awayTeam: string
}) {
  const items: { label: string; value: number | null | undefined }[] = [
    { label: 'Toplam maç', value: summary.total_matches },
    { label: `${homeTeam} galibiyeti`, value: summary.home_wins },
    { label: 'Beraberlik', value: summary.draws },
    { label: `${awayTeam} galibiyeti`, value: summary.away_wins },
    { label: `${homeTeam} golü`, value: summary.home_goals },
    { label: `${awayTeam} golü`, value: summary.away_goals },
  ]
  return (
    <dl className="h2h-summary">
      {items.map((item) => (
        <div key={item.label} className="h2h-summary__item">
          <dt className="h2h-summary__label">{item.label}</dt>
          <dd className="h2h-summary__value">
            <UnavailableValue value={formatNumber(item.value)} />
          </dd>
        </div>
      ))}
    </dl>
  )
}

export default function HeadToHead({
  homeTeam,
  awayTeam,
  matches,
  summary
}: HeadToHeadProps) {
  const hasSummary = !!summary && typeof summary.total_matches === 'number' && summary.total_matches > 0

  // Aggregated record only (no per-match list)
  if ((!matches || matches.length === 0) && hasSummary) {
    return (
      <div className="head-to-head">
        <h5 className="head-to-head__title">
          Karşılıklı Geçmiş ({homeTeam} vs {awayTeam})
        </h5>
        <H2HSummary summary={summary} homeTeam={homeTeam} awayTeam={awayTeam} />
      </div>
    )
  }

  // Empty state - no H2H data available
  if (!matches || matches.length === 0) {
    return (
      <div className="head-to-head head-to-head--empty">
        <h5 className="head-to-head__title">Karşılıklı Geçmiş</h5>
        <div className="head-to-head__empty-state">
          <span className="empty-state-icon">🔄</span>
          <span className="empty-state-text">
            {homeTeam} ve {awayTeam} arasında geçmiş maç verisi mevcut değil
          </span>
        </div>
      </div>
    )
  }

  return (
    <div className="head-to-head">
      <h5 className="head-to-head__title">
        Karşılıklı Geçmiş ({homeTeam} vs {awayTeam})
      </h5>

      {hasSummary && <H2HSummary summary={summary} homeTeam={homeTeam} awayTeam={awayTeam} />}
      
      <div className="h2h-matches">
        {matches.map((match, idx) => (
          <div key={idx} className="h2h-match">
            <div className="h2h-match__date">
              {new Date(match.date).toLocaleDateString('tr-TR', {
                day: 'numeric',
                month: 'short',
                year: 'numeric'
              })}
            </div>
            
            <div className="h2h-match__teams">
              <span className="h2h-match__team">{match.homeTeam}</span>
              <span className="h2h-match__separator">vs</span>
              <span className="h2h-match__team">{match.awayTeam}</span>
            </div>
            
            <div className="h2h-match__score">{match.score}</div>
            
            {match.competition && (
              <div className="h2h-match__competition">{match.competition}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
