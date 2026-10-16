/**
 * AIConfidence Component
 * 
 * TUTAR X AI Confidence indicator with 1-6 money-bag scale.
 * Uses custom CSS icons with TUTAR X green glow that scales by confidence level.
 * 
 * Confidence Mapping (0-1 or 0-100):
 * 1/6 (Çok Düşük):  0.00 - 0.16
 * 2/6 (Düşük):      0.17 - 0.33
 * 3/6 (Orta):       0.34 - 0.50
 * 4/6 (İyi):        0.51 - 0.67
 * 5/6 (Yüksek):     0.68 - 0.83
 * 6/6 (Çok Yüksek): 0.84 - 1.00
 */

import './AIConfidence.css'

interface AIConfidenceProps {
  /** Confidence value (0-1 or 0-100) */
  confidence: number
  /** Show percentage text */
  showPercentage?: boolean
  /** Show level text (e.g., "5/6") */
  showLevel?: boolean
  /** Show Turkish label (e.g., "Yüksek") */
  showLabel?: boolean
  /** Component size variant */
  size?: 'sm' | 'md' | 'lg'
}

interface ConfidenceLevel {
  level: number
  label: string
  glowClass: string
}

const CONFIDENCE_LABELS = [
  'Çok düşük',
  'Düşük',
  'Orta',
  'İyi',
  'Yüksek',
  'Çok yüksek'
]

/**
 * Map confidence value (0-1 or 0-100) to 1-6 level
 */
function getConfidenceLevel(confidence: number): ConfidenceLevel {
  // Normalize to 0-1 range if value is > 1 (assume 0-100)
  const normalized = confidence > 1 ? confidence / 100 : confidence
  
  // Map to 1-6 scale
  let level: number
  if (normalized <= 0.16) {
    level = 1
  } else if (normalized <= 0.33) {
    level = 2
  } else if (normalized <= 0.5) {
    level = 3
  } else if (normalized <= 0.67) {
    level = 4
  } else if (normalized <= 0.83) {
    level = 5
  } else {
    level = 6
  }
  
  return {
    level,
    label: CONFIDENCE_LABELS[level - 1],
    glowClass: `ai-confidence__icon--glow-${level}`
  }
}

export default function AIConfidence({
  confidence,
  showPercentage = true,
  showLevel = true,
  showLabel = true,
  size = 'md'
}: AIConfidenceProps) {
  const { level, label, glowClass } = getConfidenceLevel(confidence)
  
  // Normalize confidence for display
  const normalizedConfidence = confidence > 1 ? confidence : confidence * 100
  
  // Generate array of 6 icons (filled vs inactive)
  const icons = Array.from({ length: 6 }, (_, index) => ({
    active: index < level,
    key: `icon-${index}`
  }))
  
  const sizeClass = `ai-confidence--${size}`
  
  return (
    <div className={`ai-confidence ${sizeClass}`} role="status" aria-label={`Yapay zeka güveni: ${label}, ${normalizedConfidence.toFixed(0)}%`}>
      {/* Money-bag icons */}
      <div className="ai-confidence__icons" aria-hidden="true">
        {icons.map(({ active, key }) => (
          <div
            key={key}
            className={`ai-confidence__icon ${
              active ? `ai-confidence__icon--active ${glowClass}` : 'ai-confidence__icon--inactive'
            }`}
          >
            {/* Enhanced money bag SVG - classic money sack silhouette 💰 */}
            <svg viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
              {/* Gathered neck/tie at top */}
              <path d="M10 3C10 3 11 2 12 2C13 2 14 3 14 3L15 5H9L10 3Z" opacity="0.85"/>
              {/* Main rounded money sack body */}
              <path d="M8 5C7.5 5 7 5.5 7 6C7 6.5 6.5 8 6.5 10C6.5 12 6 15 7 17C8 19 9.5 21 12 21C14.5 21 16 19 17 17C18 15 17.5 12 17.5 10C17.5 8 17 6.5 17 6C17 5.5 16.5 5 16 5H8Z"/>
              {/* Currency symbol */}
              <text x="12" y="14.5" fontSize="7" fontWeight="900" textAnchor="middle" fill="currentColor" opacity="0.75">$</text>
            </svg>
          </div>
        ))}
      </div>
      
      {/* Level and label */}
      <div className="ai-confidence__info">
        {showLevel && (
          <span className="ai-confidence__level">{level}/6</span>
        )}
        {showLabel && (
          <span className="ai-confidence__label">{label}</span>
        )}
      </div>
      
      {/* Percentage */}
      {showPercentage && (
        <div className="ai-confidence__percentage">
          %{Math.round(normalizedConfidence)}
        </div>
      )}
    </div>
  )
}
