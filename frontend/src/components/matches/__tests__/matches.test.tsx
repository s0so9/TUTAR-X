/**
 * Match list component tests (DateStrip, LeagueGroup, MatchRow).
 * All match data below is test fixture data, not real football data.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { userEvent } from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { DateStrip, LeagueGroup, MatchRow, toMatchRowData } from '..';
import type { MatchRowData } from '..';
import type { MatchResponse } from '../../../api/types';
import { formatDateForAPI } from '../../../api/client';

function fixtureRow(overrides: Partial<MatchRowData> = {}): MatchRowData {
  return {
    id: 'test_match_1',
    homeTeam: { name: 'Test Home FC', logoUrl: null, code: null },
    awayTeam: { name: 'Test Away FC', logoUrl: null, code: null },
    scheduledAt: '2026-10-13T19:00:00Z',
    status: 'SCHEDULED',
    homeScore: null,
    awayScore: null,
    minute: null,
    ...overrides,
  };
}

function renderInRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe('MatchRow', () => {
  it('renders one row link: home | kickoff | away, no logo placeholders', () => {
    renderInRouter(
      <ul>
        <MatchRow
          match={fixtureRow({
            homeTeam: { name: 'Fixture Town (W)', logoUrl: null, code: null },
            awayTeam: { name: 'Test Away FC', logoUrl: null, code: null },
          })}
        />
      </ul>
    );
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute('href', '/matches/test_match_1');
    expect(links[0]).toHaveAccessibleName(/Fixture Town \(W\) - Test Away FC/);
    expect(screen.getByText('Fixture Town (W)')).toBeInTheDocument();
    expect(screen.getByText('Test Away FC')).toBeInTheDocument();
    expect(screen.queryByText('FTW')).not.toBeInTheDocument();
  });

  it('never shows a score for scheduled matches, even with 0-0 placeholders', () => {
    renderInRouter(
      <ul>
        <MatchRow match={fixtureRow({ homeScore: 0, awayScore: 0 })} />
      </ul>
    );
    expect(screen.queryByText(/0\s*-\s*0/)).not.toBeInTheDocument();
    // Kickoff time is shown in Europe/Istanbul time (19:00Z -> 22:00)
    expect(screen.getByText('22:00')).toBeInTheDocument();
  });

  it('shows the real score for finished matches', () => {
    renderInRouter(
      <ul>
        <MatchRow match={fixtureRow({ status: 'FINISHED', homeScore: 2, awayScore: 1 })} />
      </ul>
    );
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/matches/test_match_1');
    expect(link).toHaveAccessibleName(/skor 2 - 1/);
    expect(screen.getByText('MS')).toBeInTheDocument();
  });

  it('toggles favorites through a real button', async () => {
    const onToggle = vi.fn();
    renderInRouter(
      <ul>
        <MatchRow match={fixtureRow()} isFavorite={false} onToggleFavorite={onToggle} />
      </ul>
    );
    await userEvent.click(screen.getByRole('button', { name: /favorilere ekle/i }));
    expect(onToggle).toHaveBeenCalledWith('test_match_1');
  });
});

describe('LeagueGroup', () => {
  it('collapses and expands its match list', async () => {
    renderInRouter(
      <LeagueGroup leagueName="Test League" matches={[fixtureRow()]} defaultExpanded={true} />
    );
    const toggle = screen.getByRole('button', { name: /Test League/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('link')).toBeVisible();

    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});

describe('DateStrip', () => {
  it('marks today as selected and reports clicked dates as YYYY-MM-DD', async () => {
    const onDateChange = vi.fn();
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(today.getDate() + 1);

    render(<DateStrip selectedDate={formatDateForAPI(today)} onDateChange={onDateChange} />);

    const pressed = screen.getAllByRole('button', { pressed: true });
    expect(pressed).toHaveLength(1);
    expect(pressed[0]).toHaveTextContent('Bugün');

    await userEvent.click(screen.getByText('Yarın'));
    expect(onDateChange).toHaveBeenCalledWith(formatDateForAPI(tomorrow));
  });
});

describe('toMatchRowData', () => {
  it('uses the normalizer fallback instead of raw IDs for missing team names', () => {
    const match = {
      id: 'test_match_2',
      competition_id: '42',
      competition_name: 'Test Cup',
      season_id: 's',
      home_team_id: '4e7aafe3-56e6-4bf2-a212-7f1275ab36e8',
      away_team_id: 'away',
      venue_id: null,
      home_team: null,
      away_team: { id: 'away', name: 'Test Away', short_name: null, code: null, logo_url: null },
      scheduled_at: '2026-10-13T19:00:00Z',
      status: 'SCHEDULED',
      home_score: 0,
      away_score: 0,
      home_score_ht: null,
      away_score_ht: null,
      home_statistics: null,
      away_statistics: null,
      home_statistics_ht: null,
      away_statistics_ht: null,
      minute: null,
      added_time: null,
      outcome: null,
      round: null,
      created_at: null,
      updated_at: null,
    } satisfies MatchResponse;

    const row = toMatchRowData(match);
    expect(row.homeTeam.name).toBe('Takım bilgisi yok');
    expect(row.awayTeam.name).toBe('Test Away');
    expect(row.competitionName).toBe('Test Cup');
  });
});
