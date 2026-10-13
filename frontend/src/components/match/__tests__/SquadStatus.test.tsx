/**
 * SquadStatus ("Kadro Durumu") tests.
 * The squad data below is a TEST FIXTURE (mock data), not real football data.
 */

import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import SquadStatus from '../SquadStatus';
import type { SquadInfoResponse } from '../../../api/types';

const MOCK_SQUAD_INFO: SquadInfoResponse = {
  source: 'fotmob',
  home: {
    team_name: 'Mock Home FC',
    starter_value: 645063664,
    lineup_type: 'predicted',
    unavailable: [
      { name: 'Mock Player A', reason: 'injury', expected_return: 'Late October 2026', market_value: 78983208 },
      { name: 'Mock Player B', reason: 'suspension', expected_return: null, market_value: null },
      { name: 'Mock Player C', reason: 'international_duty', expected_return: 'Back in training', market_value: 120390607 },
    ],
  },
  away: {
    team_name: 'Mock Away FC',
    starter_value: 1250000000,
    lineup_type: 'standard',
    unavailable: [],
  },
};

describe('SquadStatus', () => {
  it('shows "Kadro verisi yok" when squad_info is null', () => {
    render(<SquadStatus squadInfo={null} homeTeam="H" awayTeam="A" />);
    expect(screen.getByText('Kadro Durumu')).toBeInTheDocument();
    expect(screen.getByText('Kadro verisi yok')).toBeInTheDocument();
    expect(screen.queryByText(/Kaynak:/)).not.toBeInTheDocument();
  });

  it('shows starting-XI values, lineup hint and the FotMob footnote', () => {
    render(<SquadStatus squadInfo={MOCK_SQUAD_INFO} homeTeam="H" awayTeam="A" />);
    const home = screen.getByTestId('squad-team-home');
    const away = screen.getByTestId('squad-team-away');

    expect(within(home).getByText('Mock Home FC')).toBeInTheDocument();
    expect(within(home).getByText('İlk 11 piyasa değeri')).toBeInTheDocument();
    expect(within(home).getByText('€645.1M')).toBeInTheDocument();
    expect(within(home).getByText('(tahmini kadro)')).toBeInTheDocument();

    expect(within(away).getByText('€1.25B')).toBeInTheDocument();
    expect(within(away).queryByText('(tahmini kadro)')).not.toBeInTheDocument();
    expect(within(away).getByText('Bildirilen eksik oyuncu yok')).toBeInTheDocument();

    expect(screen.getByText('Kaynak: FotMob')).toBeInTheDocument();
  });

  it('shows "veri yok" (not zero) when the source gave no injury report', () => {
    const noReport: SquadInfoResponse = {
      ...MOCK_SQUAD_INFO,
      away: { ...MOCK_SQUAD_INFO.away, unavailable: null },
    };
    render(<SquadStatus squadInfo={noReport} homeTeam="H" awayTeam="A" />);
    const away = screen.getByTestId('squad-team-away');
    expect(within(away).getByText('(veri yok)')).toBeInTheDocument();
    expect(within(away).getByText('Eksik oyuncu verisi yok')).toBeInTheDocument();
    expect(within(away).queryByText('Bildirilen eksik oyuncu yok')).not.toBeInTheDocument();
  });

  it('lists unavailable players with Turkish reasons and expected return', () => {
    render(<SquadStatus squadInfo={MOCK_SQUAD_INFO} homeTeam="H" awayTeam="A" />);
    const home = screen.getByTestId('squad-team-home');

    expect(within(home).getByText('Mock Player A')).toBeInTheDocument();
    expect(within(home).getByText('Sakat')).toBeInTheDocument();
    expect(within(home).getByText('Ekim 2026 sonu')).toBeInTheDocument();
    expect(within(home).getByText('€79.0M')).toBeInTheDocument();

    expect(within(home).getByText('Cezalı')).toBeInTheDocument();
    // Unknown reason codes are shown as received
    expect(within(home).getByText('international_duty')).toBeInTheDocument();
    expect(within(home).getByText('Antrenmanlara döndü')).toBeInTheDocument();

    // Missing return date and market value are explicit, never 0
    expect(within(home).getAllByText('veri yok')).toHaveLength(2);
    expect(within(home).queryByText('€0')).not.toBeInTheDocument();
  });

  it('shows "veri yok" when a starting-XI value is missing', () => {
    const info: SquadInfoResponse = {
      ...MOCK_SQUAD_INFO,
      away: { ...MOCK_SQUAD_INFO.away, starter_value: null },
    };
    render(<SquadStatus squadInfo={info} homeTeam="H" awayTeam="A" />);
    expect(within(screen.getByTestId('squad-team-away')).getByText('veri yok')).toBeInTheDocument();
  });
});
