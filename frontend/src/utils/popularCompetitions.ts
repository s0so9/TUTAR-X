/**
 * Popular Competition Identification
 *
 * Identifies major football competitions that should receive
 * prioritized prediction loading.
 */

/**
 * Popular competitions that should receive prioritized predictions.
 * Based on competition/league names commonly used in football data.
 */
const POPULAR_COMPETITION_KEYWORDS = [
  // English
  'premier league',
  'championship',
  'efl',

  // Spanish
  'la liga',
  'laliga',

  // German
  'bundesliga',

  // Italian
  'serie a',

  // French
  'ligue 1',

  // Turkish
  'süper lig',
  'super lig',
  'superlig',

  // Brazilian
  'brasileirão',
  'brasileirao',
  'brasileiro',
  'brazil serie a',
  'serie a brazil',
  'campeonato brasileiro',

  // European
  'champions league',
  'uefa champions',
  'europa league',
  'uefa europa',
  'conference league',

  // Other major leagues
  'eredivisie',
  'primeira liga',
  'scottish premiership',
];

/**
 * Check if a competition is considered popular based on its name.
 */
export function isPopularCompetition(competitionName: string | undefined): boolean {
  if (!competitionName) return false;

  const normalized = competitionName.toLowerCase().trim();

  return POPULAR_COMPETITION_KEYWORDS.some(keyword =>
    normalized.includes(keyword)
  );
}

/**
 * Check if a competition is popular based on competition_id pattern.
 * Many data sources use specific ID patterns for major competitions.
 */
export function isPopularCompetitionById(competitionId: string | undefined): boolean {
  if (!competitionId) return false;

  // Common ID patterns for major competitions in various data sources
  // This is a heuristic - actual IDs depend on the data provider
  const popularIdPatterns = [
    /^(PL|EPL)/i,        // Premier League
    /^(LL|LAL)/i,        // La Liga
    /^(BL|BUN)/i,        // Bundesliga
    /^(SA|SER)/i,        // Serie A
    /^(L1|LIG)/i,        // Ligue 1
    /^(SL|SUP)/i,        // Süper Lig
    /^(CL|UCL)/i,        // Champions League
    /^(EL|UEL)/i,        // Europa League
  ];

  return popularIdPatterns.some(pattern => pattern.test(competitionId));
}

/**
 * Filter matches to only those from popular competitions.
 */
export function filterPopularMatches<T extends { competition_id?: string }>(
  matches: T[],
  getCompetitionName?: (match: T) => string | undefined
): T[] {
  return matches.filter(match => {
    // Check by ID first (fast)
    if (isPopularCompetitionById(match.competition_id)) {
      return true;
    }

    // Check by name if getter provided (slower)
    if (getCompetitionName) {
      const name = getCompetitionName(match);
      if (isPopularCompetition(name)) {
        return true;
      }
    }

    return false;
  });
}

/**
 * Normalize competition name for display.
 * Handles provider-specific variations and returns a canonical display name.
 *
 * This function does NOT hardcode IDs or create fake competitions.
 * It only normalizes known competition name patterns for better UI display.
 */
export function normalizeCompetitionName(competitionName: string | undefined): string | undefined {
  if (!competitionName) return undefined;

  const normalized = competitionName.toLowerCase().trim();

  // Brazilian Serie A variations
  if (
    normalized.includes('brasileirão') ||
    normalized.includes('brasileirao') ||
    normalized.includes('brasileiro') ||
    (normalized.includes('brazil') && normalized.includes('serie a')) ||
    (normalized.includes('serie a') && normalized.includes('brazil')) ||
    normalized.includes('campeonato brasileiro')
  ) {
    return 'Brasileirão Série A';
  }

  // Return original if no normalization pattern matches
  return competitionName;
}

/**
 * FotMob league IDs of the priority competitions, in priority order (index 0 = highest).
 *
 * FotMob reuses generic names across countries ("Premier League" is also Egypt,
 * Tanzania, ...; "Ligue 1" is also Algeria; "Championship" is also Scotland/USL),
 * so for numeric provider IDs only this explicit allow-list counts. These are
 * configuration values (league identifiers), not statistics.
 * Verified against the live /matches feed where noted.
 */
const FOTMOB_PRIORITY_COMPETITION_IDS: readonly string[] = [
  '42', // UEFA Champions League (verified: 13 Oct 2026 feed)
  '73', // UEFA Europa League
  '10216', // UEFA Conference League
  '71', // Türkiye Süper Lig
  '47', // England Premier League
  '87', // Spain LaLiga
  '54', // Germany Bundesliga
  '55', // Italy Serie A
  '53', // France Ligue 1
  '57', // Netherlands Eredivisie
  '61', // Portugal Liga Portugal
  '48', // England Championship (verified: 13 Oct 2026 feed)
  '268', // Brazil Série A
];

const NUMERIC_PROVIDER_ID = /^\d+$/;

/**
 * Ordered keywords used to rank competitions for display / prediction priority
 * when the provider ID is not numeric (non-FotMob providers).
 * Lower index = higher priority. Continental club competitions first,
 * then the major domestic leagues.
 */
const COMPETITION_PRIORITY_KEYWORDS = [
  'champions league',
  'europa league',
  'conference league',
  'süper lig',
  'super lig',
  'superlig',
  'premier league',
  'la liga',
  'laliga',
  'bundesliga',
  'serie a',
  'ligue 1',
  'eredivisie',
  'primeira liga',
  'championship',
];

/** Non-UEFA confederation prefixes that share keywords with UEFA competitions. */
const NON_UEFA_PREFIXES = ['afc ', 'caf ', 'concacaf ', 'conmebol ', 'ofc '];

/** Women's, youth and reserve competitions share names with the senior men's leagues. */
const NON_SENIOR_PATTERN = /women|kadın|femin|frauen|youth|\bu\d{2}\b|reserve|premier league 2/;

/**
 * Priority rank for a competition (0 = highest). Returns Number.MAX_SAFE_INTEGER
 * for competitions that are not in the priority list.
 *
 * Numeric (FotMob) IDs are ranked only by the explicit ID allow-list, because
 * names such as "Premier League" or "Ligue 1" are shared by many countries.
 * Other provider ID formats fall back to the name-based keyword ranking.
 */
export function getCompetitionPriorityRank(
  competitionName: string | undefined | null,
  competitionId?: string
): number {
  const id = (competitionId ?? '').trim();
  if (NUMERIC_PROVIDER_ID.test(id)) {
    const idIndex = FOTMOB_PRIORITY_COMPETITION_IDS.indexOf(id);
    return idIndex >= 0 ? idIndex : Number.MAX_SAFE_INTEGER;
  }

  const normalized = (competitionName ?? '').toLowerCase().trim();
  if (normalized && !NON_SENIOR_PATTERN.test(normalized)) {
    const isNonUefa = NON_UEFA_PREFIXES.some((prefix) => normalized.startsWith(prefix));
    const index = COMPETITION_PRIORITY_KEYWORDS.findIndex((keyword) => normalized.includes(keyword));
    if (index >= 0) {
      // Keep e.g. "AFC Champions League" below the UEFA competitions and major leagues.
      return isNonUefa ? COMPETITION_PRIORITY_KEYWORDS.length + index : index;
    }
  }
  if (normalized && NON_SENIOR_PATTERN.test(normalized)) {
    return Number.MAX_SAFE_INTEGER;
  }
  if (isPopularCompetitionById(competitionId) || isPopularCompetition(competitionName ?? undefined)) {
    return COMPETITION_PRIORITY_KEYWORDS.length * 2;
  }
  return Number.MAX_SAFE_INTEGER;
}
