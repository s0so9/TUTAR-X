/**
 * PerformanceOverview Component
 * 
 * Foundation component for track record display.
 * Shows structure with empty/loading states only - no fake data.
 * Data integration will come in future FEAT-006.
 */

import './PerformanceOverview.css'

type TimeFilter = 'today' | '7days' | '30days' | 'season' | 'all'

interface PerformanceOverviewProps {
  /** Whether data is currently loading */
  loading?: boolean
}

export default function PerformanceOverview({
  loading = false
}: PerformanceOverviewProps) {
  // No real data yet - structure only
  const selectedFilter: TimeFilter = 'all'

  return (
    <div className="performance-overview">
      <h2 className="performance-overview__title">TUTAR X Performans Takibi</h2>
      
      {/* Time period filters */}
      <div className="filter-tabs" role="tablist">
        {[
          { key: 'today', label: 'Bugün' },
          { key: '7days', label: '7 Gün' },
          { key: '30days', label: '30 Gün' },
          { key: 'season', label: 'Sezon' },
          { key: 'all', label: 'Tümü' }
        ].map((filter) => (
          <button
            key={filter.key}
            role="tab"
            aria-selected={selectedFilter === filter.key}
            className={`filter-tab ${selectedFilter === filter.key ? 'filter-tab--active' : ''}`}
            disabled
          >
            {filter.label}
          </button>
        ))}
      </div>

      {/* Stats grid - Structure only, no fake numbers */}
      <div className="stats-grid">
        <div className="stat-card stat-card--success">
          <div className="stat-card__icon">✅</div>
          <div className="stat-card__label">Başarılı</div>
          <div className="stat-card__value">--</div>
        </div>
        
        <div className="stat-card stat-card--failed">
          <div className="stat-card__icon">❌</div>
          <div className="stat-card__label">Başarısız</div>
          <div className="stat-card__value">--</div>
        </div>
        
        <div className="stat-card stat-card--pending">
          <div className="stat-card__icon">⏳</div>
          <div className="stat-card__label">Bekleyen</div>
          <div className="stat-card__value">--</div>
        </div>
        
        <div className="stat-card stat-card--total">
          <div className="stat-card__icon">📊</div>
          <div className="stat-card__label">Toplam</div>
          <div className="stat-card__value">--</div>
        </div>
      </div>

      {/* Empty state message */}
      {!loading && (
        <div className="performance-overview__empty-state">
          <div className="empty-state-icon">🎯</div>
          <h3 className="empty-state-title">Performans Verisi Henüz Mevcut Değil</h3>
          <p className="empty-state-description">
            TUTAR X tahminlerinin başarı takibi gelecek güncellemelerde eklenecektir.
            Sistem tahminlerin sonuçlarını otomatik olarak değerlendirerek
            burada performans istatistiklerini gösterecek.
          </p>
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="performance-overview__loading-state">
          <div className="loading-spinner"></div>
          <p>Veriler yükleniyor...</p>
        </div>
      )}
    </div>
  )
}
