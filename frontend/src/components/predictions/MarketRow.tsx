/**
 * MarketRow Component
 * 
 * Compact single-line row for non-primary markets.
 * Shows market name, confidence percentage, odds, and combine checkbox.
 */

import './MarketRow.css'

interface MarketRowProps {
  /** Market name (e.g., "İlk Yarı 0.5+ Gol") */
  marketName: string
  /** AI confidence (0-1 or 0-100) */
  confidence: number
  /** Real market odds */
  realOdds: number
  /** Whether this market is in combine */
  inCombine: boolean
  /** Callback when combine is toggled */
  onToggleCombine: () => void
}

export default function MarketRow({
  marketName,
  confidence,
  realOdds,
  inCombine,
  onToggleCombine
}: MarketRowProps) {
  // Normalize confidence for display
  const normalizedConfidence = confidence > 1 ? confidence : confidence * 100
  
  return (
    <div className="market-row">
      {/* Market name */}
      <div className="market-row__name">{marketName}</div>
      
      {/* Confidence percentage */}
      <div className="market-row__confidence" aria-label={`Güven: ${normalizedConfidence.toFixed(0)}%`}>
        <span className="market-row__confidence-label">Güven</span>
        <span className="market-row__confidence-value">%{normalizedConfidence.toFixed(0)}</span>
      </div>
      
      {/* Odds */}
      <div className="market-row__odds" aria-label={`Oran: ${realOdds.toFixed(2)}`}>
        <span className="market-row__odds-label">Oran</span>
        <span className="market-row__odds-value">{realOdds.toFixed(2)}</span>
      </div>
      
      {/* Combine checkbox */}
      <label className="market-row__combine-label">
        <input
          type="checkbox"
          className="market-row__combine-checkbox"
          checked={inCombine}
          onChange={onToggleCombine}
          aria-label={`${marketName} - Kombine ${inCombine ? 'çıkar' : 'ekle'}`}
        />
      </label>
    </div>
  )
}
