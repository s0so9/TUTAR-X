/**
 * LiveShotIntelligence Component
 * 
 * Displays shot map visualization when coordinate data available.
 * Falls back to shot list when coordinates unavailable.
 * Shows xG, outcome, player info for each shot.
 */

import type { LiveShot } from '../../types/live';
import './LiveShotIntelligence.css';

interface LiveShotIntelligenceProps {
  /** Home team name */
  homeTeam: string;
  /** Away team name */
  awayTeam: string;
  /** Array of shots */
  shots: LiveShot[];
  /** Whether coordinate data is available */
  hasCoordinates: boolean;
  /** Loading state */
  isLoading?: boolean;
}

export default function LiveShotIntelligence({
  homeTeam,
  awayTeam,
  shots,
  hasCoordinates,
  isLoading = false
}: LiveShotIntelligenceProps) {
  if (isLoading) {
    return (
      <div className="live-shot-intelligence" aria-busy="true">
        <div className="live-shot-intelligence__header">
          <div className="skeleton skeleton--title"></div>
        </div>
        <div className="skeleton skeleton--content"></div>
      </div>
    );
  }

  const homeShots = shots.filter((s) => s.team === 'home');
  const awayShots = shots.filter((s) => s.team === 'away');

  return (
    <div className="live-shot-intelligence">
      <div className="live-shot-intelligence__header">
        <h3 className="live-shot-intelligence__title">Şut İstihbaratı</h3>
        {!hasCoordinates && shots.length > 0 && (
          <span className="data-quality-badge data-quality-badge--limited">
            Konum verisi mevcut değil
          </span>
        )}
      </div>

      {shots.length === 0 ? (
        <div className="live-shot-intelligence__empty">
          <p className="empty-text">Henüz şut kaydedilmedi</p>
        </div>
      ) : hasCoordinates ? (
        <ShotMap homeTeam={homeTeam} awayTeam={awayTeam} homeShots={homeShots} awayShots={awayShots} />
      ) : (
        <ShotList homeTeam={homeTeam} awayTeam={awayTeam} homeShots={homeShots} awayShots={awayShots} />
      )}
    </div>
  );
}

/**
 * ShotMap - Visual pitch representation (when coordinates available)
 */
function ShotMap({
  homeTeam,
  awayTeam,
  homeShots,
  awayShots
}: {
  homeTeam: string;
  awayTeam: string;
  homeShots: LiveShot[];
  awayShots: LiveShot[];
}) {
  return (
    <div className="shot-map">
      <div className="shot-map__legend">
        <div className="legend-item">
          <span className="legend-marker legend-marker--goal"></span>
          <span className="legend-label">Gol</span>
        </div>
        <div className="legend-item">
          <span className="legend-marker legend-marker--on-target"></span>
          <span className="legend-label">İsabetli</span>
        </div>
        <div className="legend-item">
          <span className="legend-marker legend-marker--off-target"></span>
          <span className="legend-label">Dışarı</span>
        </div>
        <div className="legend-item">
          <span className="legend-marker legend-marker--blocked"></span>
          <span className="legend-label">Bloke</span>
        </div>
      </div>

      <div className="shot-map__pitch">
        <div className="pitch-half pitch-half--home" aria-label={`${homeTeam} yarı sahası`}>
          {homeShots.map((shot) => (
            <ShotMarker key={shot.shotId} shot={shot} />
          ))}
        </div>
        <div className="pitch-half pitch-half--away" aria-label={`${awayTeam} yarı sahası`}>
          {awayShots.map((shot) => (
            <ShotMarker key={shot.shotId} shot={shot} />
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * ShotMarker - Individual shot on pitch map
 */
function ShotMarker({ shot }: { shot: LiveShot }) {
  if (shot.x === undefined || shot.y === undefined) return null;

  const outcomeClass = `shot-marker--${shot.outcome.toLowerCase().replace('_', '-')}`;
  const title = `${shot.player?.name || 'Unknown'} - ${shot.minute}' - xG: ${shot.xG?.toFixed(2) || '—'}`;

  return (
    <div
      className={`shot-marker ${outcomeClass} ${shot.isBigChance ? 'shot-marker--big-chance' : ''}`}
      style={{
        left: `${shot.x}%`,
        top: `${shot.y}%`
      }}
      title={title}
      role="img"
      aria-label={title}
    ></div>
  );
}

/**
 * ShotList - Tabular shot list (when no coordinates)
 */
function ShotList({
  homeTeam,
  awayTeam,
  homeShots,
  awayShots
}: {
  homeTeam: string;
  awayTeam: string;
  homeShots: LiveShot[];
  awayShots: LiveShot[];
}): JSX.Element {
  const allShots = [...homeShots, ...awayShots].sort((a, b) => {
    const aTotal = a.minute + (a.addedTime || 0);
    const bTotal = b.minute + (b.addedTime || 0);
    return bTotal - aTotal; // Most recent first
  });

  return (
    <div className="shot-list">
      <div className="shot-list__teams">
        <div className="shot-list__team">{homeTeam}</div>
        <div className="shot-list__team">{awayTeam}</div>
      </div>

      <div className="shot-list__items">
        {allShots.map((shot) => (
          <ShotListItem key={shot.shotId} shot={shot} />
        ))}
      </div>
    </div>
  );
}

/**
 * ShotListItem - Single shot in list view
 */
function ShotListItem({
  shot
}: {
  shot: LiveShot;
}) {
  const minute = shot.addedTime ? `${shot.minute}+${shot.addedTime}'` : `${shot.minute}'`;
  const outcomeLabel = {
    GOAL: '⚽ Gol',
    ON_TARGET: '🎯 İsabetli',
    OFF_TARGET: '❌ Dışarı',
    BLOCKED: '🛑 Bloke'
  }[shot.outcome];

  return (
    <div className={`shot-list-item shot-list-item--${shot.team}`}>
      <div className="shot-list-item__time">{minute}</div>
      <div className="shot-list-item__player">
        {shot.player?.name || 'Bilinmeyen Oyuncu'}
        {shot.player?.shirtNumber && (
          <span className="shot-list-item__number">#{shot.player.shirtNumber}</span>
        )}
      </div>
      <div className={`shot-list-item__outcome shot-list-item__outcome--${shot.outcome.toLowerCase()}`}>
        {outcomeLabel}
      </div>
      {shot.xG !== undefined && (
        <div className="shot-list-item__xg">xG: {shot.xG.toFixed(2)}</div>
      )}
      {shot.isBigChance && (
        <span className="big-chance-badge">Büyük Fırsat</span>
      )}
    </div>
  );
}
