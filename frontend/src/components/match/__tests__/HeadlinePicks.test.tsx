/**
 * HeadlinePicks: the Banko tier, the past test rate (tested competitions only), "Ön tahmin" / "Kesin",
 * the freeze note and the result marks of the frozen picks.
 * Picks and record below are TEST FIXTURES (made-up values).
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { HeadlinePicks } from '../HeadlinePicks';
import type { HeadlinePickItem, MatchHeadlineRecord } from '../../../api/headlineRecord';
import { bankoTier, type HeadlinePicks as Picks, type PickCandidate } from '../../../utils/headlinePicks';
import type { PickStatusInfo } from '../../../utils/headlineRecord';

function candidate(key: string, p: number, outcome: string, odds: number | null = null): PickCandidate {
  return {
    key,
    marketName: 'Mock pazar',
    outcome,
    probability: p,
    fairOdds: 1 / p,
    odds,
    oddsSource: null,
    bankoEligible: true,
    source: 'match',
  };
}

function picksOf(banko: PickCandidate | null, oranli: PickCandidate | null): Picks {
  return { banko, oranli, bankoTier: banko ? bankoTier(banko.probability) : null };
}

function frozen(over: Partial<HeadlinePickItem>): HeadlinePickItem {
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
    market_name: 'Mock pazar',
    probability: 0.81,
    fair_odds: 1.23,
    odds: null,
    lineup_type: { home: 'confirmed', away: 'confirmed', source: 'test' },
    model_1x2: null,
    result: null,
    final_score: null,
    settled_at: null,
    source: 'live_freeze',
    rule_version: 'headline_v1',
    ...over,
  };
}

const PICKS = picksOf(candidate('HOME_OR_DRAW', 0.81, '1X (Mock Ev veya beraberlik)'), candidate('OVER_2_5', 0.58, 'Üst 2.5'));

function renderCards(
  record?: MatchHeadlineRecord | null,
  picks: Picks = PICKS,
  extra: { competitionId?: string | null; status?: PickStatusInfo } = {},
) {
  return render(
    <HeadlinePicks picks={picks} isInCombine={() => false} onToggleCombine={vi.fn()} record={record} {...extra} />,
  );
}

describe('HeadlinePicks with frozen picks', () => {
  it('shows nothing extra when no record exists', () => {
    renderCards(null);
    expect(screen.queryByText(/kaydedildi/)).toBeNull();
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('shows the freeze note under the cards before the match', () => {
    renderCards({
      match_id: 'fotmob_1',
      frozen: true,
      picks: { banko: frozen({}), oranli: frozen({ kind: 'oranli', market_key: 'OVER_2_5' }) },
    });
    expect(screen.getByText('Maçtan 20 dk önce kaydedildi · resmi kadro')).toBeTruthy();
    expect(screen.queryByRole('img')).toBeNull(); // not settled: no marks yet
  });

  it('puts the result mark on each settled frozen pick', () => {
    renderCards({
      match_id: 'fotmob_1',
      frozen: true,
      picks: {
        banko: frozen({ result: 'lost' }),
        oranli: frozen({ kind: 'oranli', market_key: 'OVER_2_5', result: 'won' }),
      },
    });
    const banko = screen.getByRole('region', { name: 'Banko' });
    const oranli = screen.getByRole('region', { name: 'Oranlı' });
    expect(within(banko).getByRole('img', { name: 'Tutmadı' }).textContent).toBe('❌');
    expect(within(oranli).getByRole('img', { name: 'Tuttu' }).textContent).toBe('✅');
  });

  it('prints the frozen pick separately when the live rule now gives another one', () => {
    renderCards(
      {
        match_id: 'fotmob_1',
        frozen: true,
        picks: { banko: frozen({ result: 'won', selection_text: 'Mock Ev kazanır', market_key: 'HOME_WIN', probability: 0.72 }), oranli: null },
      },
      PICKS,
    );
    const banko = screen.getByRole('region', { name: 'Banko' });
    expect(within(banko).getByText(/Kayıtlı seçim: Mock Ev kazanır · %72/)).toBeTruthy();
    expect(within(banko).getByRole('img', { name: 'Tuttu' })).toBeTruthy();
    // the card still shows today's pick; the mark appears once, on the frozen line
    expect(within(banko).getAllByRole('img')).toHaveLength(1);
  });

  it('shows the frozen pick when today nothing qualifies, instead of the empty message', () => {
    renderCards(
      { match_id: 'fotmob_1', frozen: true, picks: { banko: frozen({ result: 'lost' }), oranli: null } },
      picksOf(null, null),
    );
    const banko = screen.getByRole('region', { name: 'Banko' });
    expect(within(banko).queryByText(/güvenli seçim yok/)).toBeNull();
    expect(within(banko).getByText(/Kayıtlı seçim: 1X \(Mock Ev veya beraberlik\) · %81/)).toBeTruthy();
    // the heading follows the frozen pick's tier (0.81: güçlü)
    expect(within(banko).getByText('Güçlü — banko değil')).toBeTruthy();
    const oranli = screen.getByRole('region', { name: 'Oranlı' });
    expect(within(oranli).getByText(/güvenilir seçim yok/)).toBeTruthy();
  });
});

describe('HeadlinePicks tiers (headline_v2)', () => {
  it.each([
    [0.92, 'Çok güçlü banko', 'hp-card--tier-cok_guclu'],
    [0.87, 'Banko', 'hp-card--tier-banko'],
    [0.81, 'Güçlü — banko değil', 'hp-card--tier-guclu'],
  ])('p %s is headed "%s"', (p, heading, className) => {
    renderCards(null, picksOf(candidate('HOME_OR_DRAW', p, '1X (Mock Ev veya beraberlik)'), null), { competitionId: '47' });
    const banko = screen.getByRole('region', { name: 'Banko' });
    expect(within(banko).getByText(heading, { selector: '.hp-card__title' })).toBeTruthy();
    expect(banko.className).toContain(className);
  });

  it('only the güçlü tier gets the quiet style', () => {
    renderCards(null, picksOf(candidate('HOME_OR_DRAW', 0.87, '1X'), null));
    expect(screen.getByRole('region', { name: 'Banko' }).className).not.toContain('tier-guclu');
  });

  it('keeps the empty Banko message when nothing is between 70 % and 95 %', () => {
    renderCards(null, picksOf(null, candidate('OVER_2_5', 0.58, 'Üst 2.5')), { competitionId: '47' });
    const banko = screen.getByRole('region', { name: 'Banko' });
    expect(within(banko).getByText('Bu maçta %70 ve üstü güvenli seçim yok.')).toBeTruthy();
    expect(within(banko).getByText('Banko', { selector: '.hp-card__title' })).toBeTruthy();
    expect(within(banko).queryByText(/Ön tahmin|Kesin/)).toBeNull(); // no pick: no status label
  });
});

describe('HeadlinePicks past test rate', () => {
  it('a tested league shows the tier band rate with n, and the Oranlı rule rate', () => {
    renderCards(null, picksOf(candidate('HOME_OR_DRAW', 0.87, '1X'), candidate('OVER_2_5', 0.58, 'Üst 2.5')), {
      competitionId: '47',
    });
    const banko = screen.getByRole('region', { name: 'Banko' });
    expect(within(banko).getByText('Geçmiş testte bu güçteki seçimler %88 tuttu (model %85–90, n 329).')).toBeTruthy();
    const oranli = screen.getByRole('region', { name: 'Oranlı' });
    expect(within(oranli).getByText('Bu kuraldaki seçimler geçmiş testte %61 tuttu (n 1.758).')).toBeTruthy();
  });

  it('a güçlü pick shows its own band, not the banko rate', () => {
    renderCards(null, picksOf(candidate('OVER_1_5', 0.81, 'Üst 1.5'), null), { competitionId: '71' });
    const banko = screen.getByRole('region', { name: 'Banko' });
    expect(within(banko).getByText('Geçmiş testte bu güçteki seçimler %85 tuttu (model %80–85, n 787).')).toBeTruthy();
  });

  it('outside the tested competitions: no rate, "Bu ligde test edilmedi"', () => {
    renderCards(null, picksOf(candidate('HOME_OR_DRAW', 0.87, '1X'), candidate('OVER_2_5', 0.58, 'Üst 2.5')), {
      competitionId: '268',
    });
    expect(screen.getAllByText('Bu ligde test edilmedi.')).toHaveLength(2);
    expect(screen.queryByText(/geçmiş testte|Geçmiş testte/)).toBeNull();
  });

  it('a single 1X2 outcome gets the risk note instead of a rate', () => {
    renderCards(null, picksOf(candidate('HOME_WIN', 0.87, 'Mock Ev kazanır'), null), { competitionId: '47' });
    const banko = screen.getByRole('region', { name: 'Banko' });
    expect(within(banko).getByText('Tek sonuç: daha riskli.')).toBeTruthy();
    expect(within(banko).queryByText(/%88/)).toBeNull();
  });

  it('a UEFA match notes the smaller sample', () => {
    renderCards(null, picksOf(candidate('HOME_OR_DRAW', 0.92, '1X'), null), { competitionId: '42' });
    const banko = screen.getByRole('region', { name: 'Banko' });
    expect(within(banko).getByText('Geçmiş testte bu güçteki seçimler %93 tuttu (model %90–95, n 161).')).toBeTruthy();
    expect(within(banko).getByText('Avrupa kupalarında örneklem küçük: %85 ve üstü seçimler %86 tuttu (n 35).')).toBeTruthy();
  });

  it('while the competition is still being looked up nothing is claimed; an unknown one is said to be unknown', () => {
    const picks = picksOf(candidate('HOME_OR_DRAW', 0.87, '1X'), candidate('OVER_2_5', 0.58, 'Üst 2.5'));
    const { unmount } = renderCards(null, picks, { competitionId: undefined });
    expect(document.querySelectorAll('.hp-card__evidence')).toHaveLength(0);
    unmount();
    renderCards(null, picks, { competitionId: null });
    expect(screen.getAllByText('Yarışma bilinmiyor: geçmiş test oranı gösterilmiyor.')).toHaveLength(2);
  });

  it('a priced Oranlı pick shows no fair-path rate', () => {
    renderCards(null, picksOf(null, candidate('OVER_2_5', 0.58, 'Üst 2.5', 1.9)), { competitionId: '47' });
    const oranli = screen.getByRole('region', { name: 'Oranlı' });
    expect(within(oranli).getByText('Gerçek oranlı seçimler için geçmiş test oranı yok.')).toBeTruthy();
  });

  it('the note explains the new rule in plain Turkish and implies no profit', () => {
    renderCards(null);
    const note = document.querySelector('.hp__note')?.textContent ?? '';
    expect(note).toContain('%90 ve üstü “çok güçlü banko”');
    expect(note).toContain('%85–90 “banko”');
    expect(note).toContain('ihtimali en az %55');
    expect(note).toContain('en az 1.60 ödeyen');
    expect(note).toContain('kazanç anlamına gelmez');
    expect(note).not.toMatch(/kâr edersin|kazandırır/);
  });
});

describe('HeadlinePicks "Ön tahmin" / "Kesin"', () => {
  it('without a record or confirmed line-ups both cards are an ön tahmin, with one line', () => {
    renderCards(null);
    expect(screen.getAllByText('Ön tahmin')).toHaveLength(2);
    expect(screen.queryByText('Kesin')).toBeNull();
    expect(screen.getByText('Kadrolar açıklanınca (maçtan ~20 dk önce) kesinleşir.')).toBeTruthy();
  });

  it('frozen picks are kesin', () => {
    renderCards({
      match_id: 'fotmob_1',
      frozen: true,
      picks: { banko: frozen({ market_key: 'HOME_OR_DRAW' }), oranli: frozen({ kind: 'oranli', market_key: 'OVER_2_5' }) },
    });
    expect(screen.getAllByText('Kesin')).toHaveLength(2);
    expect(screen.queryByText('Ön tahmin')).toBeNull();
    expect(screen.queryByText(/kesinleşir/)).toBeNull();
  });

  it('picks computed from confirmed line-ups are kesin', () => {
    renderCards(null, PICKS, { status: { status: 'kesin', reason: 'confirmed_lineups' } });
    expect(screen.getAllByText('Kesin')).toHaveLength(2);
  });

  it('line-ups out after the picks were computed: still an ön tahmin, and it says why', () => {
    renderCards(null, PICKS, { status: { status: 'on_tahmin', reason: 'lineups_after_pick' } });
    expect(screen.getAllByText('Ön tahmin')).toHaveLength(2);
    expect(screen.getByText('Kadrolar açıklandı; bu seçim kadrolardan önce hesaplandı.')).toBeTruthy();
  });

  it('a live pick that differs from the frozen one is "Kayıtlı değil"; "Kesin" goes on the recorded line', () => {
    // frozen Banko MS 1 (0.72) while the cached prediction now gives 1X (0.81); the Oranlı is the frozen one
    renderCards({
      match_id: 'fotmob_1',
      frozen: true,
      picks: {
        banko: frozen({ market_key: 'HOME_WIN', selection_text: 'Mock Ev kazanır', probability: 0.72 }),
        oranli: frozen({ kind: 'oranli', market_key: 'OVER_2_5' }),
      },
    });
    const banko = screen.getByRole('region', { name: 'Banko' });
    const head = within(banko.querySelector('.hp-card__kind') as HTMLElement);
    expect(head.queryByText('Kesin')).toBeNull();
    expect(head.getByText('Kayıtlı değil')).toBeTruthy();
    const recorded = within(banko.querySelector('.hp-card__recorded') as HTMLElement);
    expect(recorded.getByText(/Kayıtlı seçim: Mock Ev kazanır · %72/)).toBeTruthy();
    expect(recorded.getByText('Kesin')).toBeTruthy();
    // the Oranlı shown is the frozen Oranlı: Kesin
    const oranli = screen.getByRole('region', { name: 'Oranlı' });
    expect(within(oranli.querySelector('.hp-card__kind') as HTMLElement).getByText('Kesin')).toBeTruthy();
  });

  it('a kind with nothing frozen is never "Kesin", even when the other kind was frozen', () => {
    // record frozen with an Oranlı only; the cached prediction now gives a Banko Üst 1.5 (0.88)
    renderCards(
      { match_id: 'fotmob_1', frozen: true, picks: { banko: null, oranli: frozen({ kind: 'oranli', market_key: 'OVER_2_5' }) } },
      picksOf(candidate('OVER_1_5', 0.88, 'Üst 1.5'), candidate('OVER_2_5', 0.58, 'Üst 2.5')),
      { competitionId: '47', status: { status: 'kesin', reason: 'confirmed_lineups' } },
    );
    const banko = screen.getByRole('region', { name: 'Banko' });
    expect(within(banko).queryByText('Kesin')).toBeNull();
    expect(within(banko).getByText('Kayıtlı değil')).toBeTruthy();
    expect(within(banko).getByText('Maç öncesi kayıtta bu seçim yoktu.')).toBeTruthy();
    const oranli = screen.getByRole('region', { name: 'Oranlı' });
    expect(within(oranli).getByText('Kesin')).toBeTruthy();
  });

  it('only the Banko frozen: the live Oranlı is not "Kesin"', () => {
    renderCards({ match_id: 'fotmob_1', frozen: true, picks: { banko: frozen({}), oranli: null } });
    expect(within(screen.getByRole('region', { name: 'Banko' })).getByText('Kesin')).toBeTruthy();
    const oranli = screen.getByRole('region', { name: 'Oranlı' });
    expect(within(oranli).queryByText('Kesin')).toBeNull();
    expect(within(oranli).getByText('Kayıtlı değil')).toBeTruthy();
  });

  it('a pick frozen with predicted line-ups is "Kaydedildi", not "Kesin"', () => {
    const predicted = { home: 'predicted', away: 'predicted', source: 'test' } as const;
    renderCards({
      match_id: 'fotmob_1',
      frozen: true,
      picks: {
        banko: frozen({ lineup_type: predicted }),
        oranli: frozen({ kind: 'oranli', market_key: 'OVER_2_5', lineup_type: predicted }),
      },
    });
    expect(screen.queryByText('Kesin')).toBeNull();
    expect(screen.getAllByText('Kaydedildi')).toHaveLength(2);
    expect(screen.getByText('Resmi kadrolar gelmeden kaydedildi; kesin sayılmaz.')).toBeTruthy();
    expect(screen.getByText('Maçtan 20 dk önce kaydedildi · tahmini kadro')).toBeTruthy();
  });
});
