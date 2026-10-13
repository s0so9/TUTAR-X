/**
 * describePickMarket - Turkish labels for backend market keys.
 */

import { describe, it, expect } from 'vitest';
import {
  MANUAL_ODDS_LABEL,
  describeOutcomeLabel,
  describePickMarket,
  describeValueClassification,
  isManualUserSuppliedOdds,
  isModelMarketConflict,
  modelEdgeFromImpliedEdge,
  valueClassificationTone,
} from '../pickMarket';

const teams = { home: 'Ev Takımı', away: 'Dep Takımı' };

describe('describePickMarket', () => {
  it('returns PASS when no market was selected', () => {
    expect(describePickMarket(undefined, undefined)).toEqual({ marketName: 'PASS', outcome: 'Seçim yapılmadı' });
  });

  it('translates match totals and team totals', () => {
    expect(describePickMarket('OVER_1_5', 'Over 1.5 Goals', teams)).toEqual({
      marketName: 'Alt/Üst 1.5 Gol',
      outcome: 'Üst 1.5',
    });
    expect(describePickMarket('UNDER_3_5', 'Under 3.5 Goals', teams).outcome).toBe('Alt 3.5');
    expect(describePickMarket('AWAY_OVER_0_5', 'Away Over 0.5 Goals', teams)).toEqual({
      marketName: 'Dep Takımı Gol Alt/Üst 0.5',
      outcome: 'Üst 0.5',
    });
  });

  it('distinguishes double chance from 1X2 draw', () => {
    expect(describePickMarket('DRAW', 'Draw', teams)).toEqual({ marketName: 'Maç Sonucu', outcome: 'Beraberlik' });
    expect(describePickMarket('DRAW_OR_AWAY', 'Draw or Away', teams).marketName).toBe('Çifte Şans');
    expect(describePickMarket('HOME_WIN', 'Home Win', teams).outcome).toBe('Ev Takımı kazanır');
  });

  it('translates BTTS and falls back to backend text for unknown keys', () => {
    expect(describePickMarket('BTTS_YES', 'Yes', teams).outcome).toBe('KG Var');
    expect(describePickMarket('BTTS_NO', 'No', teams).outcome).toBe('KG Yok');
    expect(describePickMarket('CORNERS_9_5', 'Over 9.5 Corners', teams)).toEqual({
      marketName: 'CORNERS_9_5',
      outcome: 'Over 9.5 Corners',
    });
  });
});

describe('describeValueClassification', () => {
  it('translates backend value classification codes (any case)', () => {
    expect(describeValueClassification('STRONG_VALUE')).toBe('Güçlü Değer');
    expect(describeValueClassification('negative_value')).toBe('Negatif Değer');
    expect(describeValueClassification('NO_ODDS')).toBe('Oran verisi yok');
    expect(describeValueClassification('unavailable')).toBe('Oran verisi yok');
  });

  it('shows unknown codes as received, without underscores', () => {
    expect(describeValueClassification('SOME_NEW_CODE')).toBe('SOME NEW CODE');
  });

  it('labels MODEL_MARKET_CONFLICT as a conflict, not value', () => {
    expect(describeValueClassification('MODEL_MARKET_CONFLICT')).toBe('Model–piyasa çelişkisi');
    expect(isModelMarketConflict('MODEL_MARKET_CONFLICT')).toBe(true);
    expect(isModelMarketConflict('model_market_conflict')).toBe(true);
    expect(isModelMarketConflict('VALUE')).toBe(false);
    expect(isModelMarketConflict(null)).toBe(false);
  });
});

describe('valueClassificationTone', () => {
  it('never gives MODEL_MARKET_CONFLICT the value tone', () => {
    expect(valueClassificationTone('MODEL_MARKET_CONFLICT')).toBe('warning');
    expect(valueClassificationTone('STRONG_VALUE')).toBe('value');
    expect(valueClassificationTone('VALUE')).toBe('value');
    expect(valueClassificationTone('LOW_VALUE')).toBe('value');
    expect(valueClassificationTone('NEGATIVE_VALUE')).toBe('negative');
    expect(valueClassificationTone('NO_VALUE')).toBe('neutral');
    expect(valueClassificationTone(undefined)).toBe('neutral');
  });
});

describe('isManualUserSuppliedOdds', () => {
  it('detects user-supplied (unverified) odds', () => {
    expect(isManualUserSuppliedOdds('manual_user_supplied')).toBe(true);
    expect(isManualUserSuppliedOdds('iddaa')).toBe(false);
    expect(isManualUserSuppliedOdds(null)).toBe(false);
    expect(MANUAL_ODDS_LABEL).toBe('Kullanıcı girişli oran (doğrulanmadı)');
  });
});

describe('modelEdgeFromImpliedEdge', () => {
  it('flips the backend sign so positive means value', () => {
    // edge_value = implied - model; -0.043 means the model is 4.3 points above the market
    expect(modelEdgeFromImpliedEdge(-0.043)).toBeCloseTo(0.043, 10);
    expect(modelEdgeFromImpliedEdge(0.066)).toBeCloseTo(-0.066, 10);
    expect(Object.is(modelEdgeFromImpliedEdge(0), 0)).toBe(true);
  });
});

describe('describeOutcomeLabel', () => {
  it('translates Home/Draw/Away and keeps other labels', () => {
    expect(describeOutcomeLabel('Home')).toBe('Ev');
    expect(describeOutcomeLabel('Draw')).toBe('Beraberlik');
    expect(describeOutcomeLabel('Away')).toBe('Deplasman');
    expect(describeOutcomeLabel('1X')).toBe('1X');
  });
});
