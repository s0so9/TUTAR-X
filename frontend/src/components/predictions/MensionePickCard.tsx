/**
 * MensionePickCard Component - Premium Football Intelligence Card
 * 
 * Premium betting lounge + football analytics terminal experience.
 * TUTAR X green identity with restrained gold accents.
 * Custom CSS money-bag confidence indicators.
 */

import { useState } from 'react'
import AIConfidence from './AIConfidence'
import { UnavailableValue } from '../ui'
import { formatOdds, formatProbability } from '../../utils/displayValue'
import {
  MANUAL_ODDS_LABEL,
  MODEL_MARKET_CONFLICT_TOOLTIP,
  isManualUserSuppliedOdds,
  isModelMarketConflict,
} from '../../utils/pickMarket'
import ValueClassificationBadge from '../common/ValueClassificationBadge'
import './MensionePickCard.css'

type TabType = 'general' | 'first-half' | 'full-match'

interface MensionePickCardProps {
  homeTeam: string
  awayTeam: string
  homeTeamLogoUrl?: string
  awayTeamLogoUrl?: string
  homeTeamCode?: string
  awayTeamCode?: string
  marketName: string
  outcome: string
  /** Model confidence 0-1; null when the backend did not supply it (renders "veri yok"). */
  confidence: number | null
  realOdds?: number | null
  isFavorite: boolean
  onToggleFavorite: () => void
  inCombine: boolean
  onToggleCombine: () => void
  
  // Result state props
  skor?: { ev: number; dep: number } | null
  durum?: 'won' | 'lost' | 'pending'
  
  // Backend fields - General
  predictedScore?: string | null
  homeXg?: number | null
  awayXg?: number | null
  bttsProbability?: number | null
  homeWinProbability?: number | null
  drawProbability?: number | null
  awayWinProbability?: number | null
  pickProbability?: number | null
  reasoningFactors?: string[] | null
  scoreDistributionTop5?: string[] | null
  fairOdds?: number | null
  marketOdds?: number | null
  predictionVersionId?: string | null
  
  // Phase 5: Market Intelligence props (optional, backward compatible)
  marketEdge?: number | null
  impliedProbability?: number | null
  bookmakerSource?: string | null
  valueClassification?: string | null
  /** mensione_pick.odds_source; "manual_user_supplied" = user-typed, unverified odds */
  oddsSource?: string | null
  
  // Market Odds Integration
  averageMarketOdds?: number | null
  bookmakerCount?: number | null
  oddsLastUpdated?: string | null
  
  // Backend fields - Full Match Statistics (when available)
  homeShots?: number | null
  awayShots?: number | null
  homeShotsOnTarget?: number | null
  awayShotsOnTarget?: number | null
  homeCorners?: number | null
  awayCorners?: number | null
  homePossession?: number | null
  awayPossession?: number | null
  homeYellowCards?: number | null
  awayYellowCards?: number | null
  homeRedCards?: number | null
  awayRedCards?: number | null
  
  // Backend fields - First Half (when available)
  // NOTE: These fields are NOT currently in the backend API
  // Placeholders for future implementation
  firstHalfHomeGoals?: number | null
  firstHalfAwayGoals?: number | null
  firstHalfHomeXg?: number | null
  firstHalfAwayXg?: number | null
  firstHalfHomeShots?: number | null
  firstHalfAwayShots?: number | null
  firstHalfHomeShotsOnTarget?: number | null
  firstHalfAwayShotsOnTarget?: number | null
  firstHalfHomeCorners?: number | null
  firstHalfAwayCorners?: number | null
}

export default function MensionePickCard({
  homeTeam,
  awayTeam,
  homeTeamLogoUrl,
  awayTeamLogoUrl,
  homeTeamCode,
  awayTeamCode,
  marketName,
  outcome,
  confidence,
  isFavorite,
  onToggleFavorite,
  inCombine,
  onToggleCombine,
  skor,
  durum = 'pending',
  predictedScore,
  homeXg,
  awayXg,
  bttsProbability,
  homeWinProbability,
  drawProbability,
  awayWinProbability,
  pickProbability,
  reasoningFactors,
  scoreDistributionTop5,
  fairOdds,
  marketOdds,
  predictionVersionId,
  // Phase 5: Market Intelligence props
  marketEdge,
  impliedProbability,
  bookmakerSource,
  valueClassification,
  oddsSource,
  // Market Odds
  averageMarketOdds,
  bookmakerCount,
  // oddsLastUpdated, // TODO: Implement odds update time display
  // Full match stats
  homeShots,
  awayShots,
  homeShotsOnTarget,
  awayShotsOnTarget,
  homeCorners,
  awayCorners,
  homePossession,
  awayPossession,
  homeYellowCards,
  awayYellowCards,
  homeRedCards,
  awayRedCards,
  // First half stats
  firstHalfHomeGoals,
  firstHalfAwayGoals,
  firstHalfHomeXg,
  firstHalfAwayXg,
  firstHalfHomeShots,
  firstHalfAwayShots,
  firstHalfHomeShotsOnTarget,
  firstHalfAwayShotsOnTarget,
  firstHalfHomeCorners,
  firstHalfAwayCorners
}: MensionePickCardProps) {
  const [activeTab, setActiveTab] = useState<TabType>('general')
  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false)
  const [isExpanded, setIsExpanded] = useState(false)
  
  // Odds typed in by the user are never presented as verified bookmaker odds
  const isManualOdds = isManualUserSuppliedOdds(oddsSource)
  const isConflict = isModelMarketConflict(valueClassification)
  
  const hasBackendData = predictedScore || homeXg !== undefined || awayXg !== undefined || 
                         bttsProbability !== undefined || reasoningFactors || scoreDistributionTop5
  
  // Check first-half data availability
  const hasFirstHalfData = firstHalfHomeGoals !== undefined || 
                           firstHalfAwayGoals !== undefined ||
                           firstHalfHomeXg !== undefined ||
                           firstHalfAwayXg !== undefined ||
                           firstHalfHomeShots !== undefined ||
                           firstHalfAwayShots !== undefined ||
                           firstHalfHomeShotsOnTarget !== undefined ||
                           firstHalfAwayShotsOnTarget !== undefined ||
                           firstHalfHomeCorners !== undefined ||
                           firstHalfAwayCorners !== undefined
  
  // Check full-match data availability
  const hasFullMatchData = homeShots !== undefined ||
                           awayShots !== undefined ||
                           homeShotsOnTarget !== undefined ||
                           awayShotsOnTarget !== undefined ||
                           homeCorners !== undefined ||
                           awayCorners !== undefined ||
                           homePossession !== undefined ||
                           awayPossession !== undefined
  
  // Handle card expansion toggle (only from header/expand area, not from buttons)
  const handleCardToggle = (e: React.MouseEvent) => {
    // Prevent toggle if clicking on interactive elements
    const target = e.target as HTMLElement;
    if (
      target.closest('button') ||
      target.closest('input') ||
      target.closest('.intelligence-tab') ||
      target.closest('.combine-cta') ||
      target.closest('.favorite-btn')
    ) {
      return;
    }
    setIsExpanded(!isExpanded);
  }
  
  return (
    <article className={`mensione-pick-card ${isExpanded ? 'mensione-pick-card--expanded' : ''}`}>
      {/* Collapsed Card Header - Always Visible */}
      <div 
        className="mensione-pick-card__collapsed-header"
        onClick={handleCardToggle}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setIsExpanded(!isExpanded);
          }
        }}
        aria-expanded={isExpanded}
        aria-label={isExpanded ? 'Kartı daralt' : 'Kartı genişlet'}
      >
        {/* Top Row: Favorite + Teams + Live */}
        <div className="collapsed-header__top">
          <button
            type="button"
            className="favorite-btn favorite-btn--collapsed"
            onClick={(e) => {
              e.stopPropagation();
              onToggleFavorite();
            }}
            aria-label={isFavorite ? 'Favorilerden çıkar' : 'Favorilere ekle'}
            aria-pressed={isFavorite}
          >
            {isFavorite ? '★' : '☆'}
          </button>
          
          <div className="collapsed-header__teams">
            <div className="team-with-logo">
              {homeTeamLogoUrl ? (
                <img 
                  src={homeTeamLogoUrl} 
                  alt={homeTeam}
                  className="team-logo-mini"
                  onError={(e) => {
                    e.currentTarget.style.display = 'none';
                  }}
                />
              ) : homeTeamCode ? (
                <div className="team-logo-placeholder-mini">
                  {homeTeamCode}
                </div>
              ) : null}
              <span className="team-name">{homeTeam}</span>
            </div>
            {(skor === null || skor === undefined) ? (
              <span className="vs-separator">VS</span>
            ) : (
              <div className="score-box">
                <span className="score-home">{skor.ev}</span>
                <span className="score-separator">-</span>
                <span className="score-away">{skor.dep}</span>
              </div>
            )}
            <div className="team-with-logo">
              {awayTeamLogoUrl ? (
                <img 
                  src={awayTeamLogoUrl} 
                  alt={awayTeam}
                  className="team-logo-mini"
                  onError={(e) => {
                    e.currentTarget.style.display = 'none';
                  }}
                />
              ) : awayTeamCode ? (
                <div className="team-logo-placeholder-mini">
                  {awayTeamCode}
                </div>
              ) : null}
              <span className="team-name">{awayTeam}</span>
            </div>
          </div>
          
          {/* TODO: Add live indicator when match is live */}
        </div>
        
        {/* Pick Info Row */}
        <div className="collapsed-header__pick">
          <div className="pick-badge">TUTAR X SEÇİMİ</div>
          <div className="pick-selection">
            <span className="pick-market">{marketName}</span>
            <span className="pick-outcome">{outcome}</span>
          </div>
        </div>
        
        {/* Intelligence Row */}
        <div className="collapsed-header__intelligence">
          {/* AI Confidence or Result Badge */}
          {durum === 'pending' ? (
            <div className="intelligence-compact">
              <div className="intelligence-compact__label">YAPAY ZEKA GÜVENİ</div>
              {confidence !== null && Number.isFinite(confidence) ? (
                <AIConfidence 
                  confidence={confidence} 
                  size="sm"
                  showPercentage={false}
                  showLevel={false}
                  showLabel={false}
                />
              ) : (
                <div className="intelligence-compact__value">
                  <UnavailableValue value={null} />
                </div>
              )}
            </div>
          ) : durum === 'won' ? (
            <div className="result-badge result-badge--won" aria-label="Sonuç: Kazandı">
              <span className="result-badge__icon">✓</span>
              <span className="result-badge__text">KAZANDI</span>
            </div>
          ) : (
            <div className="result-badge result-badge--lost" aria-label="Sonuç: Kaybetti">
              <span className="result-badge__icon">✕</span>
              <span className="result-badge__text">KAYBETTİ</span>
            </div>
          )}
          
          {/* Pick Probability */}
          <div className="intelligence-compact">
            <div className="intelligence-compact__label">OLASILIK</div>
            <div className="intelligence-compact__value">
              <UnavailableValue value={formatProbability(pickProbability)} />
            </div>
          </div>
          
          {/* Real Odds */}
          <div
            className="intelligence-compact intelligence-compact--odds"
            title={isManualOdds && !averageMarketOdds ? MANUAL_ODDS_LABEL : undefined}
          >
            <div className="intelligence-compact__label">
              {isManualOdds && !averageMarketOdds ? 'ORAN (DOĞRULANMADI)' : 'ORAN'}
            </div>
            <div className="intelligence-compact__value intelligence-compact__value--gold">
              <UnavailableValue value={formatOdds(averageMarketOdds ?? marketOdds)} />
            </div>
          </div>
        </div>
        
        {/* Expand Indicator */}
        <div className="collapsed-header__expand">
          <span className="expand-text">KARTI AÇ</span>
          <span className="expand-chevron">{isExpanded ? '▲' : '▼'}</span>
        </div>
      </div>
      
      {/* Expanded Card Content */}
      {isExpanded && (
        <div className="mensione-pick-card__expanded-content">
          {/* Premium Tab Navigation */}
          <div className="intelligence-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'general'}
              aria-controls="tab-general"
              className={`intelligence-tab ${activeTab === 'general' ? 'intelligence-tab--active' : ''}`}
              onClick={() => setActiveTab('general')}
            >
              GENEL
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'first-half'}
              aria-controls="tab-first-half"
              className={`intelligence-tab ${activeTab === 'first-half' ? 'intelligence-tab--active' : ''}`}
              onClick={() => setActiveTab('first-half')}
            >
              İLK YARI
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'full-match'}
              aria-controls="tab-full-match"
              className={`intelligence-tab ${activeTab === 'full-match' ? 'intelligence-tab--active' : ''}`}
              onClick={() => setActiveTab('full-match')}
            >
              MAÇ
            </button>
          </div>
          
          {/* Tab Content */}
          <div className="tab-content">
            {/* GENEL TAB */}
            {activeTab === 'general' && (
              <div id="tab-general" role="tabpanel" className="tab-panel">
            {/* TUTAR X PICK - Hero Section */}
            <div className="mensione-pick-hero">
              <div className="mensione-pick-hero__badge">TUTAR X SEÇİMİ</div>
              <div className="mensione-pick-hero__market">{marketName}</div>
              <div className="mensione-pick-hero__selection">{outcome}</div>
            </div>
            
            {/* Intelligence Grid */}
            <div className="intelligence-grid">
              {/* AI Confidence */}
              <div className="intelligence-block intelligence-block--confidence">
                <div className="intelligence-block__label">YAPAY ZEKA GÜVENİ</div>
                {confidence !== null && Number.isFinite(confidence) ? (
                  <AIConfidence 
                    confidence={confidence} 
                    size="md"
                    showPercentage={true}
                    showLevel={true}
                    showLabel={true}
                  />
                ) : (
                  <div className="intelligence-block__value">
                    <UnavailableValue value={null} />
                  </div>
                )}
              </div>
              
              {/* Pick Probability */}
              <div className="intelligence-block intelligence-block--probability">
                <div className="intelligence-block__label">SEÇİM OLASILIĞI</div>
                <div className="intelligence-block__value intelligence-block__value--large">
                  <UnavailableValue value={formatProbability(pickProbability)} />
                </div>
              </div>
            </div>
            
            {/* Premium Odds Section */}
            <div className="odds-section">
              <div className="odds-primary">
                <div className="odds-primary__label">
                  {averageMarketOdds
                    ? 'ORTALAMA PİYASA ORANI'
                    : isManualOdds
                      ? MANUAL_ODDS_LABEL
                      : 'GERÇEK ORAN'}
                </div>
                <div className="odds-primary__value">
                  <UnavailableValue value={formatOdds(averageMarketOdds ?? marketOdds)} />
                </div>
                {bookmakerCount !== null && bookmakerCount !== undefined && bookmakerCount > 0 && (
                  <div className="odds-primary__source">
                    {bookmakerCount} büro ortalaması
                  </div>
                )}
              </div>
              
              <div className="odds-secondary">
                <div className="odds-secondary__label">Model Adil Oranı</div>
                <div className="odds-secondary__value">
                  <UnavailableValue value={formatOdds(fairOdds)} />
                </div>
              </div>
              
              {/* Show single bookmaker odds as fallback if available */}
              {averageMarketOdds && marketOdds && marketOdds !== averageMarketOdds && (
                <div className="odds-secondary">
                  <div className="odds-secondary__label">
                    {isManualOdds ? MANUAL_ODDS_LABEL : 'Tekil Büro Oranı'}
                  </div>
                  <div className="odds-secondary__value">{marketOdds.toFixed(2)}</div>
                </div>
              )}
            </div>
            
            {/* Model/market conflict: probable model error, never value */}
            {isConflict && valueClassification && (
              <div className="odds-conflict-warning" role="note" title={MODEL_MARKET_CONFLICT_TOOLTIP}>
                <ValueClassificationBadge code={valueClassification} />
                <span className="odds-conflict-warning__text">{MODEL_MARKET_CONFLICT_TOOLTIP}</span>
              </div>
            )}
            
            {/* Key Intelligence */}
            {(predictedScore || (homeXg !== undefined && awayXg !== undefined) || bttsProbability !== undefined) && (
              <div className="key-intelligence">
                {predictedScore && (
                  <div className="key-intel-item">
                    <span className="key-intel-item__label">Tahmini Skor</span>
                    <span className="key-intel-item__value">{predictedScore}</span>
                  </div>
                )}
                
                {(homeXg !== undefined && homeXg !== null && awayXg !== undefined && awayXg !== null) && (
                  <div className="key-intel-item">
                    <span className="key-intel-item__label">xG</span>
                    <span className="key-intel-item__value">
                      {homeXg.toFixed(2)} — {awayXg.toFixed(2)}
                    </span>
                  </div>
                )}
                
                {bttsProbability !== undefined && bttsProbability !== null && (
                  <div className="key-intel-item">
                    <span className="key-intel-item__label">KG Var</span>
                    <span className="key-intel-item__value">
                      {(bttsProbability * 100).toFixed(0)}%
                    </span>
                  </div>
                )}
              </div>
            )}
            
            {/* 1X2 Compact Display */}
            {(homeWinProbability !== undefined || drawProbability !== undefined || awayWinProbability !== undefined) && (
              <div className="prediction-1x2">
                <div className="prediction-1x2__label">1X2</div>
                <div className="prediction-1x2__grid">
                  {homeWinProbability !== undefined && homeWinProbability !== null && (
                    <div className="prediction-1x2__item">
                      <span className="prediction-1x2__outcome">Ev</span>
                      <span className="prediction-1x2__prob">{(homeWinProbability * 100).toFixed(1)}%</span>
                    </div>
                  )}
                  {drawProbability !== undefined && drawProbability !== null && (
                    <div className="prediction-1x2__item">
                      <span className="prediction-1x2__outcome">Beraberlik</span>
                      <span className="prediction-1x2__prob">{(drawProbability * 100).toFixed(1)}%</span>
                    </div>
                  )}
                  {awayWinProbability !== undefined && awayWinProbability !== null && (
                    <div className="prediction-1x2__item">
                      <span className="prediction-1x2__outcome">Deplasman</span>
                      <span className="prediction-1x2__prob">{(awayWinProbability * 100).toFixed(1)}%</span>
                    </div>
                  )}
                </div>
              </div>
            )}
            
            {/* Reasoning - Premium Intelligence */}
            {reasoningFactors && reasoningFactors.length > 0 && (
              <div className="reasoning-section">
                <div className="reasoning-section__label">NEDEN BU SEÇİM?</div>
                <ul className="reasoning-list">
                  {reasoningFactors.slice(0, 3).map((factor, idx) => (
                    <li key={idx} className="reasoning-list__item">• {factor}</li>
                  ))}
                </ul>
              </div>
            )}
            
            {/* Score Distribution */}
            {scoreDistributionTop5 && scoreDistributionTop5.length > 0 && (
              <div className="score-distribution-section">
                <div className="score-distribution-section__label">Skor Dağılımı</div>
                <div className="score-distribution-grid">
                  {scoreDistributionTop5.map((score, idx) => (
                    <div key={idx} className="score-dist-item">{score}</div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
        
        {/* İLK YARI TAB */}
        {activeTab === 'first-half' && (
          <div id="tab-first-half" role="tabpanel" className="tab-panel">
            {hasFirstHalfData ? (
              <>
                <div className="match-stats-section">
                  <div className="match-stats-header">İLK YARI İSTATİSTİKLER</div>
                  
                  {/* First Half Score */}
                  {(firstHalfHomeGoals !== undefined || firstHalfAwayGoals !== undefined) && (
                    <div className="stat-row">
                      <span className="stat-label">Gol</span>
                      <span className="stat-values">
                        <span className="stat-home">{firstHalfHomeGoals ?? '--'}</span>
                        <span className="stat-sep">—</span>
                        <span className="stat-away">{firstHalfAwayGoals ?? '--'}</span>
                      </span>
                    </div>
                  )}
                  
                  {/* First Half xG */}
                  {(firstHalfHomeXg !== undefined || firstHalfAwayXg !== undefined) && (
                    <div className="stat-row">
                      <span className="stat-label">xG</span>
                      <span className="stat-values">
                        <span className="stat-home">{firstHalfHomeXg?.toFixed(2) ?? '--'}</span>
                        <span className="stat-sep">—</span>
                        <span className="stat-away">{firstHalfAwayXg?.toFixed(2) ?? '--'}</span>
                      </span>
                    </div>
                  )}
                  
                  {/* First Half Shots */}
                  {(firstHalfHomeShots !== undefined || firstHalfAwayShots !== undefined) && (
                    <div className="stat-row">
                      <span className="stat-label">Şut</span>
                      <span className="stat-values">
                        <span className="stat-home">{firstHalfHomeShots ?? '--'}</span>
                        <span className="stat-sep">—</span>
                        <span className="stat-away">{firstHalfAwayShots ?? '--'}</span>
                      </span>
                    </div>
                  )}
                  
                  {/* First Half Shots on Target */}
                  {(firstHalfHomeShotsOnTarget !== undefined || firstHalfAwayShotsOnTarget !== undefined) && (
                    <div className="stat-row">
                      <span className="stat-label">İsabetli Şut</span>
                      <span className="stat-values">
                        <span className="stat-home">{firstHalfHomeShotsOnTarget ?? '--'}</span>
                        <span className="stat-sep">—</span>
                        <span className="stat-away">{firstHalfAwayShotsOnTarget ?? '--'}</span>
                      </span>
                    </div>
                  )}
                  
                  {/* First Half Corners */}
                  {(firstHalfHomeCorners !== undefined || firstHalfAwayCorners !== undefined) && (
                    <div className="stat-row">
                      <span className="stat-label">Korner</span>
                      <span className="stat-values">
                        <span className="stat-home">{firstHalfHomeCorners ?? '--'}</span>
                        <span className="stat-sep">—</span>
                        <span className="stat-away">{firstHalfAwayCorners ?? '--'}</span>
                      </span>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="empty-state">
                <div className="empty-state__icon">📊</div>
                <div className="empty-state__text">İlk yarı verisi mevcut değil</div>
              </div>
            )}
          </div>
        )}
        
        {/* MAÇ TAB */}
        {activeTab === 'full-match' && (
          <div id="tab-full-match" role="tabpanel" className="tab-panel">
            {hasFullMatchData ? (
              <div className="match-stats-section">
                <div className="match-stats-header">TAM MAÇ İSTATİSTİKLER</div>
                
                {/* Full Match Prediction */}
                {predictedScore && (
                  <div className="stat-row stat-row--highlight">
                    <span className="stat-label">Tahmin</span>
                    <span className="stat-values stat-values--prediction">{predictedScore}</span>
                  </div>
                )}
                
                {/* xG */}
                {(homeXg !== undefined || awayXg !== undefined) && (
                  <div className="stat-row">
                    <span className="stat-label">xG</span>
                    <span className="stat-values">
                      <span className="stat-home">{homeXg?.toFixed(2) ?? '--'}</span>
                      <span className="stat-sep">—</span>
                      <span className="stat-away">{awayXg?.toFixed(2) ?? '--'}</span>
                    </span>
                  </div>
                )}
                
                {/* Shots */}
                {(homeShots !== undefined || awayShots !== undefined) && (
                  <div className="stat-row">
                    <span className="stat-label">Şut</span>
                    <span className="stat-values">
                      <span className="stat-home">{homeShots ?? '--'}</span>
                      <span className="stat-sep">—</span>
                      <span className="stat-away">{awayShots ?? '--'}</span>
                    </span>
                  </div>
                )}
                
                {/* Shots on Target */}
                {(homeShotsOnTarget !== undefined || awayShotsOnTarget !== undefined) && (
                  <div className="stat-row">
                    <span className="stat-label">İsabetli Şut</span>
                    <span className="stat-values">
                      <span className="stat-home">{homeShotsOnTarget ?? '--'}</span>
                      <span className="stat-sep">—</span>
                      <span className="stat-away">{awayShotsOnTarget ?? '--'}</span>
                    </span>
                  </div>
                )}
                
                {/* Corners */}
                {(homeCorners !== undefined || awayCorners !== undefined) && (
                  <div className="stat-row">
                    <span className="stat-label">Korner</span>
                    <span className="stat-values">
                      <span className="stat-home">{homeCorners ?? '--'}</span>
                      <span className="stat-sep">—</span>
                      <span className="stat-away">{awayCorners ?? '--'}</span>
                    </span>
                  </div>
                )}
                
                {/* Possession */}
                {(homePossession !== undefined || awayPossession !== undefined) && (
                  <div className="stat-row">
                    <span className="stat-label">Top Kontrolü</span>
                    <span className="stat-values">
                      <span className="stat-home">{homePossession?.toFixed(0) ?? '--'}%</span>
                      <span className="stat-sep">—</span>
                      <span className="stat-away">{awayPossession?.toFixed(0) ?? '--'}%</span>
                    </span>
                  </div>
                )}
                
                {/* Cards */}
                {(homeYellowCards !== undefined || awayYellowCards !== undefined || homeRedCards !== undefined || awayRedCards !== undefined) && (
                  <>
                    {(homeYellowCards !== undefined || awayYellowCards !== undefined) && (
                      <div className="stat-row">
                        <span className="stat-label">Sarı Kart</span>
                        <span className="stat-values">
                          <span className="stat-home">{homeYellowCards ?? '--'}</span>
                          <span className="stat-sep">—</span>
                          <span className="stat-away">{awayYellowCards ?? '--'}</span>
                        </span>
                      </div>
                    )}
                    {(homeRedCards !== undefined || awayRedCards !== undefined) && (
                      <div className="stat-row">
                        <span className="stat-label">Kırmızı Kart</span>
                        <span className="stat-values">
                          <span className="stat-home">{homeRedCards ?? '--'}</span>
                          <span className="stat-sep">—</span>
                          <span className="stat-away">{awayRedCards ?? '--'}</span>
                        </span>
                      </div>
                    )}
                  </>
                )}
                
                {/* BTTS */}
                {bttsProbability !== undefined && bttsProbability !== null && (
                  <div className="stat-row">
                    <span className="stat-label">BTTS Olasılığı</span>
                    <span className="stat-values stat-values--single">
                      {(bttsProbability * 100).toFixed(1)}%
                    </span>
                  </div>
                )}
                
                {/* 1X2 */}
                {(homeWinProbability !== undefined || drawProbability !== undefined || awayWinProbability !== undefined) && (
                  <div className="stat-row stat-row--1x2">
                    <span className="stat-label">1X2 Olasılıkları</span>
                    <div className="stat-1x2-grid">
                      {homeWinProbability !== undefined && homeWinProbability !== null && (
                        <div className="stat-1x2-item">
                          <span className="stat-1x2-label">Ev Sahibi</span>
                          <span className="stat-1x2-value">{(homeWinProbability * 100).toFixed(1)}%</span>
                        </div>
                      )}
                      {drawProbability !== undefined && drawProbability !== null && (
                        <div className="stat-1x2-item">
                          <span className="stat-1x2-label">Beraberlik</span>
                          <span className="stat-1x2-value">{(drawProbability * 100).toFixed(1)}%</span>
                        </div>
                      )}
                      {awayWinProbability !== undefined && awayWinProbability !== null && (
                        <div className="stat-1x2-item">
                          <span className="stat-1x2-label">Deplasman</span>
                          <span className="stat-1x2-value">{(awayWinProbability * 100).toFixed(1)}%</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="empty-state">
                <div className="empty-state__icon">⚽</div>
                <div className="empty-state__text">Maç verisi mevcut değil</div>
              </div>
            )}
          </div>
        )}
          </div>
          {/* End of tab-content */}
          
          {/* Combine Action - Premium CTA */}
          <div className="card-actions">
            <button
              type="button"
              className={`combine-cta ${inCombine ? 'combine-cta--selected' : ''}`}
              onClick={(e) => {
                e.stopPropagation();
                onToggleCombine();
              }}
              aria-label={inCombine ? 'Kombineden çıkar' : 'Kombine ekle'}
              aria-pressed={inCombine}
            >
              <span className="combine-cta__icon" aria-hidden="true">
                {inCombine ? '✓' : '+'}
              </span>
              <span className="combine-cta__text">
                {inCombine ? 'KOMBİNEDEN ÇIKAR' : 'KOMBİNE EKLE'}
              </span>
            </button>
            
            {hasBackendData && (
              <button
                type="button"
                className="technical-toggle"
                onClick={(e) => {
                  e.stopPropagation();
                  setShowTechnicalDetails(!showTechnicalDetails);
                }}
              >
                {showTechnicalDetails ? 'Teknik Detayları Gizle' : 'Teknik Detaylar'}
              </button>
            )}
          </div>
          
          {/* Technical Details */}
          {hasBackendData && showTechnicalDetails && (
            <div className="technical-details">
              <div className="technical-details__content">
                {predictionVersionId && (
                  <div className="tech-field">
                    <span className="tech-field__label">Sürüm:</span>
                    <span className="tech-field__value tech-field__value--mono">
                      {predictionVersionId.slice(0, 8)}
                    </span>
                  </div>
                )}
                {/* Phase 5: Market Intelligence - only when available */}
                {marketEdge !== undefined && marketEdge !== null && (
                  <div className="tech-field">
                    <span className="tech-field__label">Piyasa Avantajı:</span>
                    <span className="tech-field__value">
                      {(marketEdge * 100).toFixed(2)}%
                    </span>
                  </div>
                )}
                {impliedProbability !== undefined && impliedProbability !== null && (
                  <div className="tech-field">
                    <span className="tech-field__label">İma Edilen Olasılık:</span>
                    <span className="tech-field__value">
                      {(impliedProbability * 100).toFixed(2)}%
                    </span>
                  </div>
                )}
                {bookmakerSource && (
                  <div className="tech-field">
                    <span className="tech-field__label">Büro:</span>
                    <span className="tech-field__value">
                      {bookmakerSource}
                    </span>
                  </div>
                )}
                {valueClassification && (
                  <div className="tech-field">
                    <span className="tech-field__label">Değer:</span>
                    <span className="tech-field__value">
                      <ValueClassificationBadge code={valueClassification} />
                    </span>
                  </div>
                )}
                {isManualOdds && (
                  <div className="tech-field">
                    <span className="tech-field__label">Oran kaynağı:</span>
                    <span className="tech-field__value">{MANUAL_ODDS_LABEL}</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </article>
  )
}
