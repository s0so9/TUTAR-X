/**
 * SquadStatus Component ("Kadro Durumu")
 *
 * Shows, per team, the starting-XI market value and the unavailable players
 * (injured / suspended) supplied by the backend in prediction.squad_info
 * (source: FotMob). Values are displayed as supplied; missing data is shown
 * explicitly ("Kadro verisi yok" / "veri yok").
 */

import type { SquadInfoResponse, SquadTeamInfoResponse } from '../../api/types'
import { UnavailableValue } from '../ui'
import {
  describeAbsenceReason,
  describeExpectedReturn,
  formatMarketValueEur,
  isPredictedLineup,
} from '../../utils/squadInfo'
import './SquadStatus.css'

interface SquadStatusProps {
  squadInfo: SquadInfoResponse | null | undefined
  /** Fallback team names when the provider omits them */
  homeTeam: string
  awayTeam: string
}

function sourceLabel(source: string | null | undefined): string {
  if (!source) return 'veri yok'
  return source.trim().toLowerCase() === 'fotmob' ? 'FotMob' : source
}

function reasonModifier(reason: string | null | undefined): string {
  const key = (reason ?? '').trim().toLowerCase()
  if (key === 'injury' || key === 'injured') return 'injury'
  if (key === 'suspension' || key === 'suspended') return 'suspension'
  return 'other'
}

function TeamSquad({
  team,
  fallbackName,
  side,
}: {
  team: SquadTeamInfoResponse
  fallbackName: string
  side: 'home' | 'away'
}) {
  const name = team.team_name || fallbackName
  // null = no injury report from the source (e.g. finished matches) — not "nobody missing"
  const unavailable = Array.isArray(team.unavailable) ? team.unavailable : null

  return (
    <div className={`squad-team squad-team--${side}`} data-testid={`squad-team-${side}`}>
      <div className="squad-team__header">
        <div className="squad-team__name">{name}</div>
        <div className="squad-team__value">
          <span className="squad-team__value-label">İlk 11 piyasa değeri</span>
          <span className="squad-team__value-amount">
            <UnavailableValue value={formatMarketValueEur(team.starter_value)} />
          </span>
          {isPredictedLineup(team.lineup_type) && (
            <span className="squad-team__lineup-hint">(tahmini kadro)</span>
          )}
        </div>
      </div>

      <div className="squad-team__absent-title">
        Eksik oyuncular{' '}
        <span className="squad-team__absent-count">({unavailable ? unavailable.length : 'veri yok'})</span>
      </div>
      {unavailable === null ? (
        <p className="squad-team__empty">Eksik oyuncu verisi yok</p>
      ) : unavailable.length === 0 ? (
        <p className="squad-team__empty">Bildirilen eksik oyuncu yok</p>
      ) : (
        <ul className="squad-team__absent-list">
          {unavailable.map((player, idx) => (
            <li key={`${player.name}-${idx}`} className="squad-player">
              <div className="squad-player__main">
                <span className="squad-player__name">{player.name}</span>
                <span className={`squad-player__reason squad-player__reason--${reasonModifier(player.reason)}`}>
                  {describeAbsenceReason(player.reason)}
                </span>
              </div>
              <div className="squad-player__meta">
                <span className="squad-player__return">
                  Dönüş: <UnavailableValue value={describeExpectedReturn(player.expected_return)} />
                </span>
                <span className="squad-player__value">
                  <UnavailableValue value={formatMarketValueEur(player.market_value)} />
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function SquadStatus({ squadInfo, homeTeam, awayTeam }: SquadStatusProps) {
  return (
    <section className="squad-status" aria-labelledby="squad-status-title">
      <h4 id="squad-status-title" className="squad-status__title">Kadro Durumu</h4>
      {!squadInfo || !squadInfo.home || !squadInfo.away ? (
        <p className="squad-status__empty">Kadro verisi yok</p>
      ) : (
        <>
          <div className="squad-status__grid">
            <TeamSquad team={squadInfo.home} fallbackName={homeTeam} side="home" />
            <TeamSquad team={squadInfo.away} fallbackName={awayTeam} side="away" />
          </div>
          <p className="squad-status__footnote">Kaynak: {sourceLabel(squadInfo.source)}</p>
        </>
      )}
    </section>
  )
}
