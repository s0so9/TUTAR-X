/**
 * LiveScoreboard Component
 * 
 * Displays live match score with team names, logos, current minute,
 * and match period. Handles loading and unavailable states.
 */

import { MatchPeriod } from '../../types/live';
import './LiveScoreboard.css';

interface Team {
  id: string;
  name: string;
  code?: string;
  logo?: string;
}

interface LiveScoreboardProps {
  /** Home team */
  homeTeam?: Team;
  /** Away team */
  awayTeam?: Team;
  /** Home score */
  homeScore?: number;
  /** Away score */
  awayScore?: number;
  /** Match minute */
  minute?: number;
  /** Added time */
  addedTime?: number;
  /** Match period */
  period?: MatchPeriod;
  /** Loading state */
  isLoading?: boolean;
}

export default function LiveScoreboard({
  homeTeam,
  awayTeam,
  homeScore = 0,
  awayScore = 0,
  minute,
  addedTime,
  period,
  isLoading = false
}: LiveScoreboardProps) {
  if (isLoading) {
    return (
      <div className="live-scoreboard live-scoreboard--loading" aria-busy="true">
        <div className="live-scoreboard__content">
          <div className="live-scoreboard__team live-scoreboard__team--home">
            <div className="skeleton skeleton--logo"></div>
            <div className="skeleton skeleton--name"></div>
          </div>
          <div className="live-scoreboard__score">
            <div className="live-scoreboard__scores">
              <div className="skeleton skeleton--score"></div>
              <span className="live-scoreboard__separator">-</span>
              <div className="skeleton skeleton--score"></div>
            </div>
            <div className="skeleton skeleton--minute"></div>
          </div>
          <div className="live-scoreboard__team live-scoreboard__team--away">
            <div className="skeleton skeleton--logo"></div>
            <div className="skeleton skeleton--name"></div>
          </div>
        </div>
      </div>
    );
  }

  const periodLabel = period ? getPeriodLabel(period) : '—';
  const minuteDisplay = formatMinute(minute, addedTime);

  return (
    <div className="live-scoreboard">
      <div className="live-scoreboard__content">
        {/* Home Team */}
        <div className="live-scoreboard__team live-scoreboard__team--home">
          <div className="live-scoreboard__team-logo" aria-hidden="true">
            {homeTeam?.logo ? (
              <img src={homeTeam.logo} alt="" />
            ) : (
              '⚽'
            )}
          </div>
          <div>
            <div className="live-scoreboard__team-name">
              {homeTeam?.name || 'Ev Sahibi'}
            </div>
            {homeTeam?.code && (
              <div className="live-scoreboard__team-code">
                {homeTeam.code}
              </div>
            )}
          </div>
        </div>

        {/* Score */}
        <div className="live-scoreboard__score">
          <div className="live-scoreboard__scores">
            <span className="live-scoreboard__team-score" aria-label={`${homeTeam?.name || 'Ev sahibi'} skoru`}>
              {homeScore}
            </span>
            <span className="live-scoreboard__separator">-</span>
            <span className="live-scoreboard__team-score" aria-label={`${awayTeam?.name || 'Deplasman'} skoru`}>
              {awayScore}
            </span>
          </div>

          {/* Time */}
          <div className="live-scoreboard__time">
            <div className="live-scoreboard__minute" aria-label="Dakika">
              {minuteDisplay}
            </div>
            <div className="live-scoreboard__period" aria-label="Periyot">
              {periodLabel}
            </div>
          </div>
        </div>

        {/* Away Team */}
        <div className="live-scoreboard__team live-scoreboard__team--away">
          <div className="live-scoreboard__team-logo" aria-hidden="true">
            {awayTeam?.logo ? (
              <img src={awayTeam.logo} alt="" />
            ) : (
              '⚽'
            )}
          </div>
          <div>
            <div className="live-scoreboard__team-name">
              {awayTeam?.name || 'Deplasman'}
            </div>
            {awayTeam?.code && (
              <div className="live-scoreboard__team-code">
                {awayTeam.code}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Get Turkish period label
 */
function getPeriodLabel(period: MatchPeriod): string {
  const labels: Record<MatchPeriod, string> = {
    FIRST_HALF: '1. Yarı',
    HALF_TIME: 'Devre Arası',
    SECOND_HALF: '2. Yarı',
    EXTRA_TIME_FIRST: 'Uzatma 1',
    EXTRA_TIME_SECOND: 'Uzatma 2',
    PENALTIES: 'Penaltılar',
    FINISHED: 'Bitti'
  };

  return labels[period] || period;
}

/**
 * Format minute display with added time
 */
function formatMinute(minute?: number, addedTime?: number): string {
  if (minute === undefined) return '—';

  if (addedTime && addedTime > 0) {
    return `${minute}+${addedTime}'`;
  }

  return `${minute}'`;
}
