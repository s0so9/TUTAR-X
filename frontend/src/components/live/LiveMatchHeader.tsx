/**
 * LiveMatchHeader Component
 * 
 * Displays live match header with competition, venue, live indicator,
 * connection status, and data quality indicators.
 */

import { ConnectionStatus, DataQualityLevel } from '../../types/live';
import './LiveMatchHeader.css';

interface LiveMatchHeaderProps {
  /** Competition name */
  competition?: string;
  /** Competition country */
  country?: string;
  /** Venue name */
  venue?: string;
  /** Connection status */
  connectionStatus: ConnectionStatus;
  /** Last update timestamp */
  lastUpdated?: Date;
  /** Overall data quality */
  dataQuality?: DataQualityLevel;
}

export default function LiveMatchHeader({
  competition,
  country,
  venue,
  connectionStatus,
  lastUpdated,
  dataQuality = 'UNAVAILABLE'
}: LiveMatchHeaderProps) {
  const statusLabel = {
    CONNECTED: 'Bağlı',
    UPDATING: 'Güncelleniyor',
    DELAYED: 'Gecikme',
    UNAVAILABLE: 'Bağlantı Yok'
  }[connectionStatus];

  const statusClass = `connection-status--${connectionStatus.toLowerCase()}`;

  const qualityLabel = {
    HIGH: 'Yüksek Kalite',
    MEDIUM: 'Orta Kalite',
    LOW: 'Düşük Kalite',
    UNAVAILABLE: 'Veri Yok'
  }[dataQuality];

  const qualityClass = `data-quality--${dataQuality.toLowerCase()}`;

  return (
    <header className="live-match-header">
      <div className="live-match-header__info">
        <div className="live-match-header__competition">
          {competition || 'Bilinmeyen Lig'}
          {country && ` • ${country}`}
        </div>
        {venue && (
          <div className="live-match-header__venue">
            📍 {venue}
          </div>
        )}
      </div>

      <div className="live-match-header__status">
        {/* Live Indicator */}
        <div className="live-indicator-badge">
          <span className="live-pulse" aria-label="Canlı"></span>
          <span className="live-text">CANLI</span>
        </div>

        {/* Connection Status */}
        <div className={`connection-status ${statusClass}`} title={statusLabel}>
          <span className="connection-dot"></span>
          <span className="connection-label">{statusLabel}</span>
        </div>

        {/* Data Quality */}
        {dataQuality !== 'UNAVAILABLE' && (
          <div className={`data-quality ${qualityClass}`} title={qualityLabel}>
            <span className="quality-icon">📊</span>
            <span className="quality-label">{qualityLabel}</span>
          </div>
        )}

        {/* Last Updated */}
        {lastUpdated && (
          <div className="last-updated" title={lastUpdated.toLocaleString('tr-TR')}>
            Son güncelleme: {getTimeAgo(lastUpdated)}
          </div>
        )}
      </div>
    </header>
  );
}

/**
 * Calculate time ago string
 */
function getTimeAgo(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);

  if (seconds < 10) return 'şimdi';
  if (seconds < 60) return `${seconds} saniye önce`;

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} dakika önce`;

  const hours = Math.floor(minutes / 60);
  return `${hours} saat önce`;
}
