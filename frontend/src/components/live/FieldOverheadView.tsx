/**
 * FieldOverheadView Component
 * 
 * PHASE 8 - Kuşbakışı Canlı Maç Takibi
 * 
 * Displays overhead field view for live matches.
 * Shows shot events, goals, and key match events on a football pitch representation.
 * Prepared for future coordinate data when providers support player/ball tracking.
 */
import './FieldOverheadView.css';

interface MatchEvent {
  id: string;
  type: 'goal' | 'shot' | 'card' | 'substitution' | 'corner' | 'penalty';
  minute: number;
  team: 'home' | 'away';
  player?: string;
  coordinates?: { x: number; y: number };
  description?: string;
}

interface PlayerPosition {
  playerId: string;
  playerName?: string;
  team: 'home' | 'away';
  x: number; // 0-120 meters
  y: number; // 0-80 meters
  timestamp: Date;
}

interface BallPosition {
  x: number; // 0-120 meters  
  y: number; // 0-80 meters
  z?: number; // height
  timestamp: Date;
}

interface FieldOverheadViewProps {
  /** Live match events */
  events: MatchEvent[];
  /** Player positions (optional, for future provider support) */
  playerPositions?: PlayerPosition[];
  /** Ball position (optional, for future provider support) */
  ballPosition?: BallPosition;
  /** Field dimensions in meters */
  fieldDimensions?: { length: number; width: number };
  /** Data availability flags */
  dataQuality: {
    has_events: boolean;
    has_shot_coordinates: boolean;
    has_player_positions: boolean;
    has_ball_tracking: boolean;
  };
  /** Match teams */
  homeTeam: string;
  awayTeam: string;
}

export default function FieldOverheadView({
  events,
  playerPositions,
  ballPosition,
  fieldDimensions = { length: 105, width: 68 }, // Standard FIFA pitch
  dataQuality,
  homeTeam,
  awayTeam,
}: FieldOverheadViewProps) {
  
  // Convert field coordinates to SVG coordinates
  const fieldToSvg = (x: number, y: number) => {
    // Field: 0-105m length, 0-68m width
    // SVG: 0-800 width, 0-520 height (preserving aspect ratio)
    const svgX = (x / fieldDimensions.length) * 800;
    const svgY = (y / fieldDimensions.width) * 520;
    return { x: svgX, y: svgY };
  };

  const renderEvent = (event: MatchEvent, index: number) => {
    if (!event.coordinates) return null;
    
    const { x, y } = fieldToSvg(event.coordinates.x, event.coordinates.y);
    const isHomeTeam = event.team === 'home';
    
    let eventColor = '#666';
    let eventIcon = '⚽';
    
    switch (event.type) {
      case 'goal':
        eventColor = '#22c55e';
        eventIcon = '⚽';
        break;
      case 'shot':
        eventColor = '#f59e0b';
        eventIcon = '🎯';
        break;
      case 'card':
        eventColor = '#ef4444';
        eventIcon = '🟨';
        break;
      case 'corner':
        eventColor = '#3b82f6';
        eventIcon = '📐';
        break;
      case 'penalty':
        eventColor = '#dc2626';
        eventIcon = '⚽';
        break;
    }

    return (
      <g key={event.id || index} className={`field-event field-event--${event.type}`}>
        <circle
          cx={x}
          cy={y}
          r="8"
          fill={eventColor}
          stroke={isHomeTeam ? '#1e40af' : '#dc2626'}
          strokeWidth="2"
          className="field-event__marker"
        />
        <text
          x={x}
          y={y + 3}
          textAnchor="middle"
          fontSize="12"
          fill="white"
          className="field-event__icon"
        >
          {eventIcon}
        </text>
        <title>{`${event.minute}' ${event.type} - ${event.player || event.team}`}</title>
      </g>
    );
  };

  const renderPlayerPositions = () => {
    if (!playerPositions || playerPositions.length === 0) return null;
    
    return playerPositions.map((player, index) => {
      const { x, y } = fieldToSvg(player.x, player.y);
      const isHomeTeam = player.team === 'home';
      
      return (
        <g key={player.playerId || index} className="field-player">
          <circle
            cx={x}
            cy={y}
            r="6"
            fill={isHomeTeam ? '#1e40af' : '#dc2626'}
            stroke="white"
            strokeWidth="1"
            className="field-player__marker"
          />
          <title>{player.playerName || player.playerId}</title>
        </g>
      );
    });
  };

  const renderBall = () => {
    if (!ballPosition) return null;
    
    const { x, y } = fieldToSvg(ballPosition.x, ballPosition.y);
    
    return (
      <g className="field-ball">
        <circle
          cx={x}
          cy={y}
          r="4"
          fill="#ffffff"
          stroke="#000000"
          strokeWidth="1"
          className="field-ball__marker"
        />
      </g>
    );
  };

  const renderDataStatus = () => {
    const availableData = [];
    if (dataQuality.has_events) availableData.push('Olaylar');
    if (dataQuality.has_shot_coordinates) availableData.push('Şut Koordinatları');
    if (dataQuality.has_player_positions) availableData.push('Oyuncu Pozisyonları');
    if (dataQuality.has_ball_tracking) availableData.push('Top Takibi');

    return (
      <div className="field-data-status">
        <div className="field-data-status__title">Mevcut Veri:</div>
        <div className="field-data-status__items">
          {availableData.length > 0 ? (
            availableData.map((item, index) => (
              <span key={index} className="field-data-status__item field-data-status__item--available">
                ✓ {item}
              </span>
            ))
          ) : (
            <span className="field-data-status__item field-data-status__item--unavailable">
              Koordinat verisi mevcut değil
            </span>
          )}
        </div>
      </div>
    );
  };

  // Filter events that have coordinates for rendering on field
  const eventsWithCoordinates = events.filter(event => event.coordinates);

  return (
    <div className="field-overhead-view">
      <div className="field-overhead-view__header">
        <h3 className="field-overhead-view__title">Saha Görünümü</h3>
        <div className="field-overhead-view__teams">
          <span className="field-team field-team--home">{homeTeam}</span>
          <span className="field-team field-team--away">{awayTeam}</span>
        </div>
      </div>

      <div className="field-overhead-view__container">
        <svg
          viewBox="0 0 800 520"
          className="field-svg"
          xmlns="http://www.w3.org/2000/svg"
        >
          {/* Football pitch background */}
          <defs>
            <pattern id="grass" patternUnits="userSpaceOnUse" width="20" height="20">
              <rect width="20" height="20" fill="#16a34a"/>
              <rect width="20" height="20" fill="#15803d" opacity="0.1"/>
            </pattern>
          </defs>
          
          {/* Main pitch */}
          <rect
            x="0"
            y="0"
            width="800"
            height="520"
            fill="url(#grass)"
            stroke="#ffffff"
            strokeWidth="3"
            className="field-pitch"
          />
          
          {/* Center line */}
          <line x1="400" y1="0" x2="400" y2="520" stroke="white" strokeWidth="2" />
          
          {/* Center circle */}
          <circle cx="400" cy="260" r="73" fill="none" stroke="white" strokeWidth="2" />
          <circle cx="400" cy="260" r="2" fill="white" />
          
          {/* Goals and penalty areas */}
          {/* Home goal (left) */}
          <rect x="0" y="180" width="44" height="160" fill="none" stroke="white" strokeWidth="2" />
          <rect x="0" y="220" width="14" height="80" fill="none" stroke="white" strokeWidth="2" />
          <rect x="0" y="240" width="7" height="40" fill="white" strokeWidth="2" />
          
          {/* Away goal (right) */}
          <rect x="756" y="180" width="44" height="160" fill="none" stroke="white" strokeWidth="2" />
          <rect x="786" y="220" width="14" height="80" fill="none" stroke="white" strokeWidth="2" />
          <rect x="793" y="240" width="7" height="40" fill="white" strokeWidth="2" />
          
          {/* Corner arcs */}
          <path d="M 0 0 A 20 20 0 0 0 20 20" fill="none" stroke="white" strokeWidth="2" />
          <path d="M 780 0 A 20 20 0 0 1 800 20" fill="none" stroke="white" strokeWidth="2" />
          <path d="M 0 520 A 20 20 0 0 1 20 500" fill="none" stroke="white" strokeWidth="2" />
          <path d="M 800 520 A 20 20 0 0 0 780 500" fill="none" stroke="white" strokeWidth="2" />

          {/* Render match events */}
          {eventsWithCoordinates.map(renderEvent)}
          
          {/* Render player positions (if available) */}
          {renderPlayerPositions()}
          
          {/* Render ball position (if available) */}
          {renderBall()}
        </svg>

        {/* Event legend */}
        <div className="field-legend">
          <div className="field-legend__title">Olay Türleri:</div>
          <div className="field-legend__items">
            <div className="field-legend__item">
              <span className="field-legend__marker field-legend__marker--goal">⚽</span>
              <span>Gol</span>
            </div>
            <div className="field-legend__item">
              <span className="field-legend__marker field-legend__marker--shot">🎯</span>
              <span>Şut</span>
            </div>
            <div className="field-legend__item">
              <span className="field-legend__marker field-legend__marker--corner">📐</span>
              <span>Korner</span>
            </div>
            <div className="field-legend__item">
              <span className="field-legend__marker field-legend__marker--penalty">⚽</span>
              <span>Penaltı</span>
            </div>
          </div>
        </div>
      </div>

      {renderDataStatus()}
    </div>
  );
}