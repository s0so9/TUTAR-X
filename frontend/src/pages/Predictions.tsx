import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { getUpcomingMatches, getMatchPrediction } from '../api';
import type { MatchResponse, MatchPredictionResponse } from '../api/types';
import {
  formatTeamName,
  formatCompetitionName,
  formatMatchDateTime
} from '../utils/formatters';
import ProbabilityDisplay from '../components/common/ProbabilityDisplay';
import ConfidenceIndicator from '../components/common/ConfidenceIndicator';
import BookmakerValueList from '../components/predictions/BookmakerValueList';
import './Predictions.css';

interface PredictionData {
  match: MatchResponse;
  prediction: MatchPredictionResponse | null;
  error?: string;
}

export function Predictions() {
  const [predictions, setPredictions] = useState<PredictionData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDevelopmentData, setIsDevelopmentData] = useState(false);

  useEffect(() => {
    async function fetchPredictions() {
      try {
        setLoading(true);
        setError(null);

        // Fetch upcoming matches
        const matchesResponse = await getUpcomingMatches(14);
        setIsDevelopmentData(matchesResponse.is_development_data);

        // OPTIMIZATION (Section 8): Bounded concurrency for predictions
        // Instead of unlimited Promise.all, use bounded queue
        const MAX_CONCURRENT_PREDICTIONS = 3;
        const predictionsData: PredictionData[] = [];

        // Process in batches
        for (let i = 0; i < matchesResponse.matches.length; i += MAX_CONCURRENT_PREDICTIONS) {
          const batch = matchesResponse.matches.slice(i, i + MAX_CONCURRENT_PREDICTIONS);
          const batchResults = await Promise.all(
            batch.map(async (match) => {
              try {
                const prediction = await getMatchPrediction(match.id);
                return { match, prediction };
              } catch (err) {
                // Prediction might not be available for this match
                return {
                  match,
                  prediction: null,
                  error: err instanceof Error ? err.message : 'Tahmin mevcut değil'
                };
              }
            })
          );
          predictionsData.push(...batchResults);
        }

        setPredictions(predictionsData);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Tahminler yüklenirken bir hata oluştu');
      } finally {
        setLoading(false);
      }
    }

    fetchPredictions();
  }, []);

  if (loading) {
    return (
      <div className="page-container">
        <div className="page-header">
          <h1>Tahminler</h1>
          <p className="page-subtitle">Tüm tahminler ve olasılıklar</p>
        </div>
        <div className="loading-state">
          <div className="loading-spinner"></div>
          <p>Tahminler yükleniyor...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-container">
        <div className="page-header">
          <h1>Tahminler</h1>
          <p className="page-subtitle">Tüm tahminler ve olasılıklar</p>
        </div>
        <div className="error-state">
          <p className="error-message">{error}</p>
          <p className="error-hint">Backend sunucusunun çalıştığından emin olun.</p>
        </div>
      </div>
    );
  }

  // Filter predictions that have actual prediction data
  const availablePredictions = predictions.filter(p => p.prediction !== null);

  if (availablePredictions.length === 0) {
    return (
      <div className="page-container">
        <div className="page-header">
          <h1>Tahminler</h1>
          <p className="page-subtitle">Tüm tahminler ve olasılıklar</p>
        </div>
        <div className="empty-state">
          <div className="empty-icon">🎯</div>
          <p className="empty-title">Tahmin bulunamadı</p>
          <p className="empty-description">
            Şu anda mevcut tahmin bulunmamaktadır. Maçlar için tahminler oluşturuldukça burada görüntülenecektir.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>Tahminler</h1>
        <p className="page-subtitle">
          Tüm tahminler ve olasılıklar
          {isDevelopmentData && (
            <span className="dev-badge">Geliştirme Verisi</span>
          )}
        </p>
      </div>

      <div className="predictions-stats">
        <div className="stat-item">
          <span className="stat-item__label">Toplam Tahmin</span>
          <span className="stat-item__value">{availablePredictions.length}</span>
        </div>
        <div className="stat-item">
          <span className="stat-item__label">Kolay Maç</span>
          <span className="stat-item__value">
            {availablePredictions.filter(p => p.prediction?.easy_match?.is_easy_match).length}
          </span>
        </div>
      </div>

      <div className="predictions-list">
        {availablePredictions.map(({ match, prediction }) => {
          if (!prediction) return null;

          const dateTime = formatMatchDateTime(match.scheduled_at);
          const homeTeam = formatTeamName(match.home_team_id);
          const awayTeam = formatTeamName(match.away_team_id);
          const competition = formatCompetitionName(match.competition_id);

          // Find markets
          const matchResultMarket = prediction.market_analysis?.find(m => m.market_type === 'match_result');
          const bttsMarket = prediction.market_analysis?.find(m => m.market_type === 'btts');
          const over15Market = prediction.market_analysis?.find(m => m.market_type === 'OVER_UNDER_1_5');
          const over25Market = prediction.market_analysis?.find(m => m.market_type === 'OVER_UNDER_2_5');
          const over35Market = prediction.market_analysis?.find(m => m.market_type === 'OVER_UNDER_3_5');
          const over25AndBttsMarket = prediction.market_analysis?.find(m => m.market_type === 'OVER_2_5_AND_BTTS');

          return (
            <Link
              key={match.id}
              to={`/matches/${match.id}`}
              className="prediction-card"
            >
              {/* Card Header */}
              <div className="prediction-card__header">
                <div className="prediction-card__match-info">
                  <div className="prediction-card__competition">
                    {competition}
                    {match.round && ` - ${match.round}. Hafta`}
                  </div>
                  <div className="prediction-card__datetime">
                    {dateTime.date} · {dateTime.time}
                  </div>
                </div>
                {prediction.easy_match?.is_easy_match && (
                  <span className="easy-match-badge">✅ Kolay Maç</span>
                )}
              </div>

              {/* Teams */}
              <div className="prediction-card__teams">
                <span className="team-name">{homeTeam}</span>
                <span className="vs-separator">vs</span>
                <span className="team-name">{awayTeam}</span>
              </div>

              {/* Main Prediction - 1X2 */}
              <div className="prediction-card__main">
                <div className="prediction-main-header">
                  <span className="prediction-market-label">Maç Sonucu</span>
                  {prediction.easy_match && (
                    <ConfidenceIndicator
                      confidence={prediction.easy_match.confidence_score}
                      showLabel={false}
                    />
                  )}
                </div>
                <div className="prediction-outcomes">
                  <div className="prediction-outcome-compact">
                    <div className="outcome-label">Ev Sahibi</div>
                    <ProbabilityDisplay probability={prediction.home_win_probability} />
                    {matchResultMarket?.outcomes[0] && (
                      <div className="outcome-odds">
                        {matchResultMarket.outcomes[0].fair_odds.toFixed(2)}
                      </div>
                    )}
                  </div>
                  <div className="prediction-outcome-compact">
                    <div className="outcome-label">Beraberlik</div>
                    <ProbabilityDisplay probability={prediction.draw_probability} />
                    {matchResultMarket?.outcomes[1] && (
                      <div className="outcome-odds">
                        {matchResultMarket.outcomes[1].fair_odds.toFixed(2)}
                      </div>
                    )}
                  </div>
                  <div className="prediction-outcome-compact">
                    <div className="outcome-label">Deplasman</div>
                    <ProbabilityDisplay probability={prediction.away_win_probability} />
                    {matchResultMarket?.outcomes[2] && (
                      <div className="outcome-odds">
                        {matchResultMarket.outcomes[2].fair_odds.toFixed(2)}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Additional Markets */}
              <div className="prediction-card__markets">
                {/* xG */}
                <div className="market-item">
                  <div className="market-item__label">Beklenen Goller</div>
                  <div className="market-item__value">
                    {prediction.home_xg.toFixed(1)} - {prediction.away_xg.toFixed(1)}
                  </div>
                </div>

                {/* BTTS */}
                {bttsMarket && (
                  <div className="market-item">
                    <div className="market-item__label">KG Var</div>
                    <div className="market-item__value">
                      {bttsMarket.outcomes[0] && (
                        <>
                          <ProbabilityDisplay
                            probability={bttsMarket.outcomes[0].model_probability}
                            showIcon={false}
                          />
                          <span className="market-odds">
                            {bttsMarket.outcomes[0].fair_odds.toFixed(2)}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                )}

                {/* Over/Under 1.5 */}
                {over15Market && (
                  <div className="market-item">
                    <div className="market-item__label">Ü/A 1.5</div>
                    <div className="market-item__value">
                      {over15Market.outcomes.find(o => o.label.includes('Over')) && (
                        <>
                          <ProbabilityDisplay
                            probability={over15Market.outcomes.find(o => o.label.includes('Over'))!.model_probability}
                            showIcon={false}
                          />
                          <span className="market-odds">
                            {over15Market.outcomes.find(o => o.label.includes('Over'))!.fair_odds?.toFixed(2)}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                )}

                {/* Over/Under 2.5 */}
                {over25Market && (
                  <div className="market-item">
                    <div className="market-item__label">Ü/A 2.5</div>
                    <div className="market-item__value">
                      {over25Market.outcomes.find(o => o.label.includes('Over')) && (
                        <>
                          <ProbabilityDisplay
                            probability={over25Market.outcomes.find(o => o.label.includes('Over'))!.model_probability}
                            showIcon={false}
                          />
                          <span className="market-odds">
                            {over25Market.outcomes.find(o => o.label.includes('Over'))!.fair_odds?.toFixed(2)}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                )}

                {/* Over/Under 3.5 */}
                {over35Market && (
                  <div className="market-item">
                    <div className="market-item__label">Ü/A 3.5</div>
                    <div className="market-item__value">
                      {over35Market.outcomes.find(o => o.label.includes('Over')) && (
                        <>
                          <ProbabilityDisplay
                            probability={over35Market.outcomes.find(o => o.label.includes('Over'))!.model_probability}
                            showIcon={false}
                          />
                          <span className="market-odds">
                            {over35Market.outcomes.find(o => o.label.includes('Over'))!.fair_odds?.toFixed(2)}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                )}

                {/* Combined Market: Over 2.5 + BTTS */}
                {over25AndBttsMarket && (
                  <div className="market-item">
                    <div className="market-item__label">2.5 Ü + KG Var</div>
                    <div className="market-item__value">
                      {over25AndBttsMarket.outcomes.find(o => o.label.includes('Over 2.5 & Both Teams Score')) && (
                        <>
                          <ProbabilityDisplay
                            probability={over25AndBttsMarket.outcomes.find(o => o.label.includes('Over 2.5 & Both Teams Score'))!.model_probability}
                            showIcon={false}
                          />
                          <span className="market-odds">
                            {over25AndBttsMarket.outcomes.find(o => o.label.includes('Over 2.5 & Both Teams Score'))!.fair_odds?.toFixed(2)}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Bookmaker Value - Only if available */}
              {matchResultMarket?.bookmaker_comparison && (
                <div className="prediction-card__value">
                  <span className="value-label">Bahis Değeri:</span>
                  <div className="value-indicators">
                    <BookmakerValueList comparisons={matchResultMarket.bookmaker_comparison} />
                  </div>
                </div>
              )}

              {/* Data quality warning */}
              {prediction.easy_match && !prediction.easy_match.data_sufficient && (
                <div className="prediction-card__warning">
                  ⚠️ Yetersiz veri
                </div>
              )}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
