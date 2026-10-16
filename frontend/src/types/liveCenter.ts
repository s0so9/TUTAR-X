/**
 * Live match centre — response contract of
 * GET /api/v1/matches/{match_id}/live-center (shared with the backend agent).
 *
 * Every value is what the source (FotMob) sent; nothing is imputed. A section
 * the source did not send is null (or absent from a list) and is named in
 * `missing` with a reason, so the UI can say "veri yok" instead of showing 0.
 *
 * Frontend assumptions where the contract leaves room (documented here, used by
 * components/match/live/liveCenterModel.ts):
 * - `shotmap[].x / y` are in FotMob's frame: x 0–105 (metres along the pitch,
 *   towards the goal the shooting side attacks), y 0–68 (metres across).
 *   Values that all fall inside 0–1 are read as fractions of that frame.
 * - `lineups.*.starters[].grid.row` orders the lines from one goal to the
 *   other; the line holding the goalkeeper is taken as the team's own goal
 *   line whichever end it sits at. `col` only orders players within a line.
 * - `momentum[].value` is -100…100, positive = home pressure (FotMob).
 */

export type LiveCenterStatus =
  | 'SCHEDULED'
  | 'LIVE'
  | 'HALF_TIME'
  | 'FINISHED'
  | 'POSTPONED'
  | 'CANCELLED'
  | 'ABANDONED'
  | 'EXTRA_TIME'
  | 'PENALTIES';

export type LiveCenterPeriod = '1H' | 'HT' | '2H' | 'ET' | 'PEN' | 'FT';

export type LiveSide = 'home' | 'away';

export interface LiveScore {
  home: number | null;
  away: number | null;
}

export interface LiveTeamRef {
  id: string | number | null;
  name: string;
  short_name: string | null;
  logo_url: string | null;
}

export interface LivePersonRef {
  id: string | number | null;
  name: string;
}

export type LiveEventType =
  | 'goal'
  | 'own_goal'
  | 'penalty_goal'
  | 'penalty_missed'
  | 'yellow_card'
  | 'second_yellow'
  | 'red_card'
  | 'substitution'
  | 'var'
  | 'period_end';

export interface LiveEvent {
  id: string | number;
  minute: number | null;
  added_time: number | null;
  period: LiveCenterPeriod | null;
  /** null for match-wide markers such as period_end */
  side: LiveSide | null;
  type: LiveEventType;
  player: LivePersonRef | null;
  assist: LivePersonRef | null;
  player_in: LivePersonRef | null;
  player_out: LivePersonRef | null;
  score_after: LiveScore | null;
  detail: string | null;
}

export type LivePosition = 'GK' | 'DEF' | 'MID' | 'FWD';

export interface LiveGrid {
  row: number;
  col: number;
  rows_in_formation: number;
}

export interface LiveLineupPlayer {
  id: string | number | null;
  name: string;
  shirt: number | string | null;
  position: LivePosition | null;
  grid: LiveGrid | null;
  captain: boolean;
  rating: number | null;
  goals: number | null;
  assists: number | null;
  yellow: number | null;
  red: number | null;
  sub_out_minute: number | null;
  /** substitutes only */
  sub_in_minute?: number | null;
}

export interface LiveUnavailablePlayer {
  id: string | number | null;
  name: string;
  reason: string | null;
  expected_return: string | null;
}

export type LiveLineupType = 'confirmed' | 'predicted' | 'last_starting11';

export interface LiveTeamLineup {
  formation: string | null;
  lineup_type: LiveLineupType | null;
  coach: LivePersonRef | null;
  starters: LiveLineupPlayer[];
  substitutes: LiveLineupPlayer[];
  unavailable: LiveUnavailablePlayer[];
}

export type LiveStatGroup = 'Genel' | 'Şutlar' | 'Pas' | 'Savunma' | 'Disiplin';

export type LiveStatUnit = 'count' | 'percent' | 'decimal';

export interface LiveStatItem {
  key: string;
  label_tr: string;
  group: LiveStatGroup;
  home: number | null;
  away: number | null;
  unit: LiveStatUnit;
  home_text: string | null;
  away_text: string | null;
}

export interface LiveStats {
  all: LiveStatItem[];
  first_half: LiveStatItem[] | null;
  second_half: LiveStatItem[] | null;
}

export type LiveShotOutcome = 'goal' | 'saved' | 'missed' | 'blocked' | 'post';

export interface LiveShot {
  minute: number | null;
  side: LiveSide;
  player: LivePersonRef | null;
  x: number;
  y: number;
  xg: number | null;
  xgot: number | null;
  outcome: LiveShotOutcome;
  situation: string | null;
  body_part: string | null;
}

export interface LiveMomentumPoint {
  minute: number;
  value: number;
}

export interface LiveMissingSection {
  section: string;
  /** Machine reason code from the endpoint, e.g. "not_started". */
  reason: string;
  /** Turkish explanation for the UI (endpoint field, may be absent). */
  message_tr?: string | null;
}

export interface LiveCenterResponse {
  match_id: string;
  provider: string;
  fetched_at: string;
  cache_ttl_seconds: number | null;
  status: LiveCenterStatus;
  minute: number | null;
  added_time: number | null;
  period: LiveCenterPeriod | null;
  kickoff: string | null;
  /** FotMob parent league id, e.g. "42" (additive endpoint field, may be absent). The match endpoint can
   * give a stage id instead (e.g. "943230" for a Champions League league-phase match). */
  competition_id?: string | null;
  venue: string | null;
  referee: string | null;
  attendance: number | null;
  score: LiveScore;
  halftime_score: LiveScore | null;
  penalty_score: LiveScore | null;
  teams: { home: LiveTeamRef; away: LiveTeamRef };
  events: LiveEvent[] | null;
  lineups: { home: LiveTeamLineup | null; away: LiveTeamLineup | null } | null;
  stats: LiveStats | null;
  shotmap: LiveShot[] | null;
  momentum: LiveMomentumPoint[] | null;
  missing: LiveMissingSection[];
}
