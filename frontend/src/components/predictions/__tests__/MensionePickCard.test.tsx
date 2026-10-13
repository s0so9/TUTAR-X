/**
 * MensionePickCard missing-data + Turkish copy tests.
 * Props below are test fixtures, not real football data.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { userEvent } from '@testing-library/user-event';
import MensionePickCard from '../MensionePickCard';

const baseProps = {
  homeTeam: 'Test Home',
  awayTeam: 'Test Away',
  marketName: 'Alt/Üst 1.5 Gol',
  outcome: 'Üst 1.5',
  isFavorite: false,
  onToggleFavorite: vi.fn(),
  inCombine: false,
  onToggleCombine: vi.fn(),
};

describe('MensionePickCard', () => {
  it('renders "veri yok" instead of 0.0% when probability/confidence/odds are missing', () => {
    render(
      <MensionePickCard
        {...baseProps}
        confidence={null}
        pickProbability={null}
        marketOdds={null}
        fairOdds={null}
      />
    );
    expect(screen.queryByText('%0.0')).not.toBeInTheDocument();
    // Collapsed header: confidence, probability and odds are all unavailable
    expect(screen.getAllByText('veri yok').length).toBeGreaterThanOrEqual(3);
  });

  it('shows supplied values unchanged', () => {
    render(
      <MensionePickCard {...baseProps} confidence={0.66} pickProbability={0.8789} marketOdds={1.25} />
    );
    expect(screen.getByText('%87.9')).toBeInTheDocument();
    expect(screen.getByText('1.25')).toBeInTheDocument();
  });

  it('uses Turkish labels in the expanded card', async () => {
    render(
      <MensionePickCard
        {...baseProps}
        confidence={0.5}
        predictedScore="1-1"
        homeWinProbability={0.42}
        drawProbability={0.28}
        awayWinProbability={0.3}
        scoreDistributionTop5={['1-1']}
      />
    );
    await userEvent.click(screen.getByRole('button', { name: 'Kartı genişlet' }));
    expect(screen.getByText('Tahmini Skor')).toBeInTheDocument();
    expect(screen.getByText('Ev')).toBeInTheDocument();
    expect(screen.getByText('Deplasman')).toBeInTheDocument();
    expect(screen.getByText('Skor Dağılımı')).toBeInTheDocument();
    expect(screen.queryByText('Predicted Score')).not.toBeInTheDocument();
  });

  it('labels user-supplied odds as unverified instead of "GERÇEK ORAN"', async () => {
    render(
      <MensionePickCard
        {...baseProps}
        confidence={0.5}
        marketOdds={1.58}
        oddsSource="manual_user_supplied"
      />
    );
    expect(screen.getByText('ORAN (DOĞRULANMADI)')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Kartı genişlet' }));
    expect(screen.getByText('Kullanıcı girişli oran (doğrulanmadı)')).toBeInTheDocument();
    expect(screen.queryByText('GERÇEK ORAN')).not.toBeInTheDocument();
  });

  it('keeps "GERÇEK ORAN" for odds that are not user-supplied', async () => {
    render(<MensionePickCard {...baseProps} confidence={0.5} marketOdds={1.58} oddsSource="iddaa" />);
    await userEvent.click(screen.getByRole('button', { name: 'Kartı genişlet' }));
    expect(screen.getByText('GERÇEK ORAN')).toBeInTheDocument();
    expect(screen.queryByText('Kullanıcı girişli oran (doğrulanmadı)')).not.toBeInTheDocument();
  });

  it('shows MODEL_MARKET_CONFLICT as a warning badge, not as value', async () => {
    render(
      <MensionePickCard
        {...baseProps}
        confidence={0.5}
        marketOdds={2.1}
        valueClassification="MODEL_MARKET_CONFLICT"
      />
    );
    await userEvent.click(screen.getByRole('button', { name: 'Kartı genişlet' }));
    const badge = screen.getByText('Model–piyasa çelişkisi').closest('.tx-badge');
    expect(badge).toHaveClass('tx-badge--warning');
    expect(badge).not.toHaveClass('tx-badge--success');
    expect(badge).toHaveAttribute(
      'title',
      'Model olasılığı piyasadan 8 puandan fazla yüksek; değer değil, olası model hatası.'
    );
  });

  it('shows Turkish result badges', () => {
    const { rerender } = render(<MensionePickCard {...baseProps} confidence={0.5} durum="won" />);
    expect(screen.getByText('KAZANDI')).toBeInTheDocument();
    rerender(<MensionePickCard {...baseProps} confidence={0.5} durum="lost" />);
    expect(screen.getByText('KAYBETTİ')).toBeInTheDocument();
  });
});
