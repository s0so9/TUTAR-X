/**
 * LiveStats Component Tests
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import LiveStats from '../LiveStats';
import type { LiveStats as LiveStatsType } from '../../../types/live';

describe('LiveStats', () => {
  const mockHomeStats: LiveStatsType = {
    possession: 60,
    xG: 1.8,
    shots: 12,
    shotsOnTarget: 6,
    corners: 5,
    fouls: 8,
    yellowCards: 2,
    passAccuracy: 85
  };

  const mockAwayStats: LiveStatsType = {
    possession: 40,
    xG: 0.9,
    shots: 8,
    shotsOnTarget: 3,
    corners: 2,
    fouls: 11,
    yellowCards: 3,
    passAccuracy: 78
  };

  it('renders statistics comparison', () => {
    render(
      <LiveStats
        homeTeam="Home Team"
        awayTeam="Away Team"
        homeStats={mockHomeStats}
        awayStats={mockAwayStats}
      />
    );

    expect(screen.getByText('Canlı İstatistikler')).toBeInTheDocument();
    expect(screen.getByText('Top Hakimiyeti')).toBeInTheDocument();
    expect(screen.getByText('Beklenen Gol (xG)')).toBeInTheDocument();
    expect(screen.getByText('Şutlar')).toBeInTheDocument();
  });

  it('displays possession percentages', () => {
    render(
      <LiveStats
        homeTeam="Home Team"
        awayTeam="Away Team"
        homeStats={mockHomeStats}
        awayStats={mockAwayStats}
      />
    );

    expect(screen.getByText('60%')).toBeInTheDocument();
    expect(screen.getByText('40%')).toBeInTheDocument();
  });

  it('displays xG with correct formatting', () => {
    render(
      <LiveStats
        homeTeam="Home Team"
        awayTeam="Away Team"
        homeStats={mockHomeStats}
        awayStats={mockAwayStats}
      />
    );

    expect(screen.getByText('1.80')).toBeInTheDocument();
    expect(screen.getByText('0.90')).toBeInTheDocument();
  });

  it('highlights leading team statistics', () => {
    const { container } = render(
      <LiveStats
        homeTeam="Home Team"
        awayTeam="Away Team"
        homeStats={mockHomeStats}
        awayStats={mockAwayStats}
      />
    );

    const leadElements = container.querySelectorAll('.stat-row__value--lead');
    expect(leadElements.length).toBeGreaterThan(0);
  });

  it('handles missing stats gracefully', () => {
    render(
      <LiveStats
        homeTeam="Home Team"
        awayTeam="Away Team"
        homeStats={{ possession: 55 }}
        awayStats={{ possession: 45 }}
      />
    );

    const emptyValues = screen.getAllByText('—');
    expect(emptyValues.length).toBeGreaterThan(0);
  });

  it('shows empty state when no stats available', () => {
    render(
      <LiveStats
        homeTeam="Home Team"
        awayTeam="Away Team"
        homeStats={undefined}
        awayStats={undefined}
      />
    );

    expect(screen.getByText('Canlı istatistikler henüz mevcut değil')).toBeInTheDocument();
  });

  it('shows loading state', () => {
    render(
      <LiveStats
        homeTeam="Home Team"
        awayTeam="Away Team"
        homeStats={mockHomeStats}
        awayStats={mockAwayStats}
        isLoading={true}
      />
    );

    const element = screen.getByRole('generic', { busy: true });
    expect(element).toBeInTheDocument();
  });
});
