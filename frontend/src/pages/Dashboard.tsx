import { useState, useEffect } from 'react';
import { getUpcomingMatches, getMatchPrediction } from '../api/client';
import type { MatchResponse, MatchPredictionResponse } from '../api/types';
import { normalizeMatch } from '../utils/matchNormalizer';
import MensionePickCard from '../components/predictions/MensionePickCard';
import CombinePanel from '../components/combine/CombinePanel';
import { useFavorites } from '../hooks/useFavorites';
import { useCombine } from '../hooks/useCombine';
import { usePredictionCache } from '../contexts/PredictionCacheContext';
import { isPopularCompetitionById } from '../utils/popularCompetitions';
import './Dashboard.css';

interface MensionePickData {
  match: MatchResponse;
  prediction: MatchPredictionResponse;
}

/**
 * Parse market field to extract market name and outcome for display
 * Handles both BestTip (market + selection) and null/undefined cases
 */
function parsePickMarket(market: string | undefined, selection: string | undefined): { marketName: string; outcome: string } {
  // Handle PASS or missing pick
  if (!market || !selection) {
    return {
      marketName: 'PASS',
      outcome: 'Seçim yapılmadı',
    };
  }

  // Use the selection as the outcome directly (it's already human-readable from backend)
  // Parse market to get the market name in Turkish
  
  if (market.startsWith('HOME_WIN') || market.startsWith('DRAW') || market.startsWith('AWAY_WIN') || 
      market === 'HOME' || market === 'DRAW' || market === 'AWAY') {
    return {
      marketName: 'Maç Sonucu',
      outcome: selection,
    };
  }
  
  if (market.startsWith('BTTS_')) {
    return {
      marketName: 'Karşılıklı Gol',
      outcome: selection,
    };
  }
  
  if (market.startsWith('OVER_') || market.startsWith('UNDER_')) {
    const lineMatch = market.match(/[0-9.]+/);
    const line = lineMatch ? lineMatch[0] : '?';
    return {
      marketName: `Alt/Üst ${line} Gol`,
      outcome: selection,
    };
  }
  
  // Default case - use market and selection as-is
  return {
    marketName: market,
    outcome: selection,
  };
}

/**
 * Execute promises with bounded concurrency.
 * Limits the number of simultaneously executing promises.
 * 
 * @param tasks - Array of promise-returning functions
 * @param concurrencyLimit - Maximum number of concurrent executions
 * @returns Promise that resolves when all tasks complete
 */
async function executeWithConcurrency<T>(
  tasks: (() => Promise<T>)[],
  concurrencyLimit: number
): Promise<PromiseSettledResult<T>[]> {
  const results: PromiseSettledResult<T>[] = [];
  const executing: Promise<void>[] = [];
  
  for (let i = 0; i < tasks.length; i++) {
    const task = tasks[i];
    
    const promise = task()
      .then(value => {
        results[i] = { status: 'fulfilled', value };
      })
      .catch(reason => {
        results[i] = { status: 'rejected', reason };
      });
    
    executing.push(promise);
    
    if (executing.length >= concurrencyLimit) {
      await Promise.race(executing);
      executing.splice(0, executing.findIndex(p => p === promise) + 1);
    }
  }
  
  await Promise.all(executing);
  return results;
}

export function Dashboard() {
  const [mensionePicksData, setMensionePicksData] = useState<MensionePickData[]>([]);
  const [loading, setLoading] = useState(true);
  const [predictionsLoading, setPredictionsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const { isFavorite, toggleFavorite } = useFavorites();
  const { isInCombine, toggleCombine, combineItems, removeFromCombine, clearCombine } = useCombine();
  const predictionCache = usePredictionCache();

  useEffect(() => {
    let isMounted = true;
    const abortController = new AbortController();

    async function fetchDashboardData() {
      try {
        setLoading(true);
        setError(null);

        // Fetch upcoming matches (TODAY ONLY for faster initial load)
        // Dashboard shows curated picks - no need for 7 days of matches
        const matchesResponse = await getUpcomingMatches(1);
        
        if (!isMounted) return;
        
        const allMatches = matchesResponse.matches;
        
        // IMMEDIATELY render page - don't wait for predictions
        setLoading(false);
        
        // Start background prediction loading
        loadPredictions(allMatches, null, abortController, isMounted);
        
      } catch (err) {
        if (isMounted) {
          console.error('[Dashboard] Error fetching dashboard data:', err);
          setError(err instanceof Error ? err.message : 'Veriler yüklenirken bir hata oluştu');
          setLoading(false);
          setPredictionsLoading(false);
        }
      }
    }

    /**
     * SINGLE prediction loading pipeline.
     * Selects candidates based on:
     * - Popular competitions
     * - Active live competition (if provided)
     * - Time window (next 48 hours)
     * - Bounded limit (max 20)
     */
    async function loadPredictions(
      allMatches: MatchResponse[],
      activeCompetitionId: string | null,
      abortCtrl: AbortController,
      mounted: boolean
    ) {
      if (!mounted || allMatches.length === 0) return;
      
      const now = new Date();
      const next24Hours = new Date(now.getTime() + 24 * 60 * 60 * 1000);
      
      // Build priority competition set: popular + active
      const priorityCompetitions = new Set<string>();
      
      // Add popular competitions
      allMatches.forEach(match => {
        if (match.competition_id && isPopularCompetitionById(match.competition_id)) {
          priorityCompetitions.add(match.competition_id);
        }
      });
      
      // Add active live competition (temporary priority)
      if (activeCompetitionId) {
        priorityCompetitions.add(activeCompetitionId);
        console.log(`[PredictionPriority] Adding live competition: ${activeCompetitionId}`);
      }
      
      // Select candidate matches
      const candidateMatches = allMatches
        .filter(match => {
          // Must be scheduled
          if (match.status !== 'SCHEDULED') return false;
          
          // Must be in priority competitions
          if (!match.competition_id || !priorityCompetitions.has(match.competition_id)) return false;
          
          // Must be in next 24 hours
          const matchDate = new Date(match.scheduled_at);
          return matchDate >= now && matchDate <= next24Hours;
        })
        .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime())
        .slice(0, 5); // BOUNDED: max 5 candidates (reduced for faster initial load)
      
      if (candidateMatches.length === 0) {
        setPredictionsLoading(false);
        return;
      }
      
      // Filter out already-cached matches
      const matchesToPredict = candidateMatches.filter(match => !predictionCache.has(match.id));
      
      if (matchesToPredict.length === 0) {
        setPredictionsLoading(false);
        return;
      }
      
      console.log(`[PredictionPriority] Loading ${matchesToPredict.length} new predictions (${candidateMatches.length - matchesToPredict.length} cached)`);
      
      setPredictionsLoading(true);
      
      // Mark as loading in cache to prevent duplicate requests
      matchesToPredict.forEach(match => predictionCache.setLoading(match.id));
      
      // Create prediction fetch tasks
      const predictionTasks = matchesToPredict.map(match => 
        () => getMatchPrediction(match.id, abortCtrl.signal)
          .then(prediction => ({ match, prediction, success: true as const }))
          .catch(err => {
            const isAborted = err instanceof DOMException && err.name === 'AbortError';
            if (!isAborted) {
              console.warn(`Failed to fetch prediction for match ${match.id}:`, err);
            }
            return { match, error: err, success: false as const, aborted: isAborted };
          })
      );

      // Execute with bounded concurrency (max 3 simultaneous requests for faster first paint)
      const results = await executeWithConcurrency(predictionTasks, 3);
      
      if (!mounted) return;

      // Process results
      const newPicksData: MensionePickData[] = [];
      let failedCount = 0;
      let abortedCount = 0;

      for (const result of results) {
        if (result.status === 'fulfilled' && result.value.success) {
          const { match, prediction } = result.value;
          
          // Cache the prediction
          predictionCache.setPrediction(match.id, prediction);
          
          if (prediction.mensione_pick && !prediction.mensione_pick.pass_decision) {
            newPicksData.push({ match, prediction });
          }
        } else if (result.status === 'fulfilled' && !result.value.success) {
          if (result.value.aborted) {
            abortedCount++;
          } else {
            failedCount++;
            const error = result.value.error;
            predictionCache.setError(result.value.match.id, error instanceof Error ? error : new Error('Unknown error'));
          }
        }
      }

      console.log(`[PredictionPriority] Loaded ${newPicksData.length} new picks (${failedCount} failed, ${abortedCount} aborted)`);
      
      if (mounted) {
        // Append new picks to existing ones
        setMensionePicksData(prev => [...prev, ...newPicksData]);
        setPredictionsLoading(false);
      }
    }

    fetchDashboardData();

    return () => {
      isMounted = false;
      abortController.abort();
    };
  }, [predictionCache]);

  if (loading) {
    return (
      <div className="dashboard">
        <div className="dashboard-header">
          <h1 className="dashboard-title">TUTAR X PICKS</h1>
          <p className="dashboard-subtitle">Bugünün yapay zeka destekli maç seçimleri</p>
        </div>
        <div className="dashboard-layout">
          <main className="dashboard-main">
            <div className="loading-state">
              <div className="loading-spinner"></div>
              <p>Veriler yükleniyor...</p>
            </div>
          </main>
      </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard">
        <div className="dashboard-header">
          <h1 className="dashboard-title">TUTAR X PICKS</h1>
          <p className="dashboard-subtitle">Bugünün yapay zeka destekli maç seçimleri</p>
        </div>
        <div className="error-state">
          <p className="error-message">❌ {error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h1 className="dashboard-title">TUTAR X PICKS</h1>
        <p className="dashboard-subtitle">Bugünün yapay zeka destekli maç seçimleri</p>
        

      </div>

      <div className="dashboard-layout">
        {/* Main area - TUTAR X picks */}
        <main className="dashboard-main dashboard-main--full-width">
          

          
          {predictionsLoading && mensionePicksData.length === 0 ? (
            <div className="loading-state">
              <div className="loading-spinner"></div>
              <p>TUTAR X seçimleri hazırlanıyor...</p>
              <p className="loading-subtext">Popüler liglerdeki maçlar için tahminler oluşturuluyor</p>
            </div>
          ) : mensionePicksData.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">⚽</div>
              <p className="empty-title">Şu anda TUTAR X seçimi yok</p>
              <p className="empty-description">
                Yaklaşan maçlar için yeterli veri mevcut olmayabilir veya modeller tarafından 
                güvenilir tahmin üretilememiş olabilir. Lütfen daha sonra tekrar kontrol edin.
              </p>
            </div>
          ) : (
            <div className="mensione-picks-grid">
              {mensionePicksData.map(({ match, prediction }) => {
                const normalizedMatch = normalizeMatch(match);
                const pick = prediction.mensione_pick!; // Already filtered for non-null
                const { marketName, outcome } = parsePickMarket(pick.market, pick.selection);
                
                return (
                  <MensionePickCard
                    key={match.id}
                    homeTeam={normalizedMatch.homeTeam.name}
                    awayTeam={normalizedMatch.awayTeam.name}
                    homeTeamLogoUrl={normalizedMatch.homeTeam.logoUrl || undefined}
                    awayTeamLogoUrl={normalizedMatch.awayTeam.logoUrl || undefined}
                    homeTeamCode={normalizedMatch.homeTeam.code || undefined}
                    awayTeamCode={normalizedMatch.awayTeam.code || undefined}
                    marketName={marketName}
                    outcome={outcome}
                    confidence={pick.confidence ?? 0}
                    realOdds={pick.bookmaker_odds ?? 0} // Real bookmaker odds (or 0 if null)
                    isFavorite={isFavorite(match.id)}
                    onToggleFavorite={() => toggleFavorite(match.id)}
                    inCombine={isInCombine(match.id)}
                    onToggleCombine={() => {
                      // For combine calculation: use ONLY real market odds
                      // Never use confidence, fair odds, or fabricated values
                      toggleCombine({
                        matchId: match.id,
                        marketName,
                        outcome,
                        marketOdds: pick.bookmaker_odds !== undefined ? pick.bookmaker_odds : null,  // null if unavailable
                        confidence: pick.confidence ?? 0,
                        homeTeam: normalizedMatch.homeTeam.name,
                        awayTeam: normalizedMatch.awayTeam.name,
                      });
                    }}
                    // === Backend fields for testing/preview ===
                    predictedScore={prediction.predicted_score ?? 'N/A'}
                    homeXg={prediction.home_xg}
                    awayXg={prediction.away_xg}
                    bttsProbability={prediction.btts_probability}
                    homeWinProbability={prediction.home_win_probability}
                    drawProbability={prediction.draw_probability}
                    awayWinProbability={prediction.away_win_probability}
                    pickProbability={pick.probability ?? 0}
                    reasoningFactors={pick.selector_reason ? [pick.selector_reason] : []}
                    scoreDistributionTop5={[]}
                    fairOdds={pick.fair_odds ?? 0}
                    marketOdds={pick.bookmaker_odds !== undefined ? pick.bookmaker_odds : null}
                    predictionVersionId={prediction.prediction_version_id}
                  />
                );
              })}
            </div>
          )}
        </main>
      </div>
      
      {/* Combine Panel - Bottom Right Fixed */}
      <CombinePanel
        combineItems={combineItems}
        onRemoveItem={removeFromCombine}
        onClearAll={clearCombine}
      />
    </div>
  );
}
