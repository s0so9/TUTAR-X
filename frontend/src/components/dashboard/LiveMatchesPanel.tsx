/**
 * LiveMatchesPanel Component
 * 
 * Left panel displaying live matches on desktop.
 * Handles empty state when no live matches available.
 * Prepared for future real live data integration.
 */

import LiveMatchCard from './LiveMatchCard';
import './LiveMatchesPanel.css';

export interface LiveMatch {
  matchId: string;
  homeTeam: string;
  awayTeam: string;
  score: {
    home: number;
    away: number;
  };
  minute: number;
  status: 'live' | 'ht' | 'ft';
  liveStats?: {
    shots?: number;
    shotsOnTarget?: number;
    corners?: number;
    possession?: number;
  };
}

interface LiveMatchesPanelProps {
  /** Array of live matches */
  liveMatches: LiveMatch[];
  /** Loading state */
  isLoading?: boolean;
}

export default function LiveMatchesPanel({
  liveMatches,
  isLoading = false,
}: LiveMatchesPanelProps) {
  return (
    <aside className="live-matches-panel" aria-label="Canlı maçlar">
      <div className="live-matches-panel__header">
        <h2 className="live-matches-panel__title">
          <span className="live-indicator">
            <span className="live-indicator__dot"></span>
            <span className="live-indicator__text">CANLI</span>
          </span>
        </h2>
        {liveMatches.length > 0 && (
          <span className="live-matches-panel__count">{liveMatches.length}</span>
        )}
      </div>

      <div className="live-matches-panel__content">
        {isLoading ? (
          <>
            <LiveMatchCard
              homeTeam=""
              awayTeam=""
              score={{ home: 0, away: 0 }}
              minute={0}
              status="live"
              isLoading={true}
            />
            <LiveMatchCard
              homeTeam=""
              awayTeam=""
              score={{ home: 0, away: 0 }}
              minute={0}
              status="live"
              isLoading={true}
            />
          </>
        ) : liveMatches.length === 0 ? (
          null
        ) : (
          liveMatches.map((match) => (
            <LiveMatchCard
              key={match.matchId}
              homeTeam={match.homeTeam}
              awayTeam={match.awayTeam}
              score={match.score}
              minute={match.minute}
              status={match.status}
              liveStats={match.liveStats}
            />
          ))
        )}
      </div>
    </aside>
  );
}
