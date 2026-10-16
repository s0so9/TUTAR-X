/**
 * MatchPreview ("Maç analizi") tests. The payload below is a TEST FIXTURE (synthetic
 * "Mock Ev" / "Mock Dep" teams with made-up results), not real football data.
 */

import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MatchPreview } from '../MatchPreview';
import type { FormWindow, MatchPreviewResponse, PreviewMatch, PreviewSide } from '../../../api/matchPreview';

function match(day: number, venue: 'home' | 'away', gf: number, ga: number, opts: Partial<PreviewMatch> = {}): PreviewMatch {
  return {
    match_id: String(9000 + day),
    date: `2026-10-${String(day).padStart(2, '0')}T18:45:00Z`,
    competition: 'Mock Lig (test verisi)',
    is_friendly: false,
    venue,
    opponent: `Mock Rakip ${day}`,
    opponent_id: String(100 + day),
    goals_for: gf,
    goals_against: ga,
    result: gf > ga ? 'G' : gf < ga ? 'M' : 'B',
    xg_for: null,
    xg_against: null,
    source: 'database',
    ...opts,
  };
}

function window(scope: FormWindow['scope'], matches: PreviewMatch[], extra: Partial<FormWindow> = {}): FormWindow {
  const wins = matches.filter((m) => m.result === 'G').length;
  const draws = matches.filter((m) => m.result === 'B').length;
  return {
    scope,
    venue: scope === 'last5_venue' ? matches[0]?.venue ?? null : null,
    played: matches.length,
    results: matches.length ? matches.map((m) => m.result).join('') : null,
    wins: matches.length ? wins : null,
    draws: matches.length ? draws : null,
    losses: matches.length ? matches.length - wins - draws : null,
    goals_for: matches.length ? matches.reduce((s, m) => s + (m.goals_for ?? 0), 0) : null,
    goals_against: matches.length ? matches.reduce((s, m) => s + (m.goals_against ?? 0), 0) : null,
    xg_for: null,
    xg_against: null,
    xg_matches: 0,
    xg_missing_reason: matches.length ? 'Bu maçlar için xG verisi yok.' : 'Maç kaydı olmadığı için xG yok.',
    matches,
    missing_reason: matches.length ? null : 'Bu takım için kayıtlı maç bulunamadı.',
    ...extra,
  };
}

const emptyRotation = { previous_match: null, previous_xi_source: null, changes: null, came_in: [], dropped_out: [], missing_reason: null };

function side(name: string, overrides: Partial<PreviewSide> = {}): PreviewSide {
  const five = [match(11, 'home', 0, 2), match(8, 'away', 1, 3), match(4, 'home', 1, 2), match(1, 'away', 2, 2), match(1, 'home', 3, 1)];
  return {
    team_id: name,
    team_name: name,
    last5: window('last5', five, { xg_for: 7.64, xg_against: 6.2, xg_matches: 4, xg_missing_reason: 'xG yalnızca 4/5 maçta var.' }),
    venue_last5: window('last5_venue', five.filter((m) => m.venue === 'home')),
    rest: { previous_match: five[0], rest_days: 4, matches_last_14_days: 3, missing_reason: null },
    absentees: {
      available: true,
      players: [
        { id: '1', name: 'Mock Oyuncu A', reason: 'Sakatlık', reason_code: 'injury', expected_return: 'Late October 2026', expected_return_date: null, started_previous_match: true },
        { id: '2', name: 'Mock Oyuncu B', reason: 'Cezalı', reason_code: 'suspension', expected_return: null, expected_return_date: null, started_previous_match: false },
      ],
      missing_reason: null,
    },
    lineup: {
      lineup_type: 'confirmed',
      formation: '4-3-3',
      starters_count: 11,
      rotation: { ...emptyRotation, changes: 5, came_in: [{ id: 'n1', name: 'Mock Giren' }], dropped_out: [{ id: 'p1', name: 'Mock Çıkan' }] },
      missing_reason: null,
    },
    history_verified: true,
    data_notes: [],
    ...overrides,
  };
}

const MOCK: MatchPreviewResponse = {
  match_id: 'fotmob_0',
  provider_match_id: '0',
  generated_at: '2026-10-15T08:00:00Z',
  kickoff: '2026-10-15T19:00:00Z',
  status: 'SCHEDULED',
  competition: 'Mock Lig (test verisi)',
  home: side('Mock Ev'),
  away: side('Mock Dep', {
    lineup: { lineup_type: 'last_starting11', formation: '4-4-2', starters_count: 11, rotation: { ...emptyRotation, missing_reason: 'Kadro henüz açıklanmadı.' }, missing_reason: 'FotMob henüz kadro vermedi.' },
  }),
  highlights: [
    { id: 'rotation_home', kind: 'rotation', side: 'home', text: 'Mock Ev geçen maça göre 5 değişiklikle sahada.', importance: 71, facts: { changes: 5 } },
    { id: 'rest_both', kind: 'rest', side: 'both', text: 'Mock Ev 3 gün dinlendi, Mock Dep 4 gün.', importance: 65, facts: {} },
  ],
  database_latest_match_at: '2026-10-14T23:30:00Z',
  sources: ['Maç sonuçları ve xG: yerel veritabanı (FotMob verisi).'],
  notes: [],
};

describe('MatchPreview', () => {
  it('lists the highlight sentences first', () => {
    render(<MatchPreview data={MOCK} state="ready" />);
    expect(screen.getByText('Mock Ev geçen maça göre 5 değişiklikle sahada.')).toBeTruthy();
    expect(screen.getByText('Mock Ev 3 gün dinlendi, Mock Dep 4 gün.')).toBeTruthy();
    const list = screen.getAllByRole('listitem').filter((li) => li.className.includes('preview__highlight'));
    expect(list).toHaveLength(2);
  });

  it('shows the form letters, goals, xG, rest and line-up in a home | away table', () => {
    render(<MatchPreview data={MOCK} state="ready" />);
    const table = screen.getByRole('table', { name: /karşılaştırma/ });
    // team headers
    expect(within(table).getByText('Mock Ev')).toBeTruthy();
    expect(within(table).getByText('Mock Dep')).toBeTruthy();
    // last 5: M M M B G in the table cells (twice: both sides use the same fixture), goals 7–10
    expect(within(table).getAllByLabelText(/Sonuçlar, en yeniden eskiye: M M M B G/).length).toBe(2);
    expect(within(table).getAllByText('7–10').length).toBe(2);
    // xG with its count and Turkish decimal comma
    expect(within(table).getAllByText('7,6 – 6,2').length).toBe(2);
    expect(within(table).getAllByText('4/5 maçta xG var').length).toBe(2);
    // rest
    expect(within(table).getAllByText('4 gün').length).toBe(2);
    expect(within(table).getAllByText('son 14 günde 3 maç').length).toBe(2);
    // line-up: confirmed with formation and rotation count for the home side
    expect(within(table).getByText('Açıklandı')).toBeTruthy();
    expect(within(table).getByText('(geçen maça göre)')).toBeTruthy();
  });

  it('names absentees with the reason and return date, and tags last match starters', () => {
    render(<MatchPreview data={MOCK} state="ready" />);
    expect(screen.getAllByText('Mock Oyuncu A').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Sakatlık · Ekim 2026 sonu/).length).toBeGreaterThan(0); // FotMob text translated, not invented
    expect(screen.getAllByText(/Cezalı/).length).toBeGreaterThan(0);
    expect(screen.getAllByTitle("Önceki maçta ilk 11'deydi").length).toBeGreaterThan(0);
  });

  it('says "veri yok" instead of 0 for missing rest, xG and rotation', () => {
    const nothing = side('Mock Boş', {
      last5: window('last5', []),
      venue_last5: window('last5_venue', []),
      rest: { previous_match: null, rest_days: null, matches_last_14_days: null, missing_reason: 'Önceki maç kaydı bulunamadı.' },
      absentees: { available: false, players: [], missing_reason: 'FotMob bu maç için kadro ve eksik oyuncu verisi göndermedi.' },
      lineup: { lineup_type: null, formation: null, starters_count: 0, rotation: { ...emptyRotation, missing_reason: 'Kadro henüz açıklanmadı.' }, missing_reason: 'Kadro henüz açıklanmadı.' },
    });
    render(<MatchPreview data={{ ...MOCK, away: nothing, highlights: [] }} state="ready" />);
    const table = screen.getByRole('table', { name: /karşılaştırma/ });
    const awayCells = within(table)
      .getAllByRole('row')
      .slice(1)
      .map((row) => within(row).getAllByRole('cell')[1]);
    // last5, venue, xg, rest, absent: "veri yok"; lineup: the reason
    for (const cell of awayCells.slice(0, 5)) expect(cell.textContent).toContain('veri yok');
    expect(awayCells[3].textContent).toContain('Önceki maç kaydı bulunamadı.');
    expect(awayCells[5].textContent).toContain('Kadro henüz açıklanmadı.');
    expect(awayCells.some((c) => /(^|\s)0\s*gün/.test(c.textContent ?? ''))).toBe(false);
    // no highlight at all: says so instead of an empty list
    expect(screen.getByText(/Öne çıkan bir bulgu yok/)).toBeTruthy();
  });

  it('shows "kadro açıklanmadı" and no rotation figure for the last starting XI', () => {
    render(<MatchPreview data={MOCK} state="ready" />);
    expect(screen.getByText('Kadro açıklanmadı')).toBeTruthy();
    expect(screen.getByText('değişiklik sayısı kadro açıklanınca')).toBeTruthy();
  });

  it('shows the reason when the history could not be verified', () => {
    const reason = 'Yerel veritabanı en son 12.10.2026 maçlarına kadar; sonraki maçlar eksik olabilir ve FotMob\'dan doğrulanamadı (FotMob yanıt vermedi).';
    const unverified = side('Mock Ev', {
      history_verified: false,
      rest: { previous_match: null, rest_days: null, matches_last_14_days: null, missing_reason: reason },
      data_notes: [reason],
    });
    render(<MatchPreview data={{ ...MOCK, home: unverified }} state="ready" />);
    expect(screen.getAllByText(reason).length).toBeGreaterThan(0);
  });

  it('marks matches filled in from the FotMob team page (score only)', () => {
    const filled = match(13, 'home', 2, 1, { source: 'fotmob_team_fixtures' });
    const home = side('Mock Ev', { last5: window('last5', [filled, match(8, 'away', 1, 0)]) });
    render(<MatchPreview data={{ ...MOCK, home }} state="ready" />);
    expect(screen.getByText(/FotMob takım sayfası, xG yok/)).toBeTruthy();
  });

  it('renders loading and unavailable states without inventing content', () => {
    const { rerender } = render(<MatchPreview data={null} state="loading" />);
    expect(screen.getByText('Maç analizi hazırlanıyor')).toBeTruthy();
    rerender(<MatchPreview data={null} state="unavailable" />);
    expect(screen.getByText('Maç analizi şu an alınamadı.')).toBeTruthy();
    rerender(<MatchPreview data={null} state="idle" />);
    expect(screen.queryByText(/Maç analizi/)).toBeNull();
  });
});
