/**
 * ProbabilityDisplay Component
 * 
 * Displays probability value with dynamic color based on thresholds.
 * Includes icon for accessibility (color not the only indicator).
 */

import { getProbabilityStatus, formatProbability, getStatusIcon } from '../../utils/visualization'

interface ProbabilityDisplayProps {
  probability: number
  decimals?: number
  showIcon?: boolean
  showLabel?: boolean
  large?: boolean
}

export default function ProbabilityDisplay({
  probability,
  decimals = 1,
  showIcon = true,
  showLabel = false,
  large = false
}: ProbabilityDisplayProps) {
  const status = getProbabilityStatus(probability)
  const formatted = formatProbability(probability, decimals)
  const icon = getStatusIcon(status.level)

  const className = `probability-display ${status.className} ${large ? 'probability-display--large' : ''}`

  return (
    <span className={className}>
      {showIcon && (
        <span className="probability-display__icon" aria-hidden="true">
          {icon}
        </span>
      )}
      <span className="probability-display__value">{formatted}</span>
      {showLabel && (
        <span className="probability-display__label" aria-label={status.label}>
          {status.label}
        </span>
      )}
    </span>
  )
}
