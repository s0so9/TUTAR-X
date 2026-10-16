/**
 * LivePickCard Component
 * 
 * Displays TUTAR X LIVE PICK or PASS decision with real-time confidence.
 * Shows signal strength, invalidation warnings, and data quality.
 * Styled with TUTAR X green glow for picks, muted for PASS.
 */

import type { LivePick, DataQualityLevel } from '../../types/live';
import './LivePickCard.css';

interface LivePickCardProps {
  /** Home team name */
  homeTeam: string;
  /** Away team name */
  awayTeam: string;
  /** Live pick data */
  pick?: LivePick | null;
  /** Loading state */
  isLoading?: boolean;
}

export default function LivePickCard({
  homeTeam,
  awayTeam,
  pick,
  isLoading = false
}: LivePickCardProps) {
  if (isLoading) {
    return (
      <div className="live-pick-card live-pick-card--loading" aria-busy="true">
        <div className="skeleton skeleton--badge"></div>
        <div className="skeleton skeleton--title"></div>
        <div className="skeleton skeleton--content"></div>
      </div>
    );
  }

  if (!pick) {
    return (
      <div className="live-pick-card live-pick-card--unavailable">
        <div className="live-pick-badge live-pick-badge--unavailable">
          TUTAR X LIVE
        </div>
        <div className="live-pick-card__empty">
          <p className="empty-text">Canlı seçim verisi mevcut değil</p>
          <p className="empty-subtitle">Model yeterli veri toplamayı bekliyor</p>
        </div>
      </div>
    );
  }

  // PASS Decision
  if (pick.passDecision) {
    return (
      <div className="live-pick-card live-pick-card--pass">
        <div className="live-pick-badge live-pick-badge--pass">
          TUTAR X LIVE PASS
        </div>
        <div className="live-pick-card__header">
          <h3 className="live-pick-card__title">
            {homeTeam} vs {awayTeam}
          </h3>
          {pick.minute !== undefined && (
            <span className="live-pick-card__minute">{pick.minute}'</span>
          )}
        </div>
        <div className="pass-decision">
          <div className="pass-decision__icon">⏸️</div>
          <div className="pass-decision__content">
            <div className="pass-decision__title">Seçim Yapılmadı</div>
            {pick.passReason && (
              <div className="pass-decision__reason">{pick.passReason}</div>
            )}
          </div>
        </div>
        {pick.dataQuality && (
          <div className="live-pick-card__footer">
            <DataQualityIndicator quality={pick.dataQuality} />
          </div>
        )}
      </div>
    );
  }

  // Invalidated Pick
  if (pick.isInvalidated) {
    return (
      <div className="live-pick-card live-pick-card--invalidated">
        <div className="live-pick-badge live-pick-badge--invalidated">
          TUTAR X LIVE - GEÇERSİZ
        </div>
        <div className="live-pick-card__header">
          <h3 className="live-pick-card__title">
            {homeTeam} vs {awayTeam}
          </h3>
          {pick.minute !== undefined && (
            <span className="live-pick-card__minute">{pick.minute}'</span>
          )}
        </div>
        <div className="invalidation-warning">
          <div className="invalidation-warning__icon">⚠️</div>
          <div className="invalidation-warning__content">
            <div className="invalidation-warning__title">Seçim Geçersiz Kılındı</div>
            {pick.invalidationReason && (
              <div className="invalidation-warning__reason">{pick.invalidationReason}</div>
            )}
            {pick.previousConfidence !== undefined && (
              <div className="invalidation-warning__previous">
                Önceki Güven: {(pick.previousConfidence * 100).toFixed(0)}%
              </div>
            )}
          </div>
        </div>
        {pick.market && pick.selection && (
          <div className="pick-details pick-details--dimmed">
            <div className="pick-market">{pick.market}</div>
            <div className="pick-selection">{pick.selection}</div>
          </div>
        )}
      </div>
    );
  }

  // Active Pick
  const signalClass = pick.signal ? `signal--${pick.signal.toLowerCase()}` : '';

  return (
    <div className={`live-pick-card live-pick-card--active ${signalClass}`}>
      <div className="live-pick-badge live-pick-badge--active">
        TUTAR X LIVE PICK
      </div>
      <div className="live-pick-card__header">
        <h3 className="live-pick-card__title">
          {homeTeam} vs {awayTeam}
        </h3>
        {pick.minute !== undefined && (
          <span className="live-pick-card__minute">{pick.minute}'</span>
        )}
      </div>

      {/* Pick Details */}
      {pick.market && pick.selection && (
        <div className="pick-details">
          <div className="pick-market">{pick.market}</div>
          <div className="pick-selection">{pick.selection}</div>
        </div>
      )}

      {/* Probability & Confidence */}
      <div className="pick-metrics">
        {pick.probability !== undefined && (
          <div className="metric">
            <span className="metric__label">Olasılık</span>
            <span className="metric__value">{(pick.probability * 100).toFixed(1)}%</span>
          </div>
        )}
        {pick.confidence !== undefined && (
          <div className="metric">
            <span className="metric__label">Güven</span>
            <span className="metric__value">{(pick.confidence * 100).toFixed(0)}%</span>
          </div>
        )}
      </div>

      {/* Signal Strength */}
      {pick.signal && (
        <div className="signal-indicator">
          <span className="signal-label">Sinyal Gücü:</span>
          <span className={`signal-value ${signalClass}`}>
            {getSignalLabel(pick.signal)}
          </span>
        </div>
      )}

      {/* Footer */}
      <div className="live-pick-card__footer">
        {pick.dataQuality && <DataQualityIndicator quality={pick.dataQuality} />}
      </div>
    </div>
  );
}

/**
 * DataQualityIndicator Component
 */
function DataQualityIndicator({ quality }: { quality: DataQualityLevel }) {
  const label = {
    HIGH: 'Yüksek Kalite',
    MEDIUM: 'Orta Kalite',
    LOW: 'Düşük Kalite',
    UNAVAILABLE: 'Veri Yok'
  }[quality];

  const colorClass = `quality--${quality.toLowerCase()}`;

  return (
    <div className={`quality-indicator ${colorClass}`}>
      <span className="quality-dot"></span>
      <span className="quality-label">{label}</span>
    </div>
  );
}

/**
 * Get signal label
 */
function getSignalLabel(signal: 'STRONG' | 'MEDIUM' | 'WEAK'): string {
  const labels = {
    STRONG: 'Güçlü',
    MEDIUM: 'Orta',
    WEAK: 'Zayıf'
  };
  return labels[signal] || signal;
}
