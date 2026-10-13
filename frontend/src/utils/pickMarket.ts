/**
 * Turkish display labels for TUTAR X pick markets (backend SmartMarketSelector keys).
 *
 * Only translates labels; never changes any numeric value. Unknown market keys
 * fall back to the backend's own market key + selection text.
 */

export interface PickMarketLabel {
  marketName: string;
  outcome: string;
}

export interface PickMarketTeams {
  home?: string;
  away?: string;
}

function lineFromKey(whole: string, fraction: string): string {
  return `${whole}.${fraction}`;
}

export function describePickMarket(
  market: string | undefined | null,
  selection: string | undefined | null,
  teams: PickMarketTeams = {}
): PickMarketLabel {
  if (!market || !selection) {
    return { marketName: 'PASS', outcome: 'Seçim yapılmadı' };
  }

  const home = teams.home || 'Ev sahibi';
  const away = teams.away || 'Deplasman';
  const key = market.toUpperCase();

  // 1X2
  if (key === 'HOME_WIN' || key === 'HOME') return { marketName: 'Maç Sonucu', outcome: `${home} kazanır` };
  if (key === 'DRAW') return { marketName: 'Maç Sonucu', outcome: 'Beraberlik' };
  if (key === 'AWAY_WIN' || key === 'AWAY') return { marketName: 'Maç Sonucu', outcome: `${away} kazanır` };

  // Double chance
  if (key === 'HOME_OR_DRAW') return { marketName: 'Çifte Şans', outcome: `1X (${home} veya beraberlik)` };
  if (key === 'DRAW_OR_AWAY') return { marketName: 'Çifte Şans', outcome: `X2 (beraberlik veya ${away})` };
  if (key === 'HOME_OR_AWAY') return { marketName: 'Çifte Şans', outcome: '12 (beraberlik olmaz)' };

  // Both teams to score
  if (key === 'BTTS_YES') return { marketName: 'Karşılıklı Gol', outcome: 'KG Var' };
  if (key === 'BTTS_NO') return { marketName: 'Karşılıklı Gol', outcome: 'KG Yok' };

  // Team totals: HOME_OVER_0_5 / AWAY_UNDER_1_5
  const teamTotal = /^(HOME|AWAY)_(OVER|UNDER)_(\d+)_(\d+)$/.exec(key);
  if (teamTotal) {
    const team = teamTotal[1] === 'HOME' ? home : away;
    const line = lineFromKey(teamTotal[3], teamTotal[4]);
    return {
      marketName: `${team} Gol Alt/Üst ${line}`,
      outcome: `${teamTotal[2] === 'OVER' ? 'Üst' : 'Alt'} ${line}`,
    };
  }

  // Match totals: OVER_2_5 / UNDER_3_5
  const total = /^(OVER|UNDER)_(\d+)_(\d+)$/.exec(key);
  if (total) {
    const line = lineFromKey(total[2], total[3]);
    return {
      marketName: `Alt/Üst ${line} Gol`,
      outcome: `${total[1] === 'OVER' ? 'Üst' : 'Alt'} ${line}`,
    };
  }

  // Shot markets keep the backend selection text (contains team + threshold)
  if (key.startsWith('SHOT_')) {
    return { marketName: 'Şut Pazarı', outcome: selection };
  }

  return { marketName: market, outcome: selection };
}

const VALUE_CLASSIFICATION_LABELS: Record<string, string> = {
  STRONG_VALUE: 'Güçlü Değer',
  VALUE: 'Değer',
  LOW_VALUE: 'Düşük Değer',
  NEUTRAL: 'Nötr',
  NO_VALUE: 'Değer Yok',
  NEGATIVE_VALUE: 'Negatif Değer',
  NO_ODDS: 'Oran verisi yok',
  UNAVAILABLE: 'Oran verisi yok',
  MODEL_MARKET_CONFLICT: 'Model–piyasa çelişkisi',
};

/**
 * Turkish label for a backend value classification code
 * (e.g. "STRONG_VALUE", "strong_value", "NO_ODDS"). Unknown codes are shown as received.
 */
export function describeValueClassification(code: string): string {
  const key = code.trim().toUpperCase();
  return VALUE_CLASSIFICATION_LABELS[key] ?? code.replace(/_/g, ' ');
}

/** Backend code: model probability > bookmaker-implied probability + 8 points. */
export const MODEL_MARKET_CONFLICT = 'MODEL_MARKET_CONFLICT';

/** Tooltip shown with the "Model–piyasa çelişkisi" badge. */
export const MODEL_MARKET_CONFLICT_TOOLTIP =
  'Model olasılığı piyasadan 8 puandan fazla yüksek; değer değil, olası model hatası.';

/** True when the backend flagged a model/market conflict (never value). */
export function isModelMarketConflict(code: string | null | undefined): boolean {
  return typeof code === 'string' && code.trim().toUpperCase() === MODEL_MARKET_CONFLICT;
}

/**
 * Visual tone for a value classification badge.
 * - "value": the backend classified the outcome as value
 * - "warning": model/market conflict (probable model error, NEVER value)
 * - "negative": negative value
 * - "neutral": everything else (no value, neutral, no odds, unknown codes)
 */
export type ValueClassificationTone = 'value' | 'warning' | 'negative' | 'neutral';

export function valueClassificationTone(code: string | null | undefined): ValueClassificationTone {
  if (typeof code !== 'string') return 'neutral';
  const key = code.trim().toUpperCase();
  if (key === MODEL_MARKET_CONFLICT) return 'warning';
  if (key === 'STRONG_VALUE' || key === 'VALUE' || key === 'LOW_VALUE') return 'value';
  if (key === 'NEGATIVE_VALUE') return 'negative';
  return 'neutral';
}

/**
 * Backtest result from docs/training/2026-10-13-model-training.md: at closing odds the
 * "value" rule lost money (4,834 bets, ROI −9.4%, 90% CI −12.7% … −5.9%).
 * Shown wherever a value label is shown, so the label is not read as a proven edge.
 */
export const VALUE_EVIDENCE_NOTE =
  'Değer etiketi kanıtlanmış bir avantaj değil: kapanış oranlarıyla geçmiş 4.834 bahiste bu kural −%9.4 getiri verdi.';

/** Backend odds_source for odds typed in by the user from their own sources (not verified). */
export const MANUAL_USER_SUPPLIED_ODDS = 'manual_user_supplied';

/** Label used instead of "GERÇEK ORAN" for user-supplied, unverified odds. */
export const MANUAL_ODDS_LABEL = 'Kullanıcı girişli oran (doğrulanmadı)';

export function isManualUserSuppliedOdds(source: string | null | undefined): boolean {
  return typeof source === 'string' && source.trim().toLowerCase() === MANUAL_USER_SUPPLIED_ODDS;
}

/**
 * Convert the backend's bookmaker-comparison edge_value (implied - model,
 * NEGATIVE = value) into a model edge (model - implied, POSITIVE = value),
 * which is the sign convention ValueIndicator expects.
 */
export function modelEdgeFromImpliedEdge(edgeValue: number): number {
  return edgeValue === 0 ? 0 : -edgeValue;
}

const OUTCOME_LABELS: Record<string, string> = {
  HOME: 'Ev',
  DRAW: 'Beraberlik',
  AWAY: 'Deplasman',
};

/**
 * Turkish label for a backend 1X2 outcome label ("Home" / "Draw" / "Away").
 * Other labels are returned unchanged.
 */
export function describeOutcomeLabel(label: string): string {
  return OUTCOME_LABELS[label.trim().toUpperCase()] ?? label;
}
