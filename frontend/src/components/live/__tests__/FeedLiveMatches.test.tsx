/**
 * FeedLiveMatches - Live page fallback that lists LIVE matches from the match feed.
 * All match data below is test fixture data, not real football data.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { MatchResponse } from '../../../api/types';
import * as apiClient from '../../../api/client';
import FeedLiveMatches from '../FeedLiveMatches';

vi.mock('../../../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/client')>();
  return { ...actual, getMatches: vi.fn() };
});

function fixtureMatch(id: string, status: MatchResponse['status'], home: string, away: string): MatchResponse {
  return {
    id,
    competition_id: 'test_comp',
    competition_name: 'Test Fixture League',
    season_id: 'test_season',
    home_team_id: `${id}_h`,
    away_team_id: `${id}_a`,
    home_team: { id: `${id}_h`, name: home, short_name: null, code: null, logo_url: null },
    away_team: { id: `${id}_a`, name: away, short_name: null, code: null, logo_url: null },
    scheduled_at: '2026-10-13T19:00:00Z',
    status,
    home_score: status === 'SCHEDULED' ? 0 : 1,
    away_score: 0,
    minute: null,
  } as unknown as MatchResponse;
}

function renderFeed() {
  return render(
    <MemoryRouter>
      <FeedLiveMatches />
    </MemoryRouter>
  );
}

describe('FeedLiveMatches', () => {
  beforeEach(() => {
    vi.mocked(apiClient.getMatches).mockReset();
  });

  it('shows only LIVE matches from the feed, with a note about the source', async () => {
    vi.mocked(apiClient.getMatches).mockResolvedValue({
      matches: [
        fixtureMatch('test_live_1', 'LIVE', 'Fixture Live Home', 'Fixture Live Away'),
        fixtureMatch('test_sched_1', 'SCHEDULED', 'Fixture Later Home', 'Fixture Later Away'),
        fixtureMatch('test_done_1', 'FINISHED', 'Fixture Done Home', 'Fixture Done Away'),
      ],
      count: 3,
      is_development_data: false,
    });

    renderFeed();

    expect(await screen.findByText('Fixture Live Home')).toBeInTheDocument();
    expect(screen.queryByText('Fixture Later Home')).not.toBeInTheDocument();
    expect(screen.queryByText('Fixture Done Home')).not.toBeInTheDocument();
    expect(screen.getByText(/genel\s+maç listesinden alınmıştır/)).toBeInTheDocument();
  });

  it('says there is no live match when the feed has none', async () => {
    vi.mocked(apiClient.getMatches).mockResolvedValue({
      matches: [fixtureMatch('test_sched_2', 'SCHEDULED', 'Fixture A', 'Fixture B')],
      count: 1,
      is_development_data: false,
    });

    renderFeed();

    expect(await screen.findByText('Şu anda canlı maç bulunmuyor')).toBeInTheDocument();
  });
});
