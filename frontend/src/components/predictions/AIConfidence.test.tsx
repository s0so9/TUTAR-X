/**
 * AIConfidence Component Tests
 * 
 * Tests confidence mapping to 1-6 scale and ensures no hardcoded values.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import AIConfidence from './AIConfidence'

describe('AIConfidence', () => {
  describe('Confidence level mapping', () => {
    it('maps confidence 0.15 to 1/6 "Çok düşük"', () => {
      render(<AIConfidence confidence={0.15} />)
      
      expect(screen.getByText('1/6')).toBeInTheDocument()
      expect(screen.getByText('Çok düşük')).toBeInTheDocument()
      expect(screen.getByText('%15')).toBeInTheDocument()
    })
    
    it('maps confidence 0.25 to 2/6 "Düşük"', () => {
      render(<AIConfidence confidence={0.25} />)
      
      expect(screen.getByText('2/6')).toBeInTheDocument()
      expect(screen.getByText('Düşük')).toBeInTheDocument()
      expect(screen.getByText('%25')).toBeInTheDocument()
    })
    
    it('maps confidence 0.45 to 3/6 "Orta"', () => {
      render(<AIConfidence confidence={0.45} />)
      
      expect(screen.getByText('3/6')).toBeInTheDocument()
      expect(screen.getByText('Orta')).toBeInTheDocument()
      expect(screen.getByText('%45')).toBeInTheDocument()
    })
    
    it('maps confidence 0.60 to 4/6 "İyi"', () => {
      render(<AIConfidence confidence={0.60} />)
      
      expect(screen.getByText('4/6')).toBeInTheDocument()
      expect(screen.getByText('İyi')).toBeInTheDocument()
      expect(screen.getByText('%60')).toBeInTheDocument()
    })
    
    it('maps confidence 0.82 to 5/6 "Yüksek"', () => {
      render(<AIConfidence confidence={0.82} />)
      
      expect(screen.getByText('5/6')).toBeInTheDocument()
      expect(screen.getByText('Yüksek')).toBeInTheDocument()
      expect(screen.getByText('%82')).toBeInTheDocument()
    })
    
    it('maps confidence 1.0 to 6/6 "Çok yüksek"', () => {
      render(<AIConfidence confidence={1.0} />)
      
      expect(screen.getByText('6/6')).toBeInTheDocument()
      expect(screen.getByText('Çok yüksek')).toBeInTheDocument()
      expect(screen.getByText('%100')).toBeInTheDocument()
    })
  })
  
  describe('Confidence normalization (0-100 scale)', () => {
    it('maps confidence 82 (0-100 scale) to 5/6 "Yüksek"', () => {
      render(<AIConfidence confidence={82} />)
      
      expect(screen.getByText('5/6')).toBeInTheDocument()
      expect(screen.getByText('Yüksek')).toBeInTheDocument()
      expect(screen.getByText('%82')).toBeInTheDocument()
    })
    
    it('maps confidence 15 (0-100 scale) to 1/6 "Çok düşük"', () => {
      render(<AIConfidence confidence={15} />)
      
      expect(screen.getByText('1/6')).toBeInTheDocument()
      expect(screen.getByText('Çok düşük')).toBeInTheDocument()
      expect(screen.getByText('%15')).toBeInTheDocument()
    })
    
    it('maps confidence 100 (0-100 scale) to 6/6 "Çok yüksek"', () => {
      render(<AIConfidence confidence={100} />)
      
      expect(screen.getByText('6/6')).toBeInTheDocument()
      expect(screen.getByText('Çok yüksek')).toBeInTheDocument()
      expect(screen.getByText('%100')).toBeInTheDocument()
    })
  })
  
  describe('Boundary conditions', () => {
    it('maps confidence exactly 0.16 to 1/6', () => {
      render(<AIConfidence confidence={0.16} />)
      expect(screen.getByText('1/6')).toBeInTheDocument()
    })
    
    it('maps confidence exactly 0.33 to 2/6', () => {
      render(<AIConfidence confidence={0.33} />)
      expect(screen.getByText('2/6')).toBeInTheDocument()
    })
    
    it('maps confidence exactly 0.50 to 3/6', () => {
      render(<AIConfidence confidence={0.50} />)
      expect(screen.getByText('3/6')).toBeInTheDocument()
    })
    
    it('maps confidence exactly 0.67 to 4/6', () => {
      render(<AIConfidence confidence={0.67} />)
      expect(screen.getByText('4/6')).toBeInTheDocument()
    })
    
    it('maps confidence exactly 0.83 to 5/6', () => {
      render(<AIConfidence confidence={0.83} />)
      expect(screen.getByText('5/6')).toBeInTheDocument()
    })
    
    it('maps confidence above 0.83 to 6/6', () => {
      render(<AIConfidence confidence={0.84} />)
      expect(screen.getByText('6/6')).toBeInTheDocument()
    })
  })
  
  describe('Display options', () => {
    it('hides percentage when showPercentage is false', () => {
      render(<AIConfidence confidence={0.82} showPercentage={false} />)
      
      expect(screen.queryByText('%82')).not.toBeInTheDocument()
      expect(screen.getByText('5/6')).toBeInTheDocument()
    })
    
    it('hides level when showLevel is false', () => {
      render(<AIConfidence confidence={0.82} showLevel={false} />)
      
      expect(screen.queryByText('5/6')).not.toBeInTheDocument()
      expect(screen.getByText('Yüksek')).toBeInTheDocument()
    })
    
    it('hides label when showLabel is false', () => {
      render(<AIConfidence confidence={0.82} showLabel={false} />)
      
      expect(screen.queryByText('Yüksek')).not.toBeInTheDocument()
      expect(screen.getByText('5/6')).toBeInTheDocument()
    })
  })
  
  describe('Accessibility', () => {
    it('includes proper ARIA label with level and percentage', () => {
      render(<AIConfidence confidence={0.82} />)
      
      const component = screen.getByRole('status')
      expect(component).toHaveAttribute('aria-label', 'Yapay zeka güveni: Yüksek, 82%')
    })
    
    it('marks icons as aria-hidden', () => {
      const { container } = render(<AIConfidence confidence={0.82} />)
      
      const iconsContainer = container.querySelector('.ai-confidence__icons')
      expect(iconsContainer).toHaveAttribute('aria-hidden', 'true')
    })
  })
  
  describe('No hardcoded values', () => {
    it('dynamically calculates level from confidence prop', () => {
      const { rerender } = render(<AIConfidence confidence={0.3} />)
      expect(screen.getByText('2/6')).toBeInTheDocument()
      
      rerender(<AIConfidence confidence={0.7} />)
      expect(screen.getByText('5/6')).toBeInTheDocument()
      
      rerender(<AIConfidence confidence={0.9} />)
      expect(screen.getByText('6/6')).toBeInTheDocument()
    })
    
    it('renders correct number of active/inactive icons based on level', () => {
      const { container } = render(<AIConfidence confidence={0.82} />)
      
      const activeIcons = container.querySelectorAll('.ai-confidence__icon--active')
      const inactiveIcons = container.querySelectorAll('.ai-confidence__icon--inactive')
      
      expect(activeIcons).toHaveLength(5) // 5/6 confidence
      expect(inactiveIcons).toHaveLength(1) // 1 inactive
    })
  })
})
