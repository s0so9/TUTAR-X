/**
 * ConfidenceIndicator Component
 * 
 * Displays confidence level with dynamic color and visual indicator.
 * Uses both color and text/icon for accessibility.
 */

import { getConfidenceStatus, formatProbability } from '../../utils/visualization'

interface ConfidenceIndicatorProps {
  confidence: number
  decimals?: number
  showValue?: boolean
  showLabel?: boolean
  variant?: 'inline' | 'badge'
}

export default function ConfidenceIndicator({
  confidence,
  decimals = 1,
  showValue = true,
  showLabel = true,
  variant = 'inline'
}: ConfidenceIndicatorProps) {
  const status = getConfidenceStatus(confidence)
  const formatted = formatProbability(confidence, decimals)

  if (variant === 'badge') {
    const badgeClass = `status-badge status-badge--${status.level}`
    return (
      <span className={badgeClass} role="status" aria-label={`Güven seviyesi: ${status.label}`}>
        {showValue && <span>{formatted}</span>}
        {showLabel && <span>{status.label}</span>}
      </span>
    )
  }

  return (
    <span className={`confidence-indicator ${status.className}`} role="status">
      <span className="confidence-indicator__icon" aria-hidden="true">
        {getConfidenceIcon(status.level)}
      </span>
      {showValue && (
        <span className="confidence-indicator__value">{formatted}</span>
      )}
      {showLabel && (
        <span className="confidence-indicator__label">{status.label}</span>
      )}
    </span>
  )
}

function getConfidenceIcon(level: string): string {
  switch (level) {
    case 'low':
      return '🔴'
    case 'medium':
      return '🟡'
    case 'high':
      return '🟢'
    case 'very-high':
      return '🟢'
    default:
      return '⚪'
  }
}
