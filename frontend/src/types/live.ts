/**
 * Live Match TypeScript Contracts
 * All fields are optional to handle missing/unavailable data gracefully
 */

export type MatchStatusType = 'SCHEDULED' | 'LIVE' | 'HALF_TIME' | 'FINISHED' | 'POSTPONED' | 'CANCELLED' | 'SUSPENDED';
export type DataQualityLevel = 'HIGH' | 'MEDIUM' | 'LOW' | 'UNAVAILABLE';
export type ConnectionStatus = 'CONNECTED' | 'UPDATING' | 'DELAYED' | 'UNAVAILABLE';
export type MatchPeriod = 'FIRST_HALF' | 'HALF_TIME' | 'SECOND_HALF' | 'EXTRA_TIME_FIRST' | 'EXTRA_TIME_SECOND' | 'PENALTIES' | 'FINISHED';

/**
 * Live Match State
 * Core real-time match information
 */
export interface LiveMatchState {
  matchId: string;
  status: MatchStatusType;
  minute?: number;
  addedTime?: number;
  homeScore?: number;
  awayScore?: number;
  homeTeam?: {
    id: string;
    name: string;
    code?: string;
    logo?: string;
  };
  awayTeam?: {
    id: string;
    name: string;
    code?: string;
    logo?: string;
  };
  competition?: {
    id: string;
    name: string;
    country?: string;
    logo?: string;
  };
  venue?: string;
  period?: MatchPeriod;
  homeStats?: LiveStats;
  awayStats?: LiveStats;
  dataQuality?: DataQualityFlags;
}

/**
 * Data Quality Flags
 * Indicates what live data is available from provider
 */
export interface DataQualityFlags {
  has_xg?: boolean;
  has_events?: boolean;
  has_shots?: boolean;
  has_player_positions?: boolean;
  has_ball_tracking?: boolean;
  has_shot_coordinates?: boolean;
  has_live_statistics?: boolean;
}

/**
 * Live Statistics
 * All fields optional - display "—" or "Unavailable" when missing
 */
export interface LiveStats {
  // Attack
  shots?: number;
  shotsOnTarget?: number;
  shotsInsideBox?: number;
  shotsOutsideBox?: number;
  bigChances?: number;
  dangerousAttacks?: number;
  
  // Possession
  possession?: number;
  fieldTilt?: number;
  
  // Chance Quality
  xG?: number;
  xGPerShot?: number;
  bigChanceRate?: number;
  
  // Pressing
  ppda?: number;
  highTurnovers?: number;
  
  // Progression
  progressivePasses?: number;
  progressiveCarries?: number;
  boxEntries?: number;
  
  // Set Pieces & Discipline
  corners?: number;
  fouls?: number;
  offsides?: number;
  yellowCards?: number;
  redCards?: number;
  
  // Other
  passes?: number;
  passAccuracy?: number;
  tackles?: number;
  interceptions?: number;
  saves?: number;
}

/**
 * Live Event
 * Match timeline events (goals, cards, subs, VAR, etc.)
 */
export interface LiveEvent {
  eventId: string;
  matchId: string;
  minute: number;
  addedTime?: number;
  type: LiveEventType;
  team: 'home' | 'away';
  player?: {
    id: string;
    name: string;
    shirtNumber?: number;
  };
  secondaryPlayer?: {
    id: string;
    name: string;
    shirtNumber?: number;
  };
  description?: string;
  isImportant?: boolean;
}

export type LiveEventType = 
  | 'GOAL' 
  | 'GOAL_PENALTY' 
  | 'GOAL_OWN' 
  | 'ASSIST'
  | 'YELLOW_CARD' 
  | 'RED_CARD' 
  | 'SECOND_YELLOW'
  | 'SUBSTITUTION'
  | 'VAR_OVERTURNED'
  | 'VAR_CONFIRMED'
  | 'PENALTY_MISSED'
  | 'PENALTY_SAVED'
  | 'SHOT_ON_TARGET'
  | 'SHOT_OFF_TARGET'
  | 'SHOT_BLOCKED'
  | 'BIG_CHANCE_MISSED';

/**
 * Live Shot
 * Individual shot data with coordinates (when available)
 */
export interface LiveShot {
  shotId: string;
  matchId: string;
  minute: number;
  addedTime?: number;
  team: 'home' | 'away';
  player?: {
    id: string;
    name: string;
    shirtNumber?: number;
  };
  x?: number; // 0-100 (pitch coordinate)
  y?: number; // 0-100 (pitch coordinate)
  outcome: 'GOAL' | 'ON_TARGET' | 'OFF_TARGET' | 'BLOCKED';
  xG?: number;
  isGoal?: boolean;
  isBigChance?: boolean;
  bodyPart?: 'HEAD' | 'LEFT_FOOT' | 'RIGHT_FOOT' | 'OTHER';
}

/**
 * Live Prediction
 * Real-time model outputs (when backend supports)
 */
export interface LivePrediction {
  matchId: string;
  timestamp: string;
  minute?: number;
  
  // Win probabilities
  homeWinProbability?: number;
  drawProbability?: number;
  awayWinProbability?: number;
  
  // Expected goals
  homeXG?: number;
  awayXG?: number;
  
  // Market probabilities
  bttsProbability?: number;
  over25Probability?: number;
  over35Probability?: number;
  
  // Markets
  markets?: LiveMarket[];
  
  // Model meta
  modelAgreement?: number;
  confidence?: number;
  dataQuality?: DataQualityLevel;
}

/**
 * Live Market
 * Individual market with model probability
 */
export interface LiveMarket {
  marketId: string;
  marketType: string;
  marketName: string;
  selection: string;
  probability: number;
  confidence?: number;
  odds?: number; // Market odds (when available)
}

/**
 * Live Pick
 * TUTAR X LIVE PICK or PASS decision
 */
export interface LivePick {
  matchId: string;
  timestamp: string;
  minute?: number;
  
  // Pick details
  market?: string;
  selection?: string;
  probability?: number;
  confidence?: number;
  
  // Signal
  signal?: 'STRONG' | 'MEDIUM' | 'WEAK';
  dataQuality?: DataQualityLevel;
  
  // PASS decision
  passDecision: boolean;
  passReason?: string;
  
  // Invalidation/weakening
  isInvalidated?: boolean;
  invalidationReason?: string;
  previousConfidence?: number;
}

/**
 * Data Quality Summary
 * Overall data quality indicators for live match
 */
export interface DataQualitySummary {
  live: DataQualityLevel;
  shot: DataQualityLevel;
  xG: DataQualityLevel;
  lineup: DataQualityLevel;
  events: DataQualityLevel;
}

/**
 * Live Match Response from API
 */
export interface LiveMatchesResponse {
  matches: LiveMatchResponse[];
  provider_health: {
    provider: string;
    status: string;
    latency_ms?: number;
  };
  data_quality: {
    overall: DataQualityLevel;
  };
  timestamp: string;
  provider_used: string;
  total_count: number;
}

export interface LiveMatchResponse {
  match_id: string;
  status: MatchStatusType;
  minute?: number;
  home_score?: number;
  away_score?: number;
  home_team_id: string;
  away_team_id: string;
  data_quality_flags: DataQualityFlags;
}
