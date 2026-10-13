/**
 * Search Text Normalization Utilities
 *
 * Handles Turkish character normalization and case-insensitive matching
 * for global search functionality.
 */

/**
 * Normalize text for search comparison.
 * - Converts to lowercase
 * - Normalizes Turkish characters (İ, ı, Ş, ş, Ğ, ğ, Ü, ü, Ö, ö, Ç, ç)
 * - Removes extra whitespace
 * - Handles common team name variations
 */
export function normalizeSearchText(text: string): string {
  if (!text) return '';

  // First normalize unicode to handle combining characters
  const normalized = text.normalize('NFD').replace(/[\u0300-\u036f]/g, '');

  return normalized
    .toLowerCase()
    .trim()
    // Turkish character normalization - handle both dotted and dotless i
    .replace(/İ/g, 'i')
    .replace(/I/g, 'i') // Turkish capital I without dot
    .replace(/ı/g, 'i') // Turkish lowercase i without dot
    .replace(/[Şş]/g, 's')
    .replace(/[Ğğ]/g, 'g')
    .replace(/[Üü]/g, 'u')
    .replace(/[Öö]/g, 'o')
    .replace(/[Çç]/g, 'c')
    // Remove punctuation and special characters for better matching
    .replace(/[.,\-_()]/g, ' ')
    // Normalize whitespace
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Check if a team name matches the search term.
 * Handles various matching strategies for better UX.
 */
export function matchesTeamName(teamName: string, searchTerm: string): boolean {
  const normalizedTeam = normalizeSearchText(teamName);
  const normalizedSearch = normalizeSearchText(searchTerm);

  if (!normalizedTeam || !normalizedSearch) return false;

  // Direct substring match
  if (normalizedTeam.includes(normalizedSearch)) return true;

  // Word-based matching (for partial matches)
  const teamWords = normalizedTeam.split(' ');
  const searchWords = normalizedSearch.split(' ');

  // Check if any team word starts with search term
  for (const teamWord of teamWords) {
    for (const searchWord of searchWords) {
      if (teamWord.startsWith(searchWord) && searchWord.length >= 3) {
        return true;
      }
    }
  }

  // Common abbreviations and nicknames
  const abbreviations = extractAbbreviations(normalizedTeam);
  for (const abbr of abbreviations) {
    if (abbr.includes(normalizedSearch)) return true;
  }

  return false;
}

/**
 * Common team name nicknames and abbreviations.
 * Only include widely known and documented nicknames.
 */
const TEAM_NICKNAMES: Record<string, string[]> = {
  'barcelona': ['barca', 'fcb'],
  'real madrid': ['real', 'madrid'],
  'manchester united': ['man utd', 'man united', 'united'],
  'manchester city': ['man city', 'city'],
  'bayern munich': ['bayern', 'fcb'],
  'borussia dortmund': ['dortmund', 'bvb'],
  'atletico madrid': ['atletico', 'atleti'],
  'paris saint germain': ['psg', 'paris'],
  'ac milan': ['milan', 'acm'],
  'inter milan': ['inter'],
  'juventus': ['juve'],
  'arsenal': ['gunners'],
  'chelsea': ['blues'],
  'liverpool': ['reds', 'lfc'],
  'tottenham': ['spurs', 'thfc'],
};

/**
 * Extract possible abbreviations from team name.
 * Examples: "Real Madrid" -> ["real", "madrid", "rm"]
 */
function extractAbbreviations(teamName: string): string[] {
  const words = teamName.split(' ').filter(word => word.length > 0);
  const abbreviations: string[] = [...words];

  // Add initials if multiple words
  if (words.length >= 2) {
    const initials = words.map(word => word[0]).join('');
    if (initials.length >= 2) {
      abbreviations.push(initials);
    }
  }

  // Check for known nicknames
  if (TEAM_NICKNAMES[teamName]) {
    abbreviations.push(...TEAM_NICKNAMES[teamName]);
  }

  return abbreviations;
}

/**
 * Calculate relevance score for search match.
 * Higher score means more relevant match.
 */
export function calculateRelevance(
  teamName: string,
  searchTerm: string,
  isExactMatch: boolean = false
): number {
  const normalizedTeam = normalizeSearchText(teamName);
  const normalizedSearch = normalizeSearchText(searchTerm);

  if (!normalizedTeam || !normalizedSearch) return 0;

  // Exact match gets highest score
  if (normalizedTeam === normalizedSearch || isExactMatch) return 100;

  // Team starts with search term
  if (normalizedTeam.startsWith(normalizedSearch)) return 90;

  // Team contains search term as substring (but not at start)
  if (normalizedTeam.includes(normalizedSearch)) {
    // If it's a word boundary match, give higher score
    const teamWords = normalizedTeam.split(' ');
    if (teamWords.includes(normalizedSearch)) {
      return 70; // Word match but not full team name
    }
    return 60; // Substring match
  }

  // Word-level matching
  const teamWords = normalizedTeam.split(' ');
  const searchWords = normalizedSearch.split(' ');

  let wordMatchScore = 0;
  for (const searchWord of searchWords) {
    for (const teamWord of teamWords) {
      if (teamWord === searchWord) wordMatchScore += 25;
      else if (teamWord.startsWith(searchWord)) wordMatchScore += 15;
      else if (teamWord.includes(searchWord)) wordMatchScore += 8;
    }
  }

  return Math.min(wordMatchScore, 50); // Cap at 50 for word matching
}

/**
 * Highlight matching text in search results.
 * Returns the original text with <mark> tags around matches.
 */
export function highlightMatch(text: string, searchTerm: string): string {
  if (!searchTerm || !text) return text;

  const normalizedSearch = normalizeSearchText(searchTerm);
  const words = normalizedSearch.split(' ').filter(word => word.length >= 2);

  if (words.length === 0) return text;

  let result = text;

  // Highlight each search word
  for (const word of words) {
    // Escape special regex characters
    const escapedWord = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

    // Create case-insensitive regex for highlighting
    // Build a pattern that matches the word with any Turkish character variants
    let pattern = '';
    for (const char of escapedWord) {
      switch (char) {
        case 'i':
          pattern += '[İıIi]';
          break;
        case 's':
          pattern += '[SsŞş]';
          break;
        case 'g':
          pattern += '[GgĞğ]';
          break;
        case 'u':
          pattern += '[UuÜü]';
          break;
        case 'o':
          pattern += '[OoÖö]';
          break;
        case 'c':
          pattern += '[CcÇç]';
          break;
        default:
          pattern += char;
      }
    }

    try {
      const regex = new RegExp(pattern, 'gi');
      result = result.replace(regex, '<mark>$&</mark>');
    } catch (e) {
      // If regex fails, skip this word
      console.warn('Regex error for word:', word, e);
    }
  }

  return result;
}