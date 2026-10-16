/**
 * StatusBadge Component
 * 
 * Displays status with color, icon, and label for accessibility.
 * Color is derived dynamically from actual numeric values.
 */

import { StatusResult } from '../../utils/visualization'

interface StatusBadgeProps {
  status: StatusResult
  showIcon?: boolean
  showLabel?: boolean
}

export default function StatusBadge({ 
  status, 
  showIcon = true, 
  showLabel = true 
}: StatusBadgeProps) {
  const badgeClass = `status-badge status-badge--${status.level}`
  const icon = getIconForLevel(status.level)

  return (
    <span className={badgeClass} role="status">
      {showIcon && (
        <span className="status-badge__icon" aria-hidden="true">
          {icon}
        </span>
      )}
      {showLabel && (
        <span className="status-badge__label">{status.label}</span>
      )}
    </span>
  )
}

function getIconForLevel(level: string): string {
  switch (level) {
    case 'negative':
    case 'low':
      return '↓'
    case 'weak':
    case 'medium':
      return '→'
    case 'positive':
    case 'high':
      return '↑'
    case 'strong':
    case 'very-high':
      return '⬆'
    default:
      return '•'
  }
}
