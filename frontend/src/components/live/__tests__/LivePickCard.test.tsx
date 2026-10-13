/**
 * LivePickCard Component Tests
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import LivePickCard from '../LivePickCard';
import type { LivePick } from '../../../types/live';

describe('LivePickCard', () => {
  const mockActivePick: LivePick = {
    matchId: 'match-1',
    timestamp: '2025-01-06T15:30:00Z',
    minute: 25,
    market: 'Maç Sonucu',
    selection: 'Ev Sahibi Kazanır',
    probability: 0.72,
    confidence: 0.85,
    signal: 'STRONG',
    dataQuality: 'HIGH',
    passDecision: false
  };

  const mockPassPick: LivePick = {
    matchId: 'match-2',
    timestamp: '2025-01-06T16:00:00Z',
    minute: 15,
    passDecision: true,
    passReason: 'Yetersiz veri kalitesi',
    dataQuality: 'LOW'
  };

  const mockInvalidatedPick: LivePick = {
    matchId: 'match-3',
    timestamp: '2025-01-06T16:30:00Z',
    minute: 70,
    market: 'Üst/Alt 2.5',
    selection: 'Üst 2.5',
    probability: 0.68,
    confidence: 0.75,
    signal: 'MEDIUM',
    dataQuality: 'MEDIUM',
    passDecision: false,
    isInvalidated: true,
    invalidationReason: 'Kırmızı kart sonrası maç dinamikleri değişti',
    previousConfidence: 0.75
  };

  it('renders active pick correctly', () => {
    render(
      <LivePickCard
        homeTeam="Home Team"
        awayTeam="Away Team"
        pick={mockActivePick}
      />
    );

    expect(screen.getByText('TUTAR X LIVE PICK')).toBeInTheDocument();
    expect(screen.getByText('Home Team vs Away Team')).toBeInTheDocument();
    expect(screen.getByText('Maç Sonucu')).toBeInTheDocument();
    expect(screen.getByText('Ev Sahibi Kazanır')).toBeInTheDocument();
  });

  it('displays probability and confidence', () => {
    render(
      <LivePickCard
        homeTeam="Home Team"
        awayTeam="Away Team"
        pick={mockActivePick}
      />
    );

    expect(screen.getByText('72.0%')).toBeInTheDocument();
    expect(screen.getByText('85%')).toBeInTheDocument();
  });

  it('shows signal strength', () => {
    render(
      <LivePickCard
        homeTeam="Home Team"
        awayTeam="Away Team"
        pick={mockActivePick}
      />
    );

    expect(screen.getByText('Sinyal Gücü:')).toBeInTheDocument();
    expect(screen.getByText('Güçlü')).toBeInTheDocument();
  });

  it('renders PASS decision', () => {
    render(
      <LivePickCard
        homeTeam="Home Team"
        awayTeam="Away Team"
        pick={mockPassPick}
      />
    );

    expect(screen.getByText('TUTAR X LIVE PASS')).toBeInTheDocument();
    expect(screen.getByText('Seçim Yapılmadı')).toBeInTheDocument();
    expect(screen.getByText('Yetersiz veri kalitesi')).toBeInTheDocument();
  });

  it('renders invalidated pick warning', () => {
    render(
      <LivePickCard
        homeTeam="Home Team"
        awayTeam="Away Team"
        pick={mockInvalidatedPick}
      />
    );

    expect(screen.getByText('TUTAR X LIVE - GEÇERSİZ')).toBeInTheDocument();
    expect(screen.getByText('Seçim Geçersiz Kılındı')).toBeInTheDocument();
    expect(screen.getByText('Kırmızı kart sonrası maç dinamikleri değişti')).toBeInTheDocument();
  });

  it('shows unavailable state when no pick', () => {
    render(
      <LivePickCard
        homeTeam="Home Team"
        awayTeam="Away Team"
        pick={null}
      />
    );

    expect(screen.getByText('Canlı seçim verisi mevcut değil')).toBeInTheDocument();
  });

  it('displays data quality indicator', () => {
    render(
      <LivePickCard
        homeTeam="Home Team"
        awayTeam="Away Team"
        pick={mockActivePick}
      />
    );

    expect(screen.getByText('Yüksek Kalite')).toBeInTheDocument();
  });

  it('shows loading state', () => {
    render(
      <LivePickCard
        homeTeam="Home Team"
        awayTeam="Away Team"
        pick={null}
        isLoading={true}
      />
    );

    const element = screen.getByRole('generic', { busy: true });
    expect(element).toBeInTheDocument();
  });
});
