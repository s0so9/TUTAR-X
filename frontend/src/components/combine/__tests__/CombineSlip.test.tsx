/**
 * CombineSlip: the past-test line of the kombine (roadmap B4) sits next to the product of the model
 * probabilities and only appears for 2-5 legs that are all 85-95 % Banko picks of tested competitions.
 * Items are TEST FIXTURES (made-up teams and probabilities).
 */

import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CombineSlip } from '../CombineSlip';
import type { CombineItem } from '../../../hooks/useCombine';

/** A leg added from the Banko card of a Premier League (47) match unless overridden. */
function leg(matchId: string, probability: number | null, over: Partial<CombineItem> = {}): CombineItem {
  return {
    matchId,
    marketName: 'Çifte Şans',
    outcome: '1X',
    marketOdds: null,
    confidence: null,
    homeTeam: `Mock Ev ${matchId}`,
    awayTeam: `Mock Dep ${matchId}`,
    probability,
    oddsSource: null,
    marketKey: 'HOME_OR_DRAW',
    competitionId: '47',
    headlineSlot: 'banko',
    ...over,
  };
}

function renderSlip(items: CombineItem[]) {
  return render(<CombineSlip items={items} onRemove={vi.fn()} onClear={vi.fn()} idPrefix="test" />);
}

describe('CombineSlip past-test line', () => {
  it('three 85 %+ legs: the product and the past same-day coupon rate, labelled as a past test', () => {
    renderSlip([leg('a', 0.9), leg('b', 0.88), leg('c', 0.86)]);
    // 0.9 * 0.88 * 0.86 = 0.68112 -> "%68.1" (displayValue.formatProbability)
    expect(screen.getByText('%68.1')).toBeTruthy();
    expect(screen.getByText('Seçimler birbirinden bağımsız sayılarak çarpıldı.')).toBeTruthy();
    // the 3-leg landed rate was above the model's expectation over few days: said so
    expect(
      screen.getByText(
        'Geçmiş test: aynı gün oynanan 3 maçlık %85+ kuponlar %75 oranında tuttu (63 gün). Bu oran modelin ' +
          'beklentisinin (%70) üstünde ve az güne dayanıyor; tesadüf olabilir.',
      ),
    ).toBeTruthy();
  });

  it('two legs use the two-leg rate, without the caveat (it landed at the expectation)', () => {
    renderSlip([leg('a', 0.85), leg('b', 0.95)]);
    expect(
      screen.getByText('Geçmiş test: aynı gün oynanan 2 maçlık %85+ kuponlar %79 oranında tuttu (90 gün).'),
    ).toBeTruthy();
  });

  it('no line for single 1X2 outcomes, untested leagues or picks that are not the Banko', () => {
    const cases: CombineItem[][] = [
      [leg('a', 0.9, { marketKey: 'HOME_WIN', outcome: 'Mock Ev kazanır' }), leg('b', 0.88)],
      [leg('a', 0.9, { competitionId: '268' }), leg('b', 0.88)],
      [leg('a', 0.9, { headlineSlot: null }), leg('b', 0.88)],
    ];
    for (const items of cases) {
      const { unmount } = renderSlip(items);
      expect(screen.queryByText(/Geçmiş test/)).toBeNull();
      unmount();
    }
  });

  it('no line when one leg is weaker, for a single leg, or for six legs', () => {
    const { unmount } = renderSlip([leg('a', 0.9), leg('b', 0.8)]);
    expect(screen.queryByText(/Geçmiş test/)).toBeNull();
    unmount();
    const single = renderSlip([leg('a', 0.9)]);
    expect(screen.queryByText(/Geçmiş test/)).toBeNull();
    single.unmount();
    renderSlip(['a', 'b', 'c', 'd', 'e', 'f'].map((id) => leg(id, 0.9)));
    expect(screen.queryByText(/Geçmiş test/)).toBeNull();
  });

  it('no line when a leg has no model probability', () => {
    renderSlip([leg('a', 0.9), leg('b', null)]);
    expect(screen.queryByText(/Geçmiş test/)).toBeNull();
  });
});
