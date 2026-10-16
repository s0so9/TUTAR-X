/**
 * StatisticsComparison Component
 * 
 * Displays compact table comparing team statistics.
 * Shows real values when available, '--' when unavailable.
 * NEVER generates fake statistics.
 */

import type { MatchPredictionResponse } from '../../api/types'
import './StatisticsComparison.css'

interface StatisticsComparisonProps {
  /** Home team name */
  homeTeam: string
  /** Away team name */
  awayTeam: string
  /** Prediction data (contains xG and potentially other stats) */
  prediction: MatchPredictionResponse | null
}

interface StatRow {
  label: string
  homeValue: string | number
  awayValue: string | number
}

export default function StatisticsComparison({
  homeTeam,
  awayTeam,
  prediction
}: StatisticsComparisonProps) {
  // Build statistics rows - only include available data
  const stats: StatRow[] = []
  
  // Expected Goals (xG) - always available from prediction
  if (prediction) {
    stats.push({
      label: 'Beklenen Gol (xG)',
      homeValue: prediction.home_xg.toFixed(2),
      awayValue: prediction.away_xg.toFixed(2)
    })
  }
  
  // Form data - show when available from API
  if (prediction?.home_form && prediction?.away_form) {
    stats.push(
      {
        label: 'Form (G-B-M)',
        homeValue: `${prediction.home_form.wins}-${prediction.home_form.draws}-${prediction.home_form.losses}`,
        awayValue: `${prediction.away_form.wins}-${prediction.away_form.draws}-${prediction.away_form.losses}`
      },
      {
        label: 'Puan',
        homeValue: prediction.home_form.points,
        awayValue: prediction.away_form.points
      },
      {
        label: 'Attığı Gol',
        homeValue: prediction.home_form.goals_for,
        awayValue: prediction.away_form.goals_for
      },
      {
        label: 'Yediği Gol',
        homeValue: prediction.home_form.goals_against,
        awayValue: prediction.away_form.goals_against
      }
    )
  }
  
  // Head-to-Head data - show when available from API
  if (prediction?.head_to_head && prediction.head_to_head.total_matches > 0) {
    stats.push(
      {
        label: 'Karşılıklı Geçmiş',
        homeValue: `${prediction.head_to_head.home_wins} Galibiyet`,
        awayValue: `${prediction.head_to_head.away_wins} Galibiyet`
      },
      {
        label: 'Toplam Karşılaşma',
        homeValue: prediction.head_to_head.total_matches,
        awayValue: `${prediction.head_to_head.draws} Beraberlik`
      }
    )
    
    if (prediction.head_to_head.home_goals !== null && prediction.head_to_head.away_goals !== null) {
      stats.push({
        label: 'Geçmiş Goller',
        homeValue: prediction.head_to_head.home_goals,
        awayValue: prediction.head_to_head.away_goals
      })
    }
  }
  
  // Placeholder rows for future data integration
  // Show '--' to indicate data is not yet available
  stats.push(
    { label: 'Şut', homeValue: '--', awayValue: '--' },
    { label: 'İsabetli Şut', homeValue: '--', awayValue: '--' },
    { label: 'Korner', homeValue: '--', awayValue: '--' },
    { label: 'Topa Sahip %', homeValue: '--', awayValue: '--' }
  )

  return (
    <div className="statistics-comparison">
      <h4 className="statistics-comparison__title">İstatistik Karşılaştırması</h4>
      
      <div className="stats-table">
        {/* Header row */}
        <div className="stats-table__header">
          <div className="stats-table__team-col">{homeTeam}</div>
          <div className="stats-table__stat-col">İstatistik</div>
          <div className="stats-table__team-col">{awayTeam}</div>
        </div>
        
        {/* Data rows */}
        {stats.map((stat, idx) => (
          <div key={idx} className="stats-table__row">
            <div className="stats-table__team-col stats-table__team-col--home">
              {stat.homeValue}
            </div>
            <div className="stats-table__stat-col">
              {stat.label}
            </div>
            <div className="stats-table__team-col stats-table__team-col--away">
              {stat.awayValue}
            </div>
          </div>
        ))}
      </div>
      
      {/* Note about unavailable data */}
      <div className="statistics-comparison__note">
        <span className="note-icon">ℹ️</span>
        <span className="note-text">
          Bazı istatistikler henüz mevcut değil. Veriler güncellendiğinde otomatik olarak gösterilecektir.
        </span>
      </div>
    </div>
  )
}
