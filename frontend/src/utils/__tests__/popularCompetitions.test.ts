/**
 * Tests for popularCompetitions utility
 */

import { describe, it, expect } from 'vitest';
import { 
  isPopularCompetition, 
  isPopularCompetitionById,
  normalizeCompetitionName 
} from '../popularCompetitions';

describe('popularCompetitions', () => {
  describe('isPopularCompetition', () => {
    it('should recognize Brazilian Serie A variations', () => {
      expect(isPopularCompetition('Brasileirão Série A')).toBe(true);
      expect(isPopularCompetition('Campeonato Brasileiro Série A')).toBe(true);
      expect(isPopularCompetition('Brazil Serie A')).toBe(true);
      expect(isPopularCompetition('Serie A Brazil')).toBe(true);
      expect(isPopularCompetition('Brasileiro')).toBe(true);
    });

    it('should recognize Premier League', () => {
      expect(isPopularCompetition('Premier League')).toBe(true);
      expect(isPopularCompetition('English Premier League')).toBe(true);
    });

    it('should recognize La Liga', () => {
      expect(isPopularCompetition('La Liga')).toBe(true);
      expect(isPopularCompetition('LaLiga EA Sports')).toBe(true);
    });

    it('should recognize Bundesliga', () => {
      expect(isPopularCompetition('Bundesliga')).toBe(true);
      expect(isPopularCompetition('German Bundesliga')).toBe(true);
    });

    it('should recognize Italian Serie A', () => {
      expect(isPopularCompetition('Serie A')).toBe(true);
      expect(isPopularCompetition('Italian Serie A')).toBe(true);
    });

    it('should be case-insensitive', () => {
      expect(isPopularCompetition('PREMIER LEAGUE')).toBe(true);
      expect(isPopularCompetition('brasileirão')).toBe(true);
      expect(isPopularCompetition('BRASILEIRAO')).toBe(true);
    });

    it('should return false for unknown competitions', () => {
      expect(isPopularCompetition('Unknown League')).toBe(false);
      expect(isPopularCompetition('Random Competition')).toBe(false);
    });

    it('should handle undefined input', () => {
      expect(isPopularCompetition(undefined)).toBe(false);
    });
  });

  describe('normalizeCompetitionName', () => {
    it('should normalize Brazilian Serie A variations to canonical name', () => {
      expect(normalizeCompetitionName('Brasileirão Série A')).toBe('Brasileirão Série A');
      expect(normalizeCompetitionName('Campeonato Brasileiro Série A')).toBe('Brasileirão Série A');
      expect(normalizeCompetitionName('Campeonato Brasileiro - Série A')).toBe('Brasileirão Série A');
      expect(normalizeCompetitionName('Brazil Serie A')).toBe('Brasileirão Série A');
      expect(normalizeCompetitionName('Serie A Brazil')).toBe('Brasileirão Série A');
      expect(normalizeCompetitionName('Brasileiro')).toBe('Brasileirão Série A');
    });

    it('should be case-insensitive for normalization', () => {
      expect(normalizeCompetitionName('CAMPEONATO BRASILEIRO SÉRIE A')).toBe('Brasileirão Série A');
      expect(normalizeCompetitionName('brasileiro')).toBe('Brasileirão Série A');
      expect(normalizeCompetitionName('BRAZIL SERIE A')).toBe('Brasileirão Série A');
    });

    it('should return original name for non-normalized competitions', () => {
      expect(normalizeCompetitionName('Premier League')).toBe('Premier League');
      expect(normalizeCompetitionName('La Liga')).toBe('La Liga');
      expect(normalizeCompetitionName('Bundesliga')).toBe('Bundesliga');
    });

    it('should handle undefined input', () => {
      expect(normalizeCompetitionName(undefined)).toBeUndefined();
    });
  });

  describe('isPopularCompetitionById', () => {
    it('should return false for numeric IDs', () => {
      expect(isPopularCompetitionById('9011')).toBe(false);
      expect(isPopularCompetitionById('530')).toBe(false);
      expect(isPopularCompetitionById('10270')).toBe(false);
    });

    it('should handle undefined input', () => {
      expect(isPopularCompetitionById(undefined)).toBe(false);
    });
  });
});
