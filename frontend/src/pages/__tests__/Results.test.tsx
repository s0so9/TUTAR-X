/**
 * Sonuçlar page. The track record below is a TEST FIXTURE (made-up teams, probabilities and
 * results), never football data.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import { userEvent } from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { Results } from '../Results';
import { apiClient } from '../../api/client';
import type { HeadlinePickItem, HeadlineTrackRecord, KindSummary } from '../../api/headlineRecord';

vi.mock('../../api/client', () => ({ apiClient: { get: vi.fn() } }));

const apiGet = apiClient.get as unknown as ReturnType<typeof vi.fn>;

/** apiClient.get(url, signal) -> { json() }: every call answers with `data` (or fails). */
function respondWith(data: HeadlineTrackRecord | Error, times = Infinity) {
  const impl = () => ({ json: () => (data instanceof Error ? Promise.reject(data) : Promise.resolve(data)) });
  if (times === Infinity) apiGet.mockImplementation(impl);
  else apiGet.mockImplementationOnce(impl);
}

function summary(over: Partial<KindSummary> = {}): KindSummary {
  return { won: 0, lost: 0, void: 0, pending: 0, settled: 0, hit_rate: null, ...over };
}

function pick(over: Partial<HeadlinePickItem>): HeadlinePickItem {
  return {
    id: 'p',
    match_id: 'fotmob_1',
    kind: 'banko',
    stage: 'headline_banko',
    home_team: 'Mock Ev',
    away_team: 'Mock Dep',
    competition_id: '42',
    competition_name: 'Mock Kupa',
    kickoff_at: '2026-10-14T19:00:00Z',
    frozen_at: '2026-10-14T18:40:00Z',
    minutes_before_kickoff: 20,
    market_key: 'HOME_OR_DRAW',
    label: '1X',
    selection_text: '1X (Mock Ev veya beraberlik)',
    market_name: 'Çifte Şans',
    probability: 0.81,
    fair_odds: 1.23,
    odds: null,
    lineup_type: { home: 'confirmed', away: 'confirmed', source: 'test' },
    model_1x2: { home: 0.59, draw: 0.22, away: 0.19 },
    result: 'won',
    final_score: { home: 2, away: 1, extra_time: false },
    settled_at: '2026-10-14T21:00:00Z',
    source: 'live_freeze',
    rule_version: 'headline_v1',
    ...over,
  };
}

const FIXTURE: HeadlineTrackRecord = {
  generated_at: '2026-10-15T09:00:00Z',
  days: 30,
  competition_id: null,
  rule_version: 'headline_v2',
  current_rule_version: 'headline_v2',
  available_rule_versions: ['headline_v1', 'headline_v2'],
  summary: {
    banko: summary({ won: 1, lost: 1, settled: 2, hit_rate: 0.5, pending: 1 }),
    oranli: summary({ won: 1, settled: 1, hit_rate: 1, void: 1 }),
    // p >= 0.85 only: 0.91 won, 0.86 lost (not the güçlü 0.81)
    banko_strong: summary({ won: 1, lost: 1, settled: 2, hit_rate: 0.5 }),
  },
  // the three Banko picks below: 0.91 won, 0.86 lost, 0.81 pending
  banko_tiers: {
    cok_guclu: summary({ won: 1, settled: 1, hit_rate: 1 }),
    banko: summary({ lost: 1, settled: 1, hit_rate: 0 }),
    guclu: summary({ pending: 1 }),
  },
  banko_progress: {
    ...summary({ won: 1, lost: 1, settled: 2, hit_rate: 0.5, pending: 3 }),
    rule_version: 'headline_v2',
    min_probability: 0.85,
    target: 300,
  },
  by_competition: [
    { competition_id: '42', competition_name: 'Mock Kupa', total: 4, banko: summary({ won: 1, lost: 1, settled: 2, hit_rate: 0.5 }), oranli: summary({ won: 1, settled: 1, hit_rate: 1 }), banko_strong: summary({ won: 1, lost: 1, settled: 2, hit_rate: 0.5 }) },
    { competition_id: '73', competition_name: 'Mock Lig', total: 2, banko: summary(), oranli: summary(), banko_strong: summary() },
  ],
  by_week: [
    { week_start: '2026-10-12', banko: summary({ won: 1, lost: 1, settled: 2, hit_rate: 0.5 }), oranli: summary({ won: 1, settled: 1, hit_rate: 1 }), banko_strong: summary({ won: 1, lost: 1, settled: 2, hit_rate: 0.5 }) },
    { week_start: '2026-10-05', banko: summary(), oranli: summary(), banko_strong: summary() },
  ],
  available_competitions: [
    { id: '42', name: 'Mock Kupa' },
    { id: '73', name: 'Mock Lig' },
  ],
  picks: [
    pick({ id: 'a', match_id: 'fotmob_1', kind: 'banko', probability: 0.91, tier: 'cok_guclu' }),
    pick({ id: 'b', match_id: 'fotmob_1', kind: 'oranli', stage: 'headline_oranli', market_key: 'OVER_2_5', label: '2.5 Üst', probability: 0.58, result: 'won' }),
    pick({ id: 'c', match_id: 'fotmob_2', home_team: 'Mock A', away_team: 'Mock B', kickoff_at: '2026-10-14T16:45:00Z', kind: 'banko', market_key: 'OVER_1_5', label: '1.5 Üst', probability: 0.86, tier: 'banko', result: 'lost', final_score: { home: 1, away: 0, extra_time: false }, lineup_type: { home: 'predicted', away: 'predicted', source: 'test' } }),
    pick({ id: 'd', match_id: 'fotmob_2', kind: 'oranli', stage: 'headline_oranli', kickoff_at: '2026-10-14T16:45:00Z', home_team: 'Mock A', away_team: 'Mock B', market_key: 'BTTS_YES', label: 'KG Var', probability: 0.5, result: 'void', final_score: null }),
    pick({ id: 'e', match_id: 'fotmob_3', home_team: 'Mock C', away_team: 'Mock D', kickoff_at: '2026-10-16T19:00:00Z', kind: 'banko', tier: 'guclu', result: null, final_score: null, source: 'manual_record_2026-10-14' }),
  ],
  note: 'fixture',
};

const EMPTY: HeadlineTrackRecord = {
  ...FIXTURE,
  summary: { banko: summary(), oranli: summary(), banko_strong: summary() },
  banko_tiers: { cok_guclu: summary(), banko: summary(), guclu: summary() },
  banko_progress: { ...summary(), rule_version: 'headline_v2', min_probability: 0.85, target: 300 },
  by_competition: [],
  by_week: [],
  available_competitions: [],
  picks: [],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <Results />
    </MemoryRouter>,
  );
}

/** The list of picks (the tier table comes before it). */
async function picksTable() {
  return within(await screen.findByRole('region', { name: 'Son seçimler' })).getByRole('table');
}

const CURRENT = '/track-record/headline?days=30&rule_version=headline_v2';

beforeEach(() => {
  apiGet.mockReset();
});

describe('Results page', () => {
  it('shows the two hit rates with their counts', async () => {
    respondWith(FIXTURE);
    renderPage();
    const banko = await screen.findByRole('group', { name: 'Banko başarı oranı' });
    expect(within(banko).getByText('%50')).toBeTruthy();
    expect(within(banko).getByText('1 / 2 tuttu')).toBeTruthy();
    // the pending güçlü 0.81 is not a Banko: not counted here
    expect(within(banko).getByText('1 tutmadı')).toBeTruthy();
    const oranli = screen.getByRole('group', { name: 'Oranlı başarı oranı' });
    expect(within(oranli).getByText('%100')).toBeTruthy();
    expect(within(oranli).getByText('1 / 1 tuttu')).toBeTruthy();
    expect(within(oranli).getByText('1 iptal')).toBeTruthy();
  });

  it('lists one row per match with the result marks and the score', async () => {
    respondWith(FIXTURE);
    renderPage();
    const table = await picksTable();
    const rows = within(table).getAllByRole('row');
    expect(rows).toHaveLength(1 + 3); // header + 3 matches
    const [, newest, middle, oldest] = rows;
    // newest kick-off first: the 16 October match is still pending
    expect(within(newest).getByText('Mock C – Mock D')).toBeTruthy();
    expect(within(newest).getAllByText('bekliyor').length).toBeGreaterThan(0);
    expect(within(middle).getByText('Mock Ev – Mock Dep')).toBeTruthy();
    expect(within(middle).getAllByRole('img', { name: 'Tuttu' })).toHaveLength(2);
    expect(within(middle).getByText('2–1')).toBeTruthy();
    expect(within(oldest).getByText('Mock A – Mock B')).toBeTruthy();
    expect(within(oldest).getByRole('img', { name: 'Tutmadı' }).textContent).toBe('❌');
    expect(within(oldest).getByRole('img', { name: /İptal/ })).toBeTruthy();
    expect(within(oldest).getByText('1–0')).toBeTruthy();
    expect(within(oldest).getByText('Tahmini')).toBeTruthy();
    expect(within(middle).getByText('Resmi')).toBeTruthy();
  });

  it('labels hand-recorded picks and never prints a missing score as 0', async () => {
    respondWith(FIXTURE);
    renderPage();
    const table = await picksTable();
    const newest = within(table).getAllByRole('row')[1];
    expect(within(newest).getByText(/elle kayıt/)).toBeTruthy();
    expect(within(newest).queryByText('0–0')).toBeNull();
    expect(screen.getByText(/bahis oranı kaydedilmemişti/)).toBeTruthy();
  });

  it('reloads with the chosen period and competition', async () => {
    respondWith(FIXTURE);
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('group', { name: 'Banko başarı oranı' });
    expect(apiGet).toHaveBeenLastCalledWith(CURRENT, expect.anything());

    await user.click(screen.getByRole('button', { name: 'Son 7 gün' }));
    await waitFor(() =>
      expect(apiGet).toHaveBeenLastCalledWith('/track-record/headline?days=7&rule_version=headline_v2', expect.anything()),
    );

    await user.selectOptions(screen.getByRole('combobox', { name: 'Yarışma' }), '73');
    await waitFor(() =>
      expect(apiGet).toHaveBeenLastCalledWith(
        '/track-record/headline?days=7&rule_version=headline_v2&competition_id=73',
        expect.anything(),
      ),
    );
  });

  it('defaults to the current rule and switches to the old one', async () => {
    respondWith(FIXTURE);
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('group', { name: 'Banko başarı oranı' });
    const versions = screen.getByRole('group', { name: 'Kural sürümü' });
    const current = within(versions).getByRole('button', { name: 'Güncel kural (v2)' });
    const old = within(versions).getByRole('button', { name: 'Eski kural (v1)' });
    expect(current.getAttribute('aria-pressed')).toBe('true');
    expect(old.getAttribute('aria-pressed')).toBe('false');
    expect(apiGet).toHaveBeenLastCalledWith(CURRENT, expect.anything());

    respondWith({ ...FIXTURE, rule_version: 'headline_v1' });
    await user.click(old);
    await waitFor(() =>
      expect(apiGet).toHaveBeenLastCalledWith('/track-record/headline?days=30&rule_version=headline_v1', expect.anything()),
    );
    expect(old.getAttribute('aria-pressed')).toBe('true');
    // the old rule's Oranlı floor is named in its row
    expect(await screen.findByText(/eski kural: ihtimal %45 ve üstü/)).toBeTruthy();
  });

  it('shows one row per Banko tier and the Oranlı', async () => {
    respondWith(FIXTURE);
    renderPage();
    const tiers = within(await screen.findByRole('region', { name: 'Güce göre' }));
    const rows = tiers.getAllByRole('row');
    expect(rows).toHaveLength(1 + 4);
    const [, cokGuclu, banko, guclu, oranli] = rows;
    expect(within(cokGuclu).getByText('Çok güçlü')).toBeTruthy();
    expect(within(cokGuclu).getByText('model %90 ve üstü')).toBeTruthy();
    expect(within(cokGuclu).getByText('1/1 · %100')).toBeTruthy();
    expect(within(banko).getByText('Banko')).toBeTruthy();
    expect(within(banko).getByText('model %85–90')).toBeTruthy();
    expect(within(banko).getByText('0/1 · %0')).toBeTruthy();
    expect(within(guclu).getByText('Güçlü')).toBeTruthy();
    expect(within(guclu).getByText('model %70–85, banko sayılmaz')).toBeTruthy();
    // nothing settled in the güçlü tier: no rate, one pending
    expect(within(guclu).getByText('—')).toBeTruthy();
    expect(within(guclu).getByText('1')).toBeTruthy();
    expect(within(oranli).getByText('Oranlı')).toBeTruthy();
    expect(within(oranli).getByText('ihtimal %55 ve üstü, oran 1.60 ve üstü')).toBeTruthy();
    expect(within(oranli).getByText('1/1 · %100')).toBeTruthy();
    // tier tags in the pick list
    const picks = within(await picksTable());
    expect(picks.getByText('çok güçlü')).toBeTruthy();
    expect(picks.getByText('güçlü')).toBeTruthy();
  });

  it('says how many recorded Bankos a ~90 % claim needs and how many there are', async () => {
    respondWith(FIXTURE);
    renderPage();
    const line = await screen.findByText(/yaklaşık 300 kayıtlı/);
    expect(line.textContent).toContain('Banko’nun (model %85 ve üstü) yaklaşık %90 tuttuğunu söyleyebilmek için');
    expect(line.textContent).toContain('şimdiye kadar 2 Banko sonuçlandı, 3 bekliyor.');
  });

  it('still renders a track record without tiers (backend older than headline_v2)', async () => {
    const old: HeadlineTrackRecord = {
      ...FIXTURE,
      summary: { banko: FIXTURE.summary.banko, oranli: FIXTURE.summary.oranli },
      by_competition: FIXTURE.by_competition.map((row) => ({ ...row, banko_strong: undefined })),
      by_week: FIXTURE.by_week.map((row) => ({ ...row, banko_strong: undefined })),
    };
    delete old.banko_tiers;
    delete old.banko_progress;
    delete old.rule_version;
    respondWith(old);
    renderPage();
    const banko = await screen.findByRole('group', { name: 'Banko başarı oranı' });
    expect(screen.queryByRole('region', { name: 'Güce göre' })).toBeNull();
    expect(screen.queryByText(/kayıtlı\s+Banko gerekir/)).toBeNull();
    // such a backend ignores the rule version: the page says the numbers are not separated
    expect(screen.getByRole('note').textContent).toContain('Sunucu bu kural sürümünü ayırmıyor');
    // and it cannot split the Bankos by strength: the figure says it counts them all
    expect(within(banko).getByText('tüm güçler birlikte')).toBeTruthy();
    expect(within(banko).getByText('1 tutmadı · 1 bekliyor')).toBeTruthy();
    const details = document.querySelector('.results__details') as HTMLElement;
    expect(within(details).getAllByText('Banko')).toHaveLength(2);
    expect(within(details).queryByText('Banko (%85+)')).toBeNull();
  });

  it('while another rule version loads, its button never sits over the previous version nor a false warning', async () => {
    respondWith(FIXTURE, 1);
    let release: (d: HeadlineTrackRecord) => void = () => undefined;
    apiGet.mockImplementationOnce(() => ({ json: () => new Promise<HeadlineTrackRecord>((r) => (release = r)) }));
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('group', { name: 'Banko başarı oranı' });
    await user.click(screen.getByRole('button', { name: 'Eski kural (v1)' }));
    // v1 still loading: no "Sunucu ... ayırmıyor" and none of the v2 figures under the v1 button
    expect(screen.queryByRole('note')).toBeNull();
    expect(screen.queryByRole('group', { name: 'Banko başarı oranı' })).toBeNull();
    expect(screen.getByText('Sonuçlar yükleniyor')).toBeTruthy();
    release({ ...FIXTURE, rule_version: 'headline_v1' });
    expect(await screen.findByText(/eski kural: ihtimal %45 ve üstü/)).toBeTruthy();
    expect(screen.queryByRole('note')).toBeNull();
  });

  it('a failed switch shows the error, not the previous version with a false warning', async () => {
    respondWith(FIXTURE, 1);
    respondWith(new Error('network'), 1);
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('group', { name: 'Banko başarı oranı' });
    await user.click(screen.getByRole('button', { name: 'Eski kural (v1)' }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.queryByRole('note')).toBeNull();
    expect(screen.queryByText('1 / 2 tuttu')).toBeNull();
    expect(screen.queryByRole('group', { name: 'Banko başarı oranı' })).toBeNull();
  });

  it('the Banko figure counts only the 85 %+ Bankos (banko + çok güçlü), never the güçlü ones', async () => {
    // like the headline_v1 record of 2026-10-14: 5 of 7 slot picks won, but only 1 of the 2 with p >= 0.85
    respondWith({
      ...FIXTURE,
      summary: {
        banko: summary({ won: 5, lost: 2, settled: 7, hit_rate: 5 / 7 }),
        banko_strong: summary({ won: 1, lost: 1, settled: 2, hit_rate: 0.5 }),
        oranli: summary(),
      },
      by_competition: [
        {
          competition_id: '42',
          competition_name: 'Mock Kupa',
          total: 14,
          banko: summary({ won: 5, lost: 2, settled: 7, hit_rate: 5 / 7 }),
          banko_strong: summary({ won: 1, lost: 1, settled: 2, hit_rate: 0.5 }),
          oranli: summary(),
        },
        { competition_id: '73', competition_name: 'Mock Lig', total: 1, banko: summary(), banko_strong: summary(), oranli: summary() },
      ],
    });
    renderPage();
    const banko = await screen.findByRole('group', { name: 'Banko başarı oranı' });
    expect(within(banko).getByText('%50')).toBeTruthy();
    expect(within(banko).getByText('1 / 2 tuttu')).toBeTruthy();
    expect(within(banko).getByText('model %85 ve üstü')).toBeTruthy();
    expect(screen.queryByText('%71')).toBeNull();
    expect(screen.queryByText(/üçünü birlikte sayar/)).toBeNull();
    expect(screen.getByText(/yalnız model %85 ve üstü seçimleri sayar; güçlü seçimler banko sayılmaz/)).toBeTruthy();
    // the per-competition breakdown counts the same 85 %+ Bankos
    const byCompetition = within(document.querySelectorAll('.results__details table')[0] as HTMLElement);
    expect(byCompetition.getByText('Banko (%85+)')).toBeTruthy();
    expect(byCompetition.getByText('1/2 · %50')).toBeTruthy();
    expect(byCompetition.queryByText('5/7 · %71')).toBeNull();
  });

  it('no version warning when the backend answers for the requested version', async () => {
    respondWith(FIXTURE);
    renderPage();
    await screen.findByRole('group', { name: 'Banko başarı oranı' });
    expect(screen.queryByRole('note')).toBeNull();
  });

  it('shows the empty state when nothing was recorded in the period', async () => {
    respondWith(EMPTY);
    renderPage();
    expect(await screen.findByText('Bu dönemde kayıtlı seçim yok')).toBeTruthy();
    expect(screen.queryByRole('region', { name: 'Son seçimler' })).toBeNull();
    // no settled picks: the rate says "veri yok", not 0 %
    const banko = screen.getByRole('group', { name: 'Banko başarı oranı' });
    expect(within(banko).getByText('veri yok')).toBeTruthy();
    expect(within(banko).getByText('Henüz sonuçlanan seçim yok')).toBeTruthy();
    expect(within(banko).queryByText('%0')).toBeNull();
  });

  it('shows an error with a retry button', async () => {
    respondWith(new Error('network'), 1);
    respondWith(FIXTURE);
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByRole('alert')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Tekrar dene' }));
    expect(await screen.findByRole('group', { name: 'Banko başarı oranı' })).toBeTruthy();
  });

  it('offers the competitions of the period in the filter', async () => {
    respondWith(FIXTURE);
    renderPage();
    await screen.findByRole('group', { name: 'Banko başarı oranı' });
    const select = screen.getByRole('combobox', { name: 'Yarışma' });
    expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Tüm yarışmalar',
      'Mock Kupa',
      'Mock Lig',
    ]);
  });
});
