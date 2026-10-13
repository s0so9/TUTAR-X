/**
 * LiveScoreboard Component Tests
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import LiveScoreboard from '../LiveScoreboard';
import type { MatchPeriod } from '../../../types/live';

describe('LiveScoreboard', () => {
  const mockHomeTeam = {
    id: 'home-1',
    name: 'Home Team',
    code: 'HOM'
  };

  const mockAwayTeam = {
    id: 'away-1',
    name: 'Away Team',
    code: 'AWY'
  };

  it('renders team names and scores', () => {
    render(
      <LiveScoreboard
        homeTeam={mockHomeTeam}
        awayTeam={mockAwayTeam}
        homeScore={2}
        awayScore={1}
        minute={45}
        period={'FIRST_HALF' as MatchPeriod}
      />
    );

    expect(screen.getByText('Home Team')).toBeInTheDocument();
    expect(screen.getByText('Away Team')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('displays match minute correctly', () => {
    render(
      <LiveScoreboard
        homeTeam={mockHomeTeam}
        awayTeam={mockAwayTeam}
        homeScore={1}
        awayScore={1}
        minute={67}
        period={'SECOND_HALF' as MatchPeriod}
      />
    );

    expect(screen.getByText("67'")).toBeInTheDocument();
  });

  it('displays added time correctly', () => {
    render(
      <LiveScoreboard
        homeTeam={mockHomeTeam}
        awayTeam={mockAwayTeam}
        homeScore={0}
        awayScore={0}
        minute={45}
        addedTime={3}
        period={'FIRST_HALF' as MatchPeriod}
      />
    );

    expect(screen.getByText("45+3'")).toBeInTheDocument();
  });

  it('displays period label in Turkish', () => {
    render(
      <LiveScoreboard
        homeTeam={mockHomeTeam}
        awayTeam={mockAwayTeam}
        homeScore={1}
        awayScore={0}
        minute={10}
        period={'FIRST_HALF' as MatchPeriod}
      />
    );

    expect(screen.getByText('1. Yarı')).toBeInTheDocument();
  });

  it('handles missing data gracefully', () => {
    render(
      <LiveScoreboard
        homeTeam={undefined}
        awayTeam={undefined}
        homeScore={0}
        awayScore={0}
      />
    );

    expect(screen.getByText('Ev Sahibi')).toBeInTheDocument();
    expect(screen.getByText('Deplasman')).toBeInTheDocument();
    // Check for "—" period placeholder
    const periodPlaceholders = screen.getAllByText('—');
    expect(periodPlaceholders.length).toBeGreaterThan(0);
  });

  it('shows loading state', () => {
    render(
      <LiveScoreboard
        homeTeam={mockHomeTeam}
        awayTeam={mockAwayTeam}
        homeScore={0}
        awayScore={0}
        isLoading={true}
      />
    );

    const element = screen.getByRole('generic', { busy: true });
    expect(element).toBeInTheDocument();
  });
});
