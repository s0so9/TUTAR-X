/**
 * Live Competition Priority
 * 
 * Dynamically identifies competitions with currently live matches
 * and adds them to the prediction priority list.
 */

import type { MatchResponse } from '../api/types';

/**
 * Extract unique competition IDs from live matches by matching their IDs
 * with the scheduled matches dataset.
 * 
 * @param liveMatchIds - Array of match IDs currently live
 * @param allMatches - All scheduled matches dataset
 * @returns Array of competition IDs that have live matches
 */
export function getLiveCompetitionIds(
  liveMatchIds: string[],
  allMatches: MatchResponse[]
): string[] {
  const competitionIds = new Set<string>();
  
  // Create a map of match_id -> competition_id for fast lookup
  const matchCompetitionMap = new Map<string, string>();
  allMatches.forEach(match => {
    if (match.competition_id) {
      matchCompetitionMap.set(match.id, match.competition_id);
    }
  });
  
  // Find competitions for live matches
  liveMatchIds.forEach(matchId => {
    const competitionId = matchCompetitionMap.get(matchId);
    if (competitionId) {
      competitionIds.add(competitionId);
    }
  });
  
  return Array.from(competitionIds);
}

/**
 * Check if a match belongs to a currently live competition.
 */
export function isFromLiveCompetition(
  competitionId: string | undefined,
  liveCompetitionIds: string[]
): boolean {
  if (!competitionId) return false;
  return liveCompetitionIds.includes(competitionId);
}

/**
 * Select priority matches from live competitions.
 * Limits to upcoming matches within next 48 hours, max 10 per competition.
 */
export function selectLiveCompetitionPriorityMatches(
  allMatches: MatchResponse[],
  liveCompetitionIds: string[]
): MatchResponse[] {
  if (liveCompetitionIds.length === 0) return [];
  
  const now = new Date();
  const next48Hours = new Date(now.getTime() + 48 * 60 * 60 * 1000);
  
  // Group by competition
  const byCompetition = new Map<string, MatchResponse[]>();
  
  allMatches.forEach(match => {
    const compId = match.competition_id;
    if (!compId || !liveCompetitionIds.includes(compId)) return;
    
    // Only scheduled matches
    if (match.status !== 'SCHEDULED') return;
    
    const matchDate = new Date(match.scheduled_at);
    if (matchDate < now || matchDate > next48Hours) return;
    
    if (!byCompetition.has(compId)) {
      byCompetition.set(compId, []);
    }
    byCompetition.get(compId)!.push(match);
  });
  
  // Take max 10 matches per live competition
  const priorityMatches: MatchResponse[] = [];
  byCompetition.forEach(matches => {
    // Sort by scheduled_at ascending (soonest first)
    const sorted = matches.sort((a, b) => 
      new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime()
    );
    priorityMatches.push(...sorted.slice(0, 10));
  });
  
  return priorityMatches;
}
