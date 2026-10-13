/**
 * Data Formatting Utilities
 */

import type { MatchStatus } from '../api/types';

/**
 * Format team ID to display name.
 * For UUID team IDs, extract provider ID and map to known team names.
 */
export function formatTeamName(teamId: string): string {
  // Handle [DEV] prefixed names
  if (teamId.startsWith('[DEV]')) {
    return teamId.replace('[DEV]', '').trim();
  }

  // Handle dev_team_name pattern
  const match = teamId.match(/^dev_team_(.+)$/);
  if (match) {
    const name = match[1];
    // Capitalize first letter
    return name.charAt(0).toUpperCase() + name.slice(1);
  }

  // Handle UUID format - fallback display for team IDs when backend doesn't provide team names
  if (teamId.match(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i)) {
    // Use first 8 characters as team identifier (backend should provide team names)
    const shortId = teamId.substring(0, 8).toUpperCase();
    return `Takım ${shortId}`;
  }

  // Handle numeric provider IDs (legacy format)
  if (/^\d+$/.test(teamId)) {
    return `Takım #${teamId}`;
  }

  // Return as-is if no pattern matches
  return teamId;
}

/**
 * Format competition ID to display name.
 */
export function formatCompetitionName(competitionId: string): string {
  if (competitionId.startsWith('[DEV]')) {
    return competitionId.replace('[DEV]', '').trim();
  }

  const match = competitionId.match(/^dev_comp_(.+)$/);
  if (match) {
    const name = match[1].replace(/_/g, ' ');
    return name
      .split(' ')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  }

  return competitionId;
}

/**
 * Format match status to Turkish display text.
 */
export function formatMatchStatus(status: MatchStatus): string {
  const statusMap: Record<MatchStatus, string> = {
    SCHEDULED: 'Planlandı',
    LIVE: 'Canlı',
    FINISHED: 'Bitti',
    POSTPONED: 'Ertelendi',
    CANCELLED: 'İptal',
    SUSPENDED: 'Askıya Alındı',
  };

  return statusMap[status] || status;
}

/**
 * Format date and time for match display with Istanbul timezone.
 */
export function formatMatchDateTime(dateString: string): {
  date: string;
  time: string;
  full: string;
} {
  const date = new Date(dateString);

  // Convert to Istanbul timezone for display
  const dateFormatted = date.toLocaleDateString('tr-TR', {
    timeZone: 'Europe/Istanbul',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });

  const timeFormatted = date.toLocaleTimeString('tr-TR', {
    timeZone: 'Europe/Istanbul',
    hour: '2-digit',
    minute: '2-digit',
  });

  const fullFormatted = date.toLocaleString('tr-TR', {
    timeZone: 'Europe/Istanbul',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });

  return {
    date: dateFormatted,
    time: timeFormatted,
    full: fullFormatted,
  };
}

/**
 * Format match score display.
 */
export function formatScore(
  homeScore: number | null,
  awayScore: number | null
): string {
  if (homeScore === null || awayScore === null) {
    return '-';
  }
  return `${homeScore} - ${awayScore}`;
}
