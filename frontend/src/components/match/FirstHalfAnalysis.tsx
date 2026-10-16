/**
 * FirstHalfAnalysis Component
 * 
 * Displays first-half specific markets and analysis.
 * Only shows markets that exist in data - never fabricates values.
 */

import MarketRow from '../predictions/MarketRow'
import type { MatchPredictionResponse, MatchResponse } from '../../api/types'
import './FirstHalfAnalysis.css'

interface FirstHalfAnalysisProps {
  /** Match prediction data */
  prediction: MatchPredictionResponse
  /** Match data */
  match: MatchResponse
  /** Whether markets are in combine (by matchId) */
  isInCombine: (matchId: string) => boolean
  /** Callback when combine is toggled */
  onToggleCombine: (matchId: string, marketName: string, confidence: number, odds: number) => void
}

/**
 * Extract first-half markets from prediction data
 * Currently market_analysis is deprecated, so we check mensione_pick
 * In future, dedicated first-half markets may be added to the API
 */
function extractFirstHalfMarkets(prediction: MatchPredictionResponse) {
  const markets: Array<{
    name: string
    confidence: number
    odds: number
  }> = []

  // Check if mensione_pick is a first-half market
  if (prediction.mensione_pick) {
    const pick = prediction.mensione_pick
    const pickMarket = (pick.market || '').toUpperCase()
    
    // Detect first-half related picks
    if (pickMarket.includes('FIRST HALF') || pickMarket.includes('HT') || pickMarket.includes('İLK YARI')) {
      markets.push({
        name: pick.market || 'Unknown',
        confidence: pick.confidence ?? 0,
        odds: pick.fair_odds ?? 0
      })
    }
  }

  // In future: parse market_analysis for first-half specific markets
  // For now, return empty if no first-half data
  return markets
}

export default function FirstHalfAnalysis({
  prediction,
  match,
  isInCombine,
  onToggleCombine
}: FirstHalfAnalysisProps) {
  const firstHalfMarkets = extractFirstHalfMarkets(prediction)
  
  // Empty state - no first-half data available
  if (firstHalfMarkets.length === 0) {
    return (
      <div className="first-half-analysis">
        <div className="first-half-analysis__empty-state">
          <div className="empty-state-icon">📊</div>
          <h3 className="empty-state-title">İlk yarı analizi mevcut değil</h3>
          <p className="empty-state-description">
            Bu maç için ilk yarı tahminleri henüz oluşturulmadı veya yeterli veri bulunmamaktadır.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="first-half-analysis">
      <div className="markets-list">
        {firstHalfMarkets.map((market, idx) => (
          <MarketRow
            key={idx}
            marketName={market.name}
            confidence={market.confidence}
            realOdds={market.odds}
            inCombine={isInCombine(match.id)}
            onToggleCombine={() => onToggleCombine(
              match.id,
              market.name,
              market.confidence,
              market.odds
            )}
          />
        ))}
      </div>
    </div>
  )
}
