/**
 * TUTAR X Data Visualization Utilities
 * 
 * Dynamic status determination for football analytics data.
 * Colors are derived from actual numeric values, never hardcoded.
 */

export type StatusLevel = 'negative' | 'weak' | 'positive' | 'strong'
export type ConfidenceLevel = 'low' | 'medium' | 'high' | 'very-high'

export interface StatusResult {
  level: StatusLevel | ConfidenceLevel
  className: string
  label: string
}

/**
 * Get probability/win-rate status
 * < 40% → red/negative
 * 40-49.99% → orange/weak
 * 50-64.99% → green/positive
 * 65%+ → stronger green/high confidence
 */
export function getProbabilityStatus(probability: number): StatusResult {
  // Normalize to 0-100 if needed
  const value = probability > 1 ? probability : probability * 100

  if (value < 40) {
    return {
      level: 'negative',
      className: 'status-negative',
      label: 'Düşük'
    }
  } else if (value < 50) {
    return {
      level: 'weak',
      className: 'status-weak',
      label: 'Zayıf'
    }
  } else if (value < 65) {
    return {
      level: 'positive',
      className: 'status-positive',
      label: 'İyi'
    }
  } else {
    return {
      level: 'strong',
      className: 'status-strong',
      label: 'Güçlü'
    }
  }
}

/**
 * Get confidence level status
 * < 50% → red
 * 50-69.99% → orange
 * 70-84.99% → green
 * 85%+ → stronger green/high confidence
 */
export function getConfidenceStatus(confidence: number): StatusResult {
  // Normalize to 0-100 if needed
  const value = confidence > 1 ? confidence : confidence * 100

  if (value < 50) {
    return {
      level: 'low',
      className: 'confidence-low',
      label: 'Düşük Güven'
    }
  } else if (value < 70) {
    return {
      level: 'medium',
      className: 'confidence-medium',
      label: 'Orta Güven'
    }
  } else if (value < 85) {
    return {
      level: 'high',
      className: 'confidence-high',
      label: 'Yüksek Güven'
    }
  } else {
    return {
      level: 'very-high',
      className: 'confidence-very-high',
      label: 'Çok Yüksek Güven'
    }
  }
}

/**
 * Get value/edge status
 * negative → red
 * near zero → muted
 * positive → green
 */
export function getValueStatus(value: number, threshold: number = 0.02): StatusResult {
  if (value < -threshold) {
    return {
      level: 'negative',
      className: 'value-negative',
      label: 'Değer Yok'
    }
  } else if (value >= -threshold && value <= threshold) {
    return {
      level: 'weak',
      className: 'value-neutral',
      label: 'Nötr'
    }
  } else {
    return {
      level: 'positive',
      className: 'value-positive',
      label: 'Değer Var'
    }
  }
}

/**
 * Get performance metric status (ROI, accuracy, etc.)
 * positive → green
 * negative → red
 * near zero → muted
 */
export function getPerformanceStatus(value: number, threshold: number = 0): StatusResult {
  if (value < threshold) {
    return {
      level: 'negative',
      className: 'performance-negative',
      label: 'Negatif'
    }
  } else if (value === threshold) {
    return {
      level: 'weak',
      className: 'performance-neutral',
      label: 'Nötr'
    }
  } else {
    return {
      level: 'positive',
      className: 'performance-positive',
      label: 'Pozitif'
    }
  }
}

/**
 * Get calibration quality status
 * Based on calibration error (lower is better)
 */
export function getCalibrationStatus(error: number): StatusResult {
  if (error > 0.1) {
    return {
      level: 'negative',
      className: 'calibration-poor',
      label: 'Zayıf Kalibrasyon'
    }
  } else if (error > 0.05) {
    return {
      level: 'weak',
      className: 'calibration-moderate',
      label: 'Orta Kalibrasyon'
    }
  } else if (error > 0.02) {
    return {
      level: 'positive',
      className: 'calibration-good',
      label: 'İyi Kalibrasyon'
    }
  } else {
    return {
      level: 'strong',
      className: 'calibration-excellent',
      label: 'Mükemmel Kalibrasyon'
    }
  }
}

/**
 * Get match prediction signal status
 * Based on probability difference from neutral (33.33% for 1X2)
 */
export function getMatchSignalStatus(
  probability: number,
  neutralPoint: number = 0.333
): StatusResult {
  const diff = probability - neutralPoint

  if (diff < 0.1) {
    return {
      level: 'weak',
      className: 'signal-weak',
      label: 'Zayıf Sinyal'
    }
  } else if (diff < 0.2) {
    return {
      level: 'positive',
      className: 'signal-moderate',
      label: 'Orta Sinyal'
    }
  } else {
    return {
      level: 'strong',
      className: 'signal-strong',
      label: 'Güçlü Sinyal'
    }
  }
}

/**
 * Format probability as percentage
 */
export function formatProbability(probability: number, decimals: number = 1): string {
  const value = probability > 1 ? probability : probability * 100
  return `${value.toFixed(decimals)}%`
}

/**
 * Format decimal odds
 */
export function formatOdds(odds: number, decimals: number = 2): string {
  return odds.toFixed(decimals)
}

/**
 * Format xG (expected goals)
 */
export function formatXG(xg: number, decimals: number = 2): string {
  return xg.toFixed(decimals)
}

/**
 * Format ROI as percentage with sign
 */
export function formatROI(roi: number, decimals: number = 1): string {
  const sign = roi > 0 ? '+' : ''
  return `${sign}${roi.toFixed(decimals)}%`
}

/**
 * Get color variable name for status
 * For use with CSS custom properties
 */
export function getStatusColor(level: StatusLevel | ConfidenceLevel): string {
  switch (level) {
    case 'negative':
    case 'low':
      return 'var(--color-status-negative)'
    case 'weak':
    case 'medium':
      return 'var(--color-status-weak)'
    case 'positive':
    case 'high':
      return 'var(--color-status-positive)'
    case 'strong':
    case 'very-high':
      return 'var(--color-status-strong)'
    default:
      return 'var(--color-text-secondary)'
  }
}

/**
 * Get icon for probability status
 * For accessibility - color should not be the only indicator
 */
export function getStatusIcon(level: StatusLevel | ConfidenceLevel): string {
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
