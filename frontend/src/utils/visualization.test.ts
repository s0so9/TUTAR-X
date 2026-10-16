/**
 * TUTAR X Data Visualization Rules - Test Suite
 * 
 * Verifies that status determination follows the specified rules.
 */

import { describe, it, expect } from 'vitest'
import {
  getProbabilityStatus,
  getConfidenceStatus,
  getValueStatus,
  getPerformanceStatus,
  getCalibrationStatus,
  formatProbability,
  formatOdds,
  formatROI,
} from './visualization'

describe('getProbabilityStatus', () => {
  it('should return negative for < 40%', () => {
    expect(getProbabilityStatus(0.31).level).toBe('negative')
    expect(getProbabilityStatus(0.39).level).toBe('negative')
    expect(getProbabilityStatus(31.2).level).toBe('negative')
  })

  it('should return weak for 40-49.99%', () => {
    expect(getProbabilityStatus(0.40).level).toBe('weak')
    expect(getProbabilityStatus(0.487).level).toBe('weak')
    expect(getProbabilityStatus(0.4999).level).toBe('weak')
    expect(getProbabilityStatus(48.7).level).toBe('weak')
  })

  it('should return positive for 50-64.99%', () => {
    expect(getProbabilityStatus(0.50).level).toBe('positive')
    expect(getProbabilityStatus(0.524).level).toBe('positive')
    expect(getProbabilityStatus(0.6499).level).toBe('positive')
    expect(getProbabilityStatus(52.4).level).toBe('positive')
  })

  it('should return strong for >= 65%', () => {
    expect(getProbabilityStatus(0.65).level).toBe('strong')
    expect(getProbabilityStatus(0.87).level).toBe('strong')
    expect(getProbabilityStatus(87).level).toBe('strong')
  })

  it('should handle both decimal (0-1) and percentage (0-100) formats', () => {
    expect(getProbabilityStatus(0.52).level).toBe(getProbabilityStatus(52).level)
    expect(getProbabilityStatus(0.65).level).toBe(getProbabilityStatus(65).level)
  })
})

describe('getConfidenceStatus', () => {
  it('should return low for < 50%', () => {
    expect(getConfidenceStatus(0.30).level).toBe('low')
    expect(getConfidenceStatus(0.49).level).toBe('low')
    expect(getConfidenceStatus(30).level).toBe('low')
  })

  it('should return medium for 50-69.99%', () => {
    expect(getConfidenceStatus(0.50).level).toBe('medium')
    expect(getConfidenceStatus(0.60).level).toBe('medium')
    expect(getConfidenceStatus(0.6999).level).toBe('medium')
    expect(getConfidenceStatus(60).level).toBe('medium')
  })

  it('should return high for 70-84.99%', () => {
    expect(getConfidenceStatus(0.70).level).toBe('high')
    expect(getConfidenceStatus(0.75).level).toBe('high')
    expect(getConfidenceStatus(0.8499).level).toBe('high')
    expect(getConfidenceStatus(75).level).toBe('high')
  })

  it('should return very-high for >= 85%', () => {
    expect(getConfidenceStatus(0.85).level).toBe('very-high')
    expect(getConfidenceStatus(0.95).level).toBe('very-high')
    expect(getConfidenceStatus(87).level).toBe('very-high')
  })
})

describe('getValueStatus', () => {
  it('should return negative for negative values beyond threshold', () => {
    expect(getValueStatus(-0.05).level).toBe('negative')
    expect(getValueStatus(-0.10).level).toBe('negative')
  })

  it('should return weak/neutral for values near zero', () => {
    expect(getValueStatus(0.01).level).toBe('weak')
    expect(getValueStatus(-0.01).level).toBe('weak')
    expect(getValueStatus(0.0).level).toBe('weak')
  })

  it('should return positive for positive values beyond threshold', () => {
    expect(getValueStatus(0.05).level).toBe('positive')
    expect(getValueStatus(0.10).level).toBe('positive')
  })

  it('should respect custom threshold', () => {
    expect(getValueStatus(0.03, 0.05).level).toBe('weak')
    expect(getValueStatus(0.06, 0.05).level).toBe('positive')
  })
})

describe('getPerformanceStatus', () => {
  it('should return negative for negative values', () => {
    expect(getPerformanceStatus(-5.2).level).toBe('negative')
    expect(getPerformanceStatus(-0.1).level).toBe('negative')
  })

  it('should return weak/neutral for zero', () => {
    expect(getPerformanceStatus(0).level).toBe('weak')
  })

  it('should return positive for positive values', () => {
    expect(getPerformanceStatus(3.5).level).toBe('positive')
    expect(getPerformanceStatus(0.1).level).toBe('positive')
  })
})

describe('getCalibrationStatus', () => {
  it('should return poor for error > 0.1', () => {
    expect(getCalibrationStatus(0.15).level).toBe('negative')
    expect(getCalibrationStatus(0.20).level).toBe('negative')
  })

  it('should return moderate for error > 0.05', () => {
    expect(getCalibrationStatus(0.06).level).toBe('weak')
    expect(getCalibrationStatus(0.08).level).toBe('weak')
  })

  it('should return good for error > 0.02', () => {
    expect(getCalibrationStatus(0.03).level).toBe('positive')
    expect(getCalibrationStatus(0.04).level).toBe('positive')
  })

  it('should return excellent for error <= 0.02', () => {
    expect(getCalibrationStatus(0.01).level).toBe('strong')
    expect(getCalibrationStatus(0.02).level).toBe('strong')
  })
})

describe('formatProbability', () => {
  it('should format decimal probabilities as percentages', () => {
    expect(formatProbability(0.524)).toBe('52.4%')
    expect(formatProbability(0.487)).toBe('48.7%')
    expect(formatProbability(0.87)).toBe('87.0%')
  })

  it('should handle percentage input', () => {
    expect(formatProbability(52.4)).toBe('52.4%')
    expect(formatProbability(87)).toBe('87.0%')
  })

  it('should respect decimals parameter', () => {
    expect(formatProbability(0.5243, 2)).toBe('52.43%')
    expect(formatProbability(0.5243, 0)).toBe('52%')
  })
})

describe('formatOdds', () => {
  it('should format odds with 2 decimals by default', () => {
    expect(formatOdds(2.50)).toBe('2.50')
    expect(formatOdds(1.85)).toBe('1.85')
  })

  it('should respect decimals parameter', () => {
    expect(formatOdds(2.5, 1)).toBe('2.5')
    expect(formatOdds(2.567, 3)).toBe('2.567')
  })
})

describe('formatROI', () => {
  it('should format positive ROI with + sign', () => {
    expect(formatROI(5.2)).toBe('+5.2%')
    expect(formatROI(12.8)).toBe('+12.8%')
  })

  it('should format negative ROI without + sign', () => {
    expect(formatROI(-3.5)).toBe('-3.5%')
    expect(formatROI(-8.2)).toBe('-8.2%')
  })

  it('should format zero ROI', () => {
    expect(formatROI(0)).toBe('0.0%')
  })
})
