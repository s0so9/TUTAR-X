/**
 * ValueIndicator Component
 * 
 * Displays betting value/edge with dynamic color.
 * Negative value → red, neutral → muted, positive → green
 */

import { getValueStatus } from '../../utils/visualization'

interface ValueIndicatorProps {
  value: number
  threshold?: number
  decimals?: number
  showSign?: boolean
}

export default function ValueIndicator({
  value,
  threshold = 0.02,
  decimals = 3,
  showSign = true
}: ValueIndicatorProps) {
  const status = getValueStatus(value, threshold)
  const formatted = value.toFixed(decimals)
  const displayValue = showSign && value > 0 ? `+${formatted}` : formatted

  return (
    <span className={`value-indicator ${status.className}`} role="status">
      <span className="value-indicator__icon" aria-hidden="true">
        {getValueIcon(status.level)}
      </span>
      <span className="value-indicator__value">{displayValue}</span>
      <span className="sr-only">{status.label}</span>
    </span>
  )
}

function getValueIcon(level: string): string {
  switch (level) {
    case 'negative':
      return '✕'
    case 'weak':
      return '○'
    case 'positive':
      return '✓'
    default:
      return '•'
  }
}
