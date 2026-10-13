/**
 * Search Normalizer Tests
 *
 * Tests for Turkish character normalization and search matching.
 */

import {
  normalizeSearchText,
  matchesTeamName,
  calculateRelevance,
  highlightMatch
} from '../searchNormalizer';

describe('normalizeSearchText', () => {
  it('should convert to lowercase', () => {
    expect(normalizeSearchText('GALATASARAY')).toBe('galatasaray');
    expect(normalizeSearchText('Real Madrid')).toBe('real madrid');
  });

  it('should normalize Turkish characters', () => {
    expect(normalizeSearchText('İstanbul')).toBe('istanbul');
    expect(normalizeSearchText('Beşiktaş')).toBe('besiktas');
    expect(normalizeSearchText('Fenerbahçe')).toBe('fenerbahce');
    expect(normalizeSearchText('Galatasaray')).toBe('galatasaray');
    expect(normalizeSearchText('Trabzonspor')).toBe('trabzonspor');
    expect(normalizeSearchText('Başakşehir')).toBe('basaksehir');
  });

  it('should handle mixed Turkish and English text', () => {
    expect(normalizeSearchText('Süper Lig')).toBe('super lig');
    expect(normalizeSearchText('İngiltere Premier')).toBe('ingiltere premier');
  });

  it('should normalize whitespace', () => {
    expect(normalizeSearchText('  Real   Madrid  ')).toBe('real madrid');
    expect(normalizeSearchText('Man\tCity')).toBe('man city');
  });

  it('should remove punctuation', () => {
    expect(normalizeSearchText('Real Madrid C.F.')).toBe('real madrid c f');
    expect(normalizeSearchText('AC Milan')).toBe('ac milan');
    expect(normalizeSearchText('Borussia Mönchengladbach')).toBe('borussia monchengladbach');
  });
});

describe('matchesTeamName', () => {
  it('should match exact team names', () => {
    expect(matchesTeamName('Galatasaray', 'galatasaray')).toBe(true);
    expect(matchesTeamName('Real Madrid', 'real madrid')).toBe(true);
  });

  it('should match partial team names', () => {
    expect(matchesTeamName('Galatasaray', 'gala')).toBe(true);
    expect(matchesTeamName('Real Madrid', 'real')).toBe(true);
    expect(matchesTeamName('Real Madrid', 'madrid')).toBe(true);
  });

  it('should handle Turkish characters in matching', () => {
    expect(matchesTeamName('Beşiktaş', 'besiktas')).toBe(true);
    expect(matchesTeamName('Beşiktaş', 'beşiktaş')).toBe(true);
    expect(matchesTeamName('Fenerbahçe', 'fener')).toBe(true);
    expect(matchesTeamName('İstanbul Başakşehir', 'basaksehir')).toBe(true);
  });

  it('should match abbreviations', () => {
    expect(matchesTeamName('Real Madrid', 'rm')).toBe(true);
    expect(matchesTeamName('Manchester United', 'mu')).toBe(true);
    expect(matchesTeamName('Barcelona', 'barca')).toBe(true);
  });

  it('should not match unrelated text', () => {
    expect(matchesTeamName('Galatasaray', 'fenerbahce')).toBe(false);
    expect(matchesTeamName('Real Madrid', 'barcelona')).toBe(false);
  });

  it('should handle case insensitivity', () => {
    expect(matchesTeamName('GALATASARAY', 'gala')).toBe(true);
    expect(matchesTeamName('galatasaray', 'GALA')).toBe(true);
  });
});

describe('calculateRelevance', () => {
  it('should give highest score to exact matches', () => {
    expect(calculateRelevance('Galatasaray', 'galatasaray')).toBe(100);
    expect(calculateRelevance('Real Madrid', 'real madrid')).toBe(100);
  });

  it('should give high score to prefix matches', () => {
    const score = calculateRelevance('Galatasaray', 'gala');
    expect(score).toBe(90);
  });

  it('should give medium score to substring matches', () => {
    const score = calculateRelevance('Galatasaray', 'saray');
    expect(score).toBe(60); // Substring match (not at start)
  });

  it('should give lower scores to partial word matches', () => {
    const score = calculateRelevance('Real Madrid', 'madrid');
    expect(score).toBeGreaterThan(0);
    expect(score).toBeLessThan(80);
  });

  it('should return 0 for non-matches', () => {
    expect(calculateRelevance('Galatasaray', 'fenerbahce')).toBe(0);
  });
});

describe('highlightMatch', () => {
  it('should highlight exact matches', () => {
    expect(highlightMatch('Galatasaray', 'gala')).toContain('<mark>');
    expect(highlightMatch('Real Madrid', 'real')).toContain('<mark>Real</mark>');
  });

  it('should handle Turkish characters in highlighting', () => {
    expect(highlightMatch('İstanbul', 'istanbul')).toContain('<mark>İstanbul</mark>');
    expect(highlightMatch('Beşiktaş', 'besiktas')).toContain('<mark>Beşiktaş</mark>');
  });

  it('should return original text when no match', () => {
    expect(highlightMatch('Galatasaray', 'fenerbahce')).toBe('Galatasaray');
  });

  it('should handle multiple word highlighting', () => {
    const result = highlightMatch('Real Madrid Barcelona', 'real barcelona');
    expect(result).toContain('<mark>Real</mark>');
    expect(result).toContain('<mark>Barcelona</mark>');
  });
});