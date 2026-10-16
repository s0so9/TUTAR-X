/**
 * LiveMatchCard Component
 * 
 * Displays live match information with red pulse indicator.
 * Handles empty/loading/unavailable states gracefully.
 * Respects prefers-reduced-motion for pulse animation.
 */

import './LiveMatchCard.css'

interface LiveStats {
  shots?: number
  shotsOnTarget?: number
  corners?: number
  possession?: number
}

interface Score {
  home: number
  away: number
}

interface LiveMatchCardProps {
  /** Home team name */
  homeTeam: string
  /** Away team name */
  awayTeam: string
  /** Current score */
  score: Score
  /** Match minute */
  minute: number
  /** Match status */
  status: 'live' | 'ht' | 'ft'
  /** Live statistics (optional) */
  liveStats?: LiveStats
  /** Loading state */
  isLoading?: boolean
}

export default function LiveMatchCard({
  homeTeam,
  awayTeam,
  score,
  minute,
  status,
  liveStats,
  isLoading = false
}: LiveMatchCardProps) {
  if (isLoading) {
    return (
      <div className="live-match-card live-match-card--loading" aria-busy="true" aria-label="Yükleniyor">
        <div className="live-match-card__skeleton">
          <div className="skeleton skeleton--indicator"></div>
          <div className="skeleton skeleton--teams"></div>
          <div className="skeleton skeleton--score"></div>
          <div className="skeleton skeleton--minute"></div>
        </div>
      </div>
    )
  }
  
  const statusText = status === 'ht' ? 'İlk Yarı' : status === 'ft' ? 'Maç Bitti' : 'CANLI'
  const statusClass = `live-match-card__status--${status}`
  
  return (
    <article className="live-match-card">
      {/* Live indicator with pulse */}
      <div className={`live-match-card__status ${statusClass}`}>
        {status === 'live' && <span className="live-indicator" aria-label="Canlı maç"></span>}
        <span className="live-match-card__status-text">{statusText}</span>
      </div>
      
      {/* Teams */}
      <div className="live-match-card__teams">
        <div className="live-match-card__team">{homeTeam}</div>
        <div className="live-match-card__team">{awayTeam}</div>
      </div>
      
      {/* Score */}
      <div className="live-match-card__score">
        <span className="live-match-card__score-value">{score.home}</span>
        <span className="live-match-card__score-separator">-</span>
        <span className="live-match-card__score-value">{score.away}</span>
      </div>
      
      {/* Minute */}
      <div className="live-match-card__minute">{minute}'</div>
      
      {/* Live stats - if available */}
      {liveStats ? (
        <div className="live-stats" aria-label="Canlı istatistikler">
          {liveStats.shots !== undefined && (
            <div className="live-stats__item">
              <span className="live-stats__label">Şut</span>
              <span className="live-stats__value">{liveStats.shots}</span>
            </div>
          )}
          {liveStats.shotsOnTarget !== undefined && (
            <div className="live-stats__item">
              <span className="live-stats__label">İsabetli</span>
              <span className="live-stats__value">{liveStats.shotsOnTarget}</span>
            </div>
          )}
          {liveStats.corners !== undefined && (
            <div className="live-stats__item">
              <span className="live-stats__label">Korner</span>
              <span className="live-stats__value">{liveStats.corners}</span>
            </div>
          )}
          {liveStats.possession !== undefined && (
            <div className="live-stats__item">
              <span className="live-stats__label">Hücum</span>
              <span className="live-stats__value">{liveStats.possession}%</span>
            </div>
          )}
        </div>
      ) : (
        <div className="live-stats--unavailable">
          <span className="live-stats__unavailable-text">Canlı istatistikler mevcut değil</span>
        </div>
      )}
    </article>
  )
}

/**
 * EmptyLiveMatchCard - shown when no live matches
 */
export function EmptyLiveMatchCard() {
  return (
    <div className="live-match-card live-match-card--empty">
      <div className="live-match-card__empty-text">Şu anda canlı maç bulunmuyor</div>
    </div>
  )
}
