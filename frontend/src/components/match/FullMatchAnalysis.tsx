/**
 * FullMatchAnalysis Component
 * 
 * Displays full match statistical markets and analysis.
 * Only shows markets that exist in data - never fabricates values.
 */

import MarketRow from '../predictions/MarketRow'
import type { MatchPredictionResponse, MatchResponse } from '../../api/types'
import './FullMatchAnalysis.css'

interface FullMatchAnalysisProps {
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
 * Extract full match statistical markets from prediction data
 * Includes: Over/Under, BTTS, Corners, Cards, Shots if available
 */
function extractFullMatchMarkets(prediction: MatchPredictionResponse) {
  const markets: Array<{
    name: string
    confidence: number
    odds: number
  }> = []

  // Extract from market_analysis if available (deprecated but may still contain data)
  if (prediction.market_analysis) {
    for (const market of prediction.market_analysis) {
      const { market_type, line, outcomes } = market
      
      // Over/Under markets
      if (market_type === 'over_under' && line !== null && outcomes.length > 0) {
        // Over
        const overOutcome = outcomes.find(o => o.label === 'Over')
        if (overOutcome) {
          markets.push({
            name: `Üst ${line}`,
            confidence: overOutcome.model_probability,
            odds: overOutcome.fair_odds
          })
        }
        
        // Under
        const underOutcome = outcomes.find(o => o.label === 'Under')
        if (underOutcome) {
          markets.push({
            name: `Alt ${line}`,
            confidence: underOutcome.model_probability,
            odds: underOutcome.fair_odds
          })
        }
      }
      
      // BTTS markets
      if (market_type === 'btts' && outcomes.length > 0) {
        for (const outcome of outcomes) {
          markets.push({
            name: `BTTS ${outcome.label === 'Yes' ? 'Evet' : 'Hayır'}`,
            confidence: outcome.model_probability,
            odds: outcome.fair_odds
          })
        }
      }
    }
  }

  // Add BTTS from top-level if not already added
  if (markets.length === 0 && prediction.btts_probability > 0) {
    markets.push({
      name: 'BTTS Evet',
      confidence: prediction.btts_probability,
      odds: 1 / prediction.btts_probability // Convert probability to fair odds
    })
    markets.push({
      name: 'BTTS Hayır',
      confidence: 1 - prediction.btts_probability,
      odds: 1 / (1 - prediction.btts_probability)
    })
  }

  return markets
}

export default function FullMatchAnalysis({
  prediction,
  match,
  isInCombine,
  onToggleCombine
}: FullMatchAnalysisProps) {
  const fullMatchMarkets = extractFullMatchMarkets(prediction)
  
  // Empty state - no full match statistical markets available
  if (fullMatchMarkets.length === 0) {
    return (
      <div className="full-match-analysis">
        <div className="full-match-analysis__empty-state">
          <div className="empty-state-icon">📈</div>
          <h3 className="empty-state-title">Tam maç analizi mevcut değil</h3>
          <p className="empty-state-description">
            Bu maç için detaylı istatistik tahminleri henüz oluşturulmadı veya yeterli veri bulunmamaktadır.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="full-match-analysis">
      <div className="markets-list">
        {fullMatchMarkets.map((market, idx) => (
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
