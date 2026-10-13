/**
 * BookmakerValueList tests (sign of the value edge, Turkish labels, conflict badge).
 * Comparison rows below are TEST FIXTURES (mock data), not real odds.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import BookmakerValueList from '../BookmakerValueList';
import type { BookmakerComparisonResponse } from '../../../api/types';

function mockComparison(overrides: Partial<BookmakerComparisonResponse>): BookmakerComparisonResponse {
  return {
    label: 'Home',
    fair_probability: 0.5,
    fair_odds: 2,
    bookmaker_odds: 2,
    implied_probability: 0.5,
    edge_value: 0,
    has_value_flag: false,
    ...overrides,
  };
}

describe('BookmakerValueList', () => {
  it('shows a value outcome (negative edge_value) as positive value with a Turkish label', () => {
    const { container } = render(
      <BookmakerValueList
        comparisons={[
          // implied 0.40, model 0.443 -> backend edge_value -0.043 (value)
          mockComparison({ label: 'Draw', edge_value: -0.043, has_value_flag: true, value_classification: 'VALUE' }),
          mockComparison({ label: 'Home', edge_value: 0.066, has_value_flag: false }),
        ]}
      />
    );
    expect(screen.getByText('Beraberlik')).toBeInTheDocument();
    expect(screen.queryByText('Draw')).not.toBeInTheDocument();
    // Not flagged as value -> not listed
    expect(screen.queryByText('Ev')).not.toBeInTheDocument();
    expect(screen.getByText('+0.043')).toBeInTheDocument();
    expect(container.querySelector('.value-positive')).not.toBeNull();
    expect(container.querySelector('.value-negative')).toBeNull();
  });

  it('renders MODEL_MARKET_CONFLICT as a warning badge, never as value', () => {
    const { container } = render(
      <BookmakerValueList
        comparisons={[
          mockComparison({
            label: 'Away',
            edge_value: -0.12,
            has_value_flag: true,
            value_classification: 'MODEL_MARKET_CONFLICT',
          }),
        ]}
      />
    );
    expect(screen.getByText('Deplasman')).toBeInTheDocument();
    const badge = screen.getByText('Model–piyasa çelişkisi').closest('.tx-badge');
    expect(badge).not.toBeNull();
    expect(badge).toHaveClass('tx-badge--warning');
    expect(badge).not.toHaveClass('tx-badge--success');
    expect(badge).toHaveAttribute(
      'title',
      'Model olasılığı piyasadan 8 puandan fazla yüksek; değer değil, olası model hatası.'
    );
    expect(container.querySelector('.value-positive')).toBeNull();
    expect(screen.queryByText('+0.120')).not.toBeInTheDocument();
  });

  it('says "Değer yok" when no outcome is flagged', () => {
    render(<BookmakerValueList comparisons={[mockComparison({ edge_value: 0.05 })]} />);
    expect(screen.getByText('Değer yok')).toBeInTheDocument();
  });
});
