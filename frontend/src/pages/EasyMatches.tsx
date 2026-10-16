/**
 * Easy Matches Page - Two Category Display
 * 
 * Displays picks in two categories:
 * 1. Yüksek Oranlı Pick'ler (High Odds Picks)
 * 2. Çok Yüksek AI Confidence (Very High AI Confidence)
 * 
 * Uses real prediction data from backend.
 * Shows empty state when category has no qualifying picks.
 */

import { useState, useEffect } from 'react';
import { getMatches, getMatchPrediction } from '../api';
import type { MatchResponse, MatchPredictionResponse } from '../api/types';
import MensionePickCard from '../components/predictions/MensionePickCard';
import { useFavorites } from '../hooks/useFavorites';
import { useCombine } from '../hooks/useCombine';
import './EasyMatches.css';

// Configuration: High Odds threshold
const HIGH_ODDS_THRESHOLD = 2.5;

// Configuration: Very High AI Confidence threshold (aligned with backend easy_match_threshold)
const VERY_HIGH_CONFIDENCE_THRESHOLD = 75.0;

interface EnrichedPick {
  match: MatchResponse;
  prediction: MatchPredictionResponse;
  marketName: string;
  outcome: string;
  confidence: number;
  marketOdds: number | null;
  pickProbability: number | null;
}

export function EasyMatches() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [highOddsPicks, setHighOddsPicks] = useState<EnrichedPick[]>([]);
  const [highConfidencePicks, setHighConfidencePicks] = useState<EnrichedPick[]>([]);
  const { isFavorite, toggleFavorite } = useFavorites();
  const { isInCombine, toggleCombine } = useCombine();

  useEffect(() => {
    async function loadEasyMatches() {
      try {
        setLoading(true);
        setError(null);

        // Get scheduled matches from next 48 hours
        const now = new Date();
        const next48Hours = new Date(now.getTime() + 48 * 60 * 60 * 1000);

        const matchesResponse = await getMatches({
          status: 'SCHEDULED',
          from_date: now.toISOString().split('T')[0],
          to_date: next48Hours.toISOString().split('T')[0],
        });

        const scheduledMatches = matchesResponse.matches.filter((match) => {
          const matchDate = new Date(match.scheduled_at);
          return matchDate >= now && matchDate <= next48Hours;
        });

        // OPTIMIZATION (Section 8): Bounded concurrency for predictions
        // Instead of serial for loop, use bounded concurrent fetching
        const MAX_CONCURRENT_PREDICTIONS = 3;
        const enrichedPicks: EnrichedPick[] = [];

        // Process in batches
        for (let i = 0; i < scheduledMatches.length; i += MAX_CONCURRENT_PREDICTIONS) {
          const batch = scheduledMatches.slice(i, i + MAX_CONCURRENT_PREDICTIONS);
          
          const batchResults = await Promise.allSettled(
            batch.map(async (match) => {
              try {
                const prediction = await getMatchPrediction(match.id);

                // Check if we have a mensione_pick (TUTAR X PICK)
                if (prediction.mensione_pick && !prediction.mensione_pick.pass_decision) {
                  const pick = prediction.mensione_pick;

                  return {
                    match,
                    prediction,
                    marketName: pick.market || 'Unknown Market',
                    outcome: pick.selection || '',
                    confidence: pick.confidence ? pick.confidence * 100 : 0,
                    marketOdds: pick.bookmaker_odds || null,
                    pickProbability: pick.probability || null,
                  };
                }
                return null;
              } catch (err) {
                // Skip matches without predictions
                console.warn(`Failed to load prediction for match ${match.id}:`, err);
                return null;
              }
            })
          );
          
          // Collect successful results
          for (const result of batchResults) {
            if (result.status === 'fulfilled' && result.value !== null) {
              enrichedPicks.push(result.value);
            }
          }
        }

        // Filter into two categories
        // Category 1: High Odds (≥ threshold)
        const highOdds = enrichedPicks.filter(
          (pick) => pick.marketOdds !== null && pick.marketOdds >= HIGH_ODDS_THRESHOLD
        );

        // Category 2: Very High AI Confidence (≥ threshold)
        const highConfidence = enrichedPicks.filter(
          (pick) => pick.confidence >= VERY_HIGH_CONFIDENCE_THRESHOLD
        );

        setHighOddsPicks(highOdds);
        setHighConfidencePicks(highConfidence);
      } catch (err) {
        console.error('Failed to load easy matches:', err);
        setError(err instanceof Error ? err.message : 'Veriler yüklenirken hata oluştu');
      } finally {
        setLoading(false);
      }
    }

    loadEasyMatches();
  }, []);

  if (loading) {
    return (
      <div className="page-container">
        <div className="page-header">
          <h1>Kolay Maçlar</h1>
          <p className="page-subtitle">Yüksek oranlı ve yüksek güvenli tahminler</p>
        </div>
        <div className="loading-state">
          <div className="loading-spinner"></div>
          <p>Kolay maçlar yükleniyor...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-container">
        <div className="page-header">
          <h1>Kolay Maçlar</h1>
          <p className="page-subtitle">Yüksek oranlı ve yüksek güvenli tahminler</p>
        </div>
        <div className="error-state">
          <div className="error-icon">⚠️</div>
          <p className="error-title">Veriler yüklenemedi</p>
          <p className="error-description">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>Kolay Maçlar</h1>
        <p className="page-subtitle">Yüksek oranlı ve yüksek güvenli tahminler</p>
      </div>

      {/* Configuration Info */}
      <div className="easy-matches-config-info">
        <div className="config-info-item">
          <span className="config-info-label">Yüksek Oran Eşiği:</span>
          <span className="config-info-value">{HIGH_ODDS_THRESHOLD.toFixed(2)}</span>
        </div>
        <div className="config-info-item">
          <span className="config-info-label">Yüksek Güven Eşiği:</span>
          <span className="config-info-value">{VERY_HIGH_CONFIDENCE_THRESHOLD.toFixed(0)}%</span>
        </div>
      </div>

      {/* Category 1: High Odds Picks */}
      <section className="easy-matches-category">
        <div className="category-header">
          <h2 className="category-title">
            <span className="category-icon">💰</span>
            Yüksek Oranlı Pick'ler
          </h2>
          <span className="category-count">{highOddsPicks.length} Maç</span>
        </div>
        <p className="category-description">
          Gerçek İddaa oranı {HIGH_ODDS_THRESHOLD.toFixed(2)} ve üzeri olan pick'ler. Yüksek oran yüksek kazanma
          garantisi değildir.
        </p>

        {highOddsPicks.length === 0 ? (
          <div className="category-empty-state">
            <div className="empty-icon">📊</div>
            <p className="empty-title">Yüksek oranlı pick bulunamadı</p>
            <p className="empty-description">
              Şu anda {HIGH_ODDS_THRESHOLD.toFixed(2)} ve üzeri oranlı pick bulunmamaktadır.
            </p>
          </div>
        ) : (
          <div className="picks-grid">
            {highOddsPicks.map((pick) => {
              const homeTeam = pick.match.home_team?.name || pick.match.home_team_id;
              const awayTeam = pick.match.away_team?.name || pick.match.away_team_id;

              return (
                <MensionePickCard
                  key={`high-odds-${pick.match.id}-${pick.marketName}`}
                  homeTeam={homeTeam}
                  awayTeam={awayTeam}
                  homeTeamLogoUrl={pick.match.home_team?.logo_url || undefined}
                  awayTeamLogoUrl={pick.match.away_team?.logo_url || undefined}
                  homeTeamCode={pick.match.home_team?.code || undefined}
                  awayTeamCode={pick.match.away_team?.code || undefined}
                  marketName={pick.marketName}
                  outcome={pick.outcome}
                  confidence={pick.confidence}
                  realOdds={pick.marketOdds || 0}
                  isFavorite={isFavorite(pick.match.id)}
                  onToggleFavorite={() => toggleFavorite(pick.match.id)}
                  inCombine={isInCombine(pick.match.id)}
                  onToggleCombine={() =>
                    toggleCombine({
                      matchId: pick.match.id,
                      marketName: pick.marketName,
                      outcome: pick.outcome,
                      marketOdds: pick.marketOdds,
                      confidence: pick.confidence,
                      homeTeam,
                      awayTeam,
                    })
                  }
                  predictedScore={pick.prediction.predicted_score || null}
                  homeXg={pick.prediction.home_xg || null}
                  awayXg={pick.prediction.away_xg || null}
                  bttsProbability={pick.prediction.btts_probability || null}
                  homeWinProbability={pick.prediction.home_win_probability || null}
                  drawProbability={pick.prediction.draw_probability || null}
                  awayWinProbability={pick.prediction.away_win_probability || null}
                  pickProbability={pick.pickProbability}
                  marketOdds={pick.marketOdds}
                />
              );
            })}
          </div>
        )}
      </section>

      {/* Category 2: Very High AI Confidence */}
      <section className="easy-matches-category">
        <div className="category-header">
          <h2 className="category-title">
            <span className="category-icon">🎯</span>
            Çok Yüksek AI Confidence
          </h2>
          <span className="category-count">{highConfidencePicks.length} Maç</span>
        </div>
        <p className="category-description">
          AI Confidence {VERY_HIGH_CONFIDENCE_THRESHOLD.toFixed(0)}% ve üzeri olan pick'ler. Yüksek güven kazanma
          garantisi değildir.
        </p>

        {highConfidencePicks.length === 0 ? (
          <div className="category-empty-state">
            <div className="empty-icon">🤖</div>
            <p className="empty-title">Çok yüksek güvenli pick bulunamadı</p>
            <p className="empty-description">
              Şu anda {VERY_HIGH_CONFIDENCE_THRESHOLD.toFixed(0)}% ve üzeri AI Confidence'a sahip pick
              bulunmamaktadır.
            </p>
          </div>
        ) : (
          <div className="picks-grid">
            {highConfidencePicks.map((pick) => {
              const homeTeam = pick.match.home_team?.name || pick.match.home_team_id;
              const awayTeam = pick.match.away_team?.name || pick.match.away_team_id;

              return (
                <MensionePickCard
                  key={`high-confidence-${pick.match.id}-${pick.marketName}`}
                  homeTeam={homeTeam}
                  awayTeam={awayTeam}
                  homeTeamLogoUrl={pick.match.home_team?.logo_url || undefined}
                  awayTeamLogoUrl={pick.match.away_team?.logo_url || undefined}
                  homeTeamCode={pick.match.home_team?.code || undefined}
                  awayTeamCode={pick.match.away_team?.code || undefined}
                  marketName={pick.marketName}
                  outcome={pick.outcome}
                  confidence={pick.confidence}
                  realOdds={pick.marketOdds || 0}
                  isFavorite={isFavorite(pick.match.id)}
                  onToggleFavorite={() => toggleFavorite(pick.match.id)}
                  inCombine={isInCombine(pick.match.id)}
                  onToggleCombine={() =>
                    toggleCombine({
                      matchId: pick.match.id,
                      marketName: pick.marketName,
                      outcome: pick.outcome,
                      marketOdds: pick.marketOdds,
                      confidence: pick.confidence,
                      homeTeam,
                      awayTeam,
                    })
                  }
                  predictedScore={pick.prediction.predicted_score || null}
                  homeXg={pick.prediction.home_xg || null}
                  awayXg={pick.prediction.away_xg || null}
                  bttsProbability={pick.prediction.btts_probability || null}
                  homeWinProbability={pick.prediction.home_win_probability || null}
                  drawProbability={pick.prediction.draw_probability || null}
                  awayWinProbability={pick.prediction.away_win_probability || null}
                  pickProbability={pick.pickProbability}
                  marketOdds={pick.marketOdds}
                />
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
