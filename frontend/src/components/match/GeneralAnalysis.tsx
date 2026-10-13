/**
 * GeneralAnalysis Component
 *
 * Displays general match analysis including primary TUTAR X PICK,
 * predicted score, 1X2 probabilities, xG, BTTS, and key indicators.
 */

import MensionePickCard from '../predictions/MensionePickCard'
import ProbabilityDisplay from '../common/ProbabilityDisplay'
import type {
  MatchPredictionResponse,
  MatchResponse,
  ShotMarketPrediction,
  ShotMarketThreshold
} from '../../api/types'
import { describePickMarket } from '../../utils/pickMarket'
import './GeneralAnalysis.css'

interface GeneralAnalysisProps {
  /** Match prediction data */
  prediction: MatchPredictionResponse
  /** Match data */
  match: MatchResponse
  /** Home team name (formatted) */
  homeTeam: string
  /** Away team name (formatted) */
  awayTeam: string
  /** Whether this match is favorited */
  isFavorite: boolean
  /** Callback when favorite is toggled */
  onToggleFavorite: () => void
  /** Whether this match is in combine */
  inCombine: boolean
  /** Callback when the primary pick is added to / removed from the combine (parsed Turkish market + outcome) */
  onToggleCombine: (selection: { marketName: string; outcome: string }) => void
}

export default function GeneralAnalysis({
  prediction,
  homeTeam,
  awayTeam,
  isFavorite,
  onToggleFavorite,
  inCombine,
  onToggleCombine
}: GeneralAnalysisProps) {
  const { mensione_pick } = prediction

  // Parse TUTAR X pick if available
  let mensioneMarket = ''
  let mensioneOutcome = ''
  if (mensione_pick) {
    const parsed = describePickMarket(mensione_pick.market, mensione_pick.selection, {
      home: homeTeam,
      away: awayTeam
    })
    mensioneMarket = parsed.marketName
    mensioneOutcome = parsed.outcome
  }

  return (
    <div className="general-analysis">
      {/* Primary TUTAR X PICK - Prominent placement at top */}
      {mensione_pick && (
        <section className="general-analysis__primary-pick">
          <MensionePickCard
            homeTeam={homeTeam}
            awayTeam={awayTeam}
            marketName={mensioneMarket}
            outcome={mensioneOutcome}
            confidence={mensione_pick.confidence ?? null}
            realOdds={mensione_pick.bookmaker_odds ?? null}
            isFavorite={isFavorite}
            onToggleFavorite={onToggleFavorite}
            inCombine={inCombine}
            onToggleCombine={() => onToggleCombine({ marketName: mensioneMarket, outcome: mensioneOutcome })}
            predictedScore={prediction.predicted_score ?? null}
            homeXg={prediction.home_xg}
            awayXg={prediction.away_xg}
            bttsProbability={prediction.btts_probability}
            homeWinProbability={prediction.home_win_probability}
            drawProbability={prediction.draw_probability}
            awayWinProbability={prediction.away_win_probability}
            pickProbability={mensione_pick.probability ?? null}
            reasoningFactors={mensione_pick.selector_reason ? [mensione_pick.selector_reason] : []}
            scoreDistributionTop5={[]}
            fairOdds={mensione_pick.fair_odds ?? null}
            marketOdds={mensione_pick.bookmaker_odds ?? null}
            predictionVersionId={prediction.prediction_version_id}
            valueClassification={mensione_pick.value_classification ?? null}
            oddsSource={mensione_pick.odds_source ?? null}
          />
        </section>
      )}

      {/* Predicted Score */}
      {prediction.predicted_score && (
        <section className="general-analysis__predicted-score">
          <h4 className="general-analysis__section-title">Tahmini Skor</h4>
          <div className="predicted-score-display">
            {prediction.predicted_score}
          </div>
        </section>
      )}

      {/* 1X2 Probabilities */}
      <section className="general-analysis__probabilities">
        <h4 className="general-analysis__section-title">Maç Sonucu Olasılıkları</h4>
        <div className="probabilities-grid">
          <div className="probability-outcome">
            <div className="probability-outcome__label">{homeTeam} Kazanır</div>
            <ProbabilityDisplay
              probability={prediction.home_win_probability}
              large={true}
              showIcon={true}
            />
          </div>
          <div className="probability-outcome">
            <div className="probability-outcome__label">Beraberlik</div>
            <ProbabilityDisplay
              probability={prediction.draw_probability}
              large={true}
              showIcon={true}
            />
          </div>
          <div className="probability-outcome">
            <div className="probability-outcome__label">{awayTeam} Kazanır</div>
            <ProbabilityDisplay
              probability={prediction.away_win_probability}
              large={true}
              showIcon={true}
            />
          </div>
        </div>
      </section>

      {/* Expected Goals (xG) */}
      <section className="general-analysis__xg">
        <h4 className="general-analysis__section-title">Beklenen Goller (xG)</h4>
        <div className="xg-display">
          <div className="xg-team xg-team--home">
            <div className="xg-team__name">{homeTeam}</div>
            <div className="xg-team__value">{prediction.home_xg.toFixed(2)}</div>
          </div>
          <div className="xg-separator">-</div>
          <div className="xg-team xg-team--away">
            <div className="xg-team__value">{prediction.away_xg.toFixed(2)}</div>
            <div className="xg-team__name">{awayTeam}</div>
          </div>
        </div>
      </section>

      {/* BTTS Probability */}
      <section className="general-analysis__btts">
        <h4 className="general-analysis__section-title">Karşılıklı Gol (BTTS)</h4>
        <div className="btts-display">
          <div className="btts-outcome">
            <span className="btts-outcome__label">Evet</span>
            <ProbabilityDisplay
              probability={prediction.btts_probability}
              large={false}
              showIcon={false}
            />
          </div>
          <div className="btts-outcome">
            <span className="btts-outcome__label">Hayır</span>
            <ProbabilityDisplay
              probability={1 - prediction.btts_probability}
              large={false}
              showIcon={false}
            />
          </div>
        </div>
      </section>

      {/* Shot Markets */}
      {prediction.shot_markets && Object.keys(prediction.shot_markets).length > 0 && (
        <section className="general-analysis__shot-markets">
          <h4 className="general-analysis__section-title">Şut Marketleri</h4>
          <div className="shot-markets-grid">
            {Object.entries(prediction.shot_markets).map(([marketType, predictions]) => {
              if (!Array.isArray(predictions) || predictions.length === 0) return null;

              return (
                <div key={marketType} className="shot-market-group">
                  <div className="shot-market-group__title">
                    {marketType === 'team_shots' ? 'Takım Şutları' :
                     marketType === 'team_shots_on_target' ? 'Takım İsabetli Şutları' :
                     marketType === 'total_shots' ? 'Toplam Şutlar' :
                     marketType === 'total_sot' ? 'Toplam İsabetli Şutlar' : marketType}
                  </div>
                  <div className="shot-market-predictions">
                    {predictions.map((pred: ShotMarketPrediction, index: number) => (
                      <div key={index} className="shot-prediction">
                        <div className="shot-prediction__team">
                          {pred.team_id === 'total' ? 'Toplam' :
                           pred.team_id === prediction.match_id?.split('-')[0] ? homeTeam : awayTeam}
                        </div>
                        {pred.available ? (
                          <div className="shot-prediction__thresholds">
                            {pred.thresholds?.map((threshold: ShotMarketThreshold, tIndex: number) => (
                              <div key={tIndex} className="shot-threshold">
                                <span className="shot-threshold__label">{threshold.threshold}+</span>
                                <ProbabilityDisplay
                                  probability={threshold.over_probability}
                                  large={false}
                                  showIcon={false}
                                />
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="shot-prediction__unavailable">
                            Veri yetersiz
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Key Indicators from selector reason */}
      {mensione_pick?.selector_reason && (
        <section className="general-analysis__key-indicators">
          <h4 className="general-analysis__section-title">Seçim Nedeni</h4>
          <ul className="key-indicators-list">
            <li className="key-indicator">
              <span className="key-indicator__icon">→</span>
              <span className="key-indicator__text">{mensione_pick.selector_reason}</span>
            </li>
          </ul>
        </section>
      )}
    </div>
  )
}
