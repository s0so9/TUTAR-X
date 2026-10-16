/**
 * PropsPanel tests. The props payload is a TEST FIXTURE (mock data), not real football data.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PropsPanel } from '../PropsPanel';
import type { PropsResponse } from '../../../api/props';

const MOCK: PropsResponse = {
  match_id: 'fotmob_0',
  model_version: 'props_test_fixture',
  trained_through: '2026-10-12T00:00:00Z',
  home_team: 'Mock Ev',
  away_team: 'Mock Dep',
  competition_id: '42',
  referee: 'Mock Hakem',
  referee_used: true,
  unknown_teams: [],
  markets: [
    { key: 'team_yellow_cards', label_tr: 'Mock Ev sarı kart', group: 'Kartlar', scope: 'home', expected: 1.9,
      lines: [{ line: 0.5, over: 0.82, under: 0.18 }, { line: 1.5, over: 0.55, under: 0.45 }, { line: 2.5, over: 0.28, under: 0.72 }] },
    { key: 'team_yellow_cards', label_tr: 'Mock Dep sarı kart', group: 'Kartlar', scope: 'away', expected: 2.2,
      lines: [{ line: 1.5, over: 0.62, under: 0.38 }] },
    { key: 'total_yellow_cards', label_tr: 'Toplam sarı kart', group: 'Kartlar', scope: 'total', expected: 4.1,
      lines: [{ line: 3.5, over: 0.58, under: 0.42 }, { line: 5.5, over: 0.2, under: 0.8 }] },
  ],
  recent: {
    home: [{ stat: 'yellow_cards', label_tr: 'Sarı kart', for_last5: 2.0, against_last5: 1.6, n: 5 }],
    away: [{ stat: 'yellow_cards', label_tr: 'Sarı kart', for_last5: null, against_last5: null, n: null }],
  },
  note: 'Test notu.',
};

describe('PropsPanel', () => {
  it('shows expected counts per team and in total', () => {
    render(<PropsPanel data={MOCK} />);
    expect(screen.getByText('Sarı kart')).toBeTruthy();
    expect(screen.getByText('4.1')).toBeTruthy();
    expect(screen.getByText('1.9')).toBeTruthy();
    expect(screen.getByText('2.2')).toBeTruthy();
  });

  it('shows the coin-flip line and the strong lines', () => {
    render(<PropsPanel data={MOCK} />);
    expect(screen.getByTitle('3.5 Alt %42 · Üst %58').textContent).toContain('3.5 Üst');
    expect(screen.getByTitle('5.5 Alt %80 · Üst %20').textContent).toContain('5.5 Alt');
  });

  it('says "veri yok" for missing recent averages instead of 0', () => {
    render(<PropsPanel data={MOCK} />);
    expect(screen.getAllByText(/veri yok/).length).toBeGreaterThan(0);
  });

  it('mentions the referee', () => {
    render(<PropsPanel data={MOCK} />);
    expect(screen.getByText(/Hakem: Mock Hakem/)).toBeTruthy();
  });
});
