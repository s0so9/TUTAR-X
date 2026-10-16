/**
 * Live match centre tests. All match data comes from the labelled TEST FIXTURE
 * (__fixtures__/liveCenterFixture.ts) — mock data, not real football data.
 */

import { describe, it, expect } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { LiveCenter } from '../LiveCenter';
import { LiveScoreHead } from '../LiveScoreHead';
import { groupStats, missingReason, sortEvents, STAT_GROUP_ORDER } from '../liveCenterModel';
import { makeTestLiveCenter, makeTestPreMatch } from '../__fixtures__/liveCenterFixture';
import {
  HALF_TIME_POLL_MS,
  LIVE_POLL_MS,
  PRE_MATCH_FAR_POLL_MS,
  PRE_MATCH_NEAR_POLL_MS,
  pollIntervalFor,
} from '../../../../hooks/useLiveCenter';

const TEAMS = { home: 'Test Ev FK', away: 'Test Deplasman SK' };

function renderCentre(data = makeTestLiveCenter()) {
  return render(
    <LiveCenter
      data={data}
      state="ready"
      error={null}
      lastUpdated={null}
      pollIntervalMs={LIVE_POLL_MS}
      paused={false}
      onRefresh={() => {}}
      teams={TEAMS}
    />,
  );
}

describe('pollIntervalFor', () => {
  const now = Date.parse('2026-10-14T18:00:00Z');
  it('polls fast while the ball is rolling and slower at half-time', () => {
    expect(pollIntervalFor('LIVE', null, now)).toBe(LIVE_POLL_MS);
    expect(pollIntervalFor('HALF_TIME', null, now)).toBe(HALF_TIME_POLL_MS);
  });
  it('stops after full time', () => {
    expect(pollIntervalFor('FINISHED', null, now)).toBeNull();
  });
  it('polls more often close to kick-off', () => {
    expect(pollIntervalFor('SCHEDULED', '2026-10-14T18:10:00Z', now)).toBe(PRE_MATCH_NEAR_POLL_MS);
    expect(pollIntervalFor('SCHEDULED', '2026-10-14T21:00:00Z', now)).toBe(PRE_MATCH_FAR_POLL_MS);
  });
});

describe('liveCenterModel', () => {
  it('orders events chronologically with the half-time marker after first-half stoppage time', () => {
    const ids = sortEvents(makeTestLiveCenter().events).map((e) => e.id);
    expect(ids).toEqual(['e-goal-12', 'e-yc-30', 'e-yc-45', 'e-ht', 'e-goal-52', 'e-2y-58', 'e-var-60', 'e-pen-60', 'e-sub-61']);
  });

  it('groups stats in the fixed group order', () => {
    const groups = groupStats(makeTestLiveCenter().stats?.all).map((g) => g.group);
    const order = STAT_GROUP_ORDER.filter((g) => groups.includes(g));
    expect(groups).toEqual(order);
  });

  it('prefers the Turkish message, then a known code, then the raw reason', () => {
    expect(
      missingReason({ missing: [{ section: 'shotmap', reason: 'shotmap_not_covered', message_tr: 'Özel açıklama' }] }, 'shotmap'),
    ).toBe('Özel açıklama');
    expect(missingReason({ missing: [{ section: 'stats', reason: 'not_started' }] }, 'stats')).toBe('Maç henüz başlamadı.');
    expect(missingReason({ missing: [{ section: 'stats.halves', reason: 'half_stats_not_provided' }] }, 'second_half')).toBe(
      'Kaynak devre bazlı istatistik göndermedi.',
    );
    expect(missingReason({ missing: [] }, 'stats')).toBeNull();
  });
});

describe('LiveCenter', () => {
  it('shows the four live tabs and switches to statistics', () => {
    renderCentre();
    for (const name of ['Özet', 'Kadrolar', 'İstatistikler', 'Şut haritası']) {
      expect(screen.getByRole('tab', { name })).toBeTruthy();
    }
    fireEvent.click(screen.getByRole('tab', { name: 'İstatistikler' }));
    expect(screen.getByRole('tab', { name: 'İstatistikler' }).getAttribute('aria-selected')).toBe('true');
  });

  it('lists the goal scorer in the timeline', () => {
    renderCentre();
    expect(screen.getAllByText(/Ev Forvet Bir/).length).toBeGreaterThan(0);
  });

  it('before kick-off shows only the line-ups, never a score', () => {
    renderCentre(makeTestPreMatch());
    expect(screen.queryByRole('tab', { name: 'Özet' })).toBeNull();
    expect(screen.getByRole('heading', { name: 'Kadrolar' })).toBeTruthy();
  });

  it('hides the shotmap tab when the source sent no shots', () => {
    renderCentre(makeTestLiveCenter({ shotmap: null }));
    expect(screen.queryByRole('tab', { name: 'Şut haritası' })).toBeNull();
  });
});

describe('LiveScoreHead', () => {
  it('shows score, minute and half-time score', () => {
    render(<LiveScoreHead data={makeTestLiveCenter()} />);
    expect(screen.getByLabelText(/Skor 2.1/)).toBeTruthy();
    expect(screen.getByText(/67/)).toBeTruthy();
    expect(screen.getByTitle('İlk yarı skoru').textContent).toContain('1');
  });

  it('says "veri yok" instead of 0-0 when the score is unknown', () => {
    render(<LiveScoreHead data={makeTestLiveCenter({ score: { home: null, away: null } })} />);
    expect(screen.getByText(/veri yok/)).toBeTruthy();
  });
});
