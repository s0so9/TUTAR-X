/**
 * LivePrediction Component
 * 
 * Displays live prediction probabilities with real-time model outputs.
 * Shows win probabilities, xG, BTTS, Over/Under markets.
 * Includes model confidence and data quality indicators.
 */

import type { LivePrediction as LivePredictionType, DataQualityLevel } from '../../types/live';
import './LivePrediction.css';

interface LivePredictionProps {
  /** Home team name */
  homeTeam: string;
  /** Away team name */
  awayTeam: string;
  /** Live prediction data */
  prediction?: LivePredictionType | null;
  /** Loading state */
  isLoading?: boolean;
}

export default function LivePrediction({
  homeTeam,
  awayTeam,
  prediction,
  isLoading = false
}: LivePredictionProps) {
  if (isLoading) {
    return (
      <div className="live-prediction" aria-busy="true">
        <div className="live-prediction__header">
          <div className="skeleton skeleton--title"></div>
        </div>
        <div className="skeleton skeleton--content"></div>
      </div>
    );
  }

  if (!prediction) {
    return (
      <div className="live-prediction">
        <div className="live-prediction__header">
          <h3 className="live-prediction__title">Canlı Tahmin</h3>
        </div>
        <div className="live-prediction__empty">
          <p className="empty-text">Canlı tahmin verisi mevcut değil</p>
          <p className="empty-subtitle">Model henüz yeterli canlı veri toplamadı</p>
        </div>
      </div>
    );
  }

  const dataQualityClass = getDataQualityClass(prediction.dataQuality);
  const dataQualityLabel = getDataQualityLabel(prediction.dataQuality);

  return (
    <div className="live-prediction">
      <div className="live-prediction__header">
        <h3 className="live-prediction__title">Canlı Tahmin</h3>
        <div className="live-prediction__meta">
          {prediction.minute !== undefined && (
            <span className="prediction-minute">{prediction.minute}'</span>
          )}
          {prediction.dataQuality && (
            <span className={`data-quality-badge ${dataQualityClass}`}>
              {dataQualityLabel}
            </span>
          )}
        </div>
      </div>

      {/* Win Probabilities */}
      {(prediction.homeWinProbability !== undefined ||
        prediction.drawProbability !== undefined ||
        prediction.awayWinProbability !== undefined) && (
        <div className="prediction-section">
          <h4 className="prediction-section__title">Maç Sonucu</h4>
          <div className="probabilities-grid">
            <ProbabilityBar
              label={`${homeTeam} Kazanır`}
              probability={prediction.homeWinProbability}
              color="green"
            />
            <ProbabilityBar
              label="Beraberlik"
              probability={prediction.drawProbability}
              color="gray"
            />
            <ProbabilityBar
              label={`${awayTeam} Kazanır`}
              probability={prediction.awayWinProbability}
              color="red"
            />
          </div>
        </div>
      )}

      {/* Expected Goals */}
      {(prediction.homeXG !== undefined || prediction.awayXG !== undefined) && (
        <div className="prediction-section">
          <h4 className="prediction-section__title">Beklenen Gol (xG)</h4>
          <div className="xg-comparison">
            <div className="xg-team">
              <div className="xg-team__label">{homeTeam}</div>
              <div className="xg-team__value">
                {prediction.homeXG?.toFixed(2) || '—'}
              </div>
            </div>
            <div className="xg-separator">—</div>
            <div className="xg-team">
              <div className="xg-team__value">
                {prediction.awayXG?.toFixed(2) || '—'}
              </div>
              <div className="xg-team__label">{awayTeam}</div>
            </div>
          </div>
        </div>
      )}

      {/* Popular Markets */}
      {(prediction.bttsProbability !== undefined ||
        prediction.over25Probability !== undefined ||
        prediction.over35Probability !== undefined) && (
        <div className="prediction-section">
          <h4 className="prediction-section__title">Popüler Marketler</h4>
          <div className="markets-grid">
            {prediction.bttsProbability !== undefined && (
              <MarketCard
                label="Karşılıklı Gol"
                probability={prediction.bttsProbability}
              />
            )}
            {prediction.over25Probability !== undefined && (
              <MarketCard
                label="Üst 2.5 Gol"
                probability={prediction.over25Probability}
              />
            )}
            {prediction.over35Probability !== undefined && (
              <MarketCard
                label="Üst 3.5 Gol"
                probability={prediction.over35Probability}
              />
            )}
          </div>
        </div>
      )}

      {/* Model Confidence */}
      {(prediction.confidence !== undefined || prediction.modelAgreement !== undefined) && (
        <div className="prediction-footer">
          {prediction.confidence !== undefined && (
            <div className="confidence-indicator">
              <span className="confidence-label">Model Güveni:</span>
              <span className="confidence-value">
                {(prediction.confidence * 100).toFixed(0)}%
              </span>
            </div>
          )}
          {prediction.modelAgreement !== undefined && (
            <div className="confidence-indicator">
              <span className="confidence-label">Model Uyumu:</span>
              <span className="confidence-value">
                {(prediction.modelAgreement * 100).toFixed(0)}%
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * ProbabilityBar Component
 */
function ProbabilityBar({
  label,
  probability,
  color
}: {
  label: string;
  probability?: number;
  color: 'green' | 'gray' | 'red';
}) {
  const value = probability !== undefined ? probability * 100 : 0;
  const display = probability !== undefined ? `${value.toFixed(1)}%` : '—';

  return (
    <div className="probability-bar">
      <div className="probability-bar__header">
        <span className="probability-bar__label">{label}</span>
        <span className="probability-bar__value">{display}</span>
      </div>
      <div className="probability-bar__track">
        <div
          className={`probability-bar__fill probability-bar__fill--${color}`}
          style={{ width: `${value}%` }}
          role="progressbar"
          aria-valuenow={value}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${label}: ${display}`}
        ></div>
      </div>
    </div>
  );
}

/**
 * MarketCard Component
 */
function MarketCard({ label, probability }: { label: string; probability: number }) {
  const value = probability * 100;

  return (
    <div className="market-card">
      <div className="market-card__label">{label}</div>
      <div className="market-card__probability">{value.toFixed(1)}%</div>
    </div>
  );
}

/**
 * Data quality helpers
 */
function getDataQualityClass(quality?: DataQualityLevel): string {
  if (!quality) return '';
  const map: Record<DataQualityLevel, string> = {
    HIGH: 'data-quality--high',
    MEDIUM: 'data-quality--medium',
    LOW: 'data-quality--low',
    UNAVAILABLE: 'data-quality--unavailable'
  };
  return map[quality] || '';
}

function getDataQualityLabel(quality?: DataQualityLevel): string {
  if (!quality) return '';
  const map: Record<DataQualityLevel, string> = {
    HIGH: 'Yüksek Kalite',
    MEDIUM: 'Orta Kalite',
    LOW: 'Düşük Kalite',
    UNAVAILABLE: 'Veri Yok'
  };
  return map[quality] || '';
}
