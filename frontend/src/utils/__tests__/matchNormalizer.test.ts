/**
 * Tests for matchNormalizer utility
 * 
 * Regression tests for team name normalization — ensures raw IDs are never displayed as team names.
 */

import { describe, it, expect } from 'vitest';
import { normalizeMatch } from '../matchNormalizer';
import type { MatchResponse, TeamInfoResponse } from '../../api/types';

describe('matchNormalizer', () => {
  describe('normalizeTeam', () => {
    // Helper to create a minimal MatchResponse
    function createMatchResponse(
      homeTeamId: string,
      awayTeamId: string,
      homeTeam: TeamInfoResponse | null = null,
      awayTeam: TeamInfoResponse | null = null
    ): MatchResponse {
      return {
        id: 'match_1',
        competition_id: 'comp_1',
        season_id: 'season_1',
        home_team_id: homeTeamId,
        away_team_id: awayTeamId,
        venue_id: null,
        home_team: homeTeam,
        away_team: awayTeam,
        scheduled_at: '2026-10-10T15:00:00Z',
        status: 'SCHEDULED',
        home_score: null,
        away_score: null,
        home_score_ht: null,
        away_score_ht: null,
        home_statistics: null,
        away_statistics: null,
        home_statistics_ht: null,
        away_statistics_ht: null,
        minute: null,
        added_time: null,
        outcome: null,
        round: null,
        created_at: null,
        updated_at: null,
      };
    }

    it('should use teamInfo.name when available', () => {
      const match = createMatchResponse(
        'team_home',
        'team_away',
        { id: 'team_home', name: 'Arsenal', short_name: 'ARS', code: 'ARS', logo_url: 'logo.png' },
        { id: 'team_away', name: 'Chelsea', short_name: 'CHE', code: 'CHE', logo_url: null }
      );
      const normalized = normalizeMatch(match);

      expect(normalized.homeTeam.name).toBe('Arsenal');
      expect(normalized.homeTeam.shortName).toBe('ARS');
      expect(normalized.awayTeam.name).toBe('Chelsea');
      expect(normalized.awayTeam.shortName).toBe('CHE');
    });

    it('should preserve all teamInfo fields when present', () => {
      const match = createMatchResponse(
        'team_home',
        'team_away',
        { id: 'team_home', name: 'Real Madrid', short_name: 'RMA', code: 'RMA', logo_url: 'logo.png' },
        null
      );
      const normalized = normalizeMatch(match);

      expect(normalized.homeTeam.id).toBe('team_home');
      expect(normalized.homeTeam.name).toBe('Real Madrid');
      expect(normalized.homeTeam.shortName).toBe('RMA');
      expect(normalized.homeTeam.code).toBe('RMA');
      expect(normalized.homeTeam.logoUrl).toBe('logo.png');
    });

    it('should show "Takım bilgisi yok" for numeric string ID when teamInfo missing', () => {
      const match = createMatchResponse('12345', '67890', null, null);
      const normalized = normalizeMatch(match);

      expect(normalized.homeTeam.name).toBe('Takım bilgisi yok');
      expect(normalized.awayTeam.name).toBe('Takım bilgisi yok');
    });

    it('should format dev_team_xxx pattern correctly', () => {
      const match = createMatchResponse('dev_team_arsenal', 'dev_team_liverpool', null, null);
      const normalized = normalizeMatch(match);

      expect(normalized.homeTeam.name).toBe('Arsenal');
      expect(normalized.awayTeam.name).toBe('Liverpool');
    });

    it('should show "Takım bilgisi yok" for alphanumeric provider ID when teamInfo missing', () => {
      const match = createMatchResponse('fotmob_123456', 'ryzellx_abc789', null, null);
      const normalized = normalizeMatch(match);

      expect(normalized.homeTeam.name).toBe('Takım bilgisi yok');
      expect(normalized.awayTeam.name).toBe('Takım bilgisi yok');
    });

    it('should show "Takım bilgisi yok" when both teamInfo and teamId are missing', () => {
      const match = createMatchResponse('', '', null, null);
      const normalized = normalizeMatch(match);

      expect(normalized.homeTeam.name).toBe('Takım bilgisi yok');
      expect(normalized.awayTeam.name).toBe('Takım bilgisi yok');
    });

    it('should show "Takım bilgisi yok" when teamInfo is present but name is null', () => {
      const match = createMatchResponse(
        'team_home',
        'team_away',
        { id: 'team_home', name: null as unknown as string, short_name: null, code: null, logo_url: null },
        { id: 'team_away', name: '', short_name: null, code: null, logo_url: null }
      );
      const normalized = normalizeMatch(match);

      expect(normalized.homeTeam.name).toBe('Takım bilgisi yok');
      expect(normalized.awayTeam.name).toBe('Takım bilgisi yok');
    });

    it('should prefer teamInfo.name over teamId when both are present', () => {
      const match = createMatchResponse(
        'team_home',
        'team_away',
        { id: 'team_home', name: 'Manchester United', short_name: 'MUN', code: 'MUN', logo_url: null },
        { id: 'different_id', name: 'Manchester City', short_name: 'MCI', code: 'MCI', logo_url: null }
      );
      const normalized = normalizeMatch(match);

      expect(normalized.homeTeam.name).toBe('Manchester United');
      expect(normalized.homeTeam.id).toBe('team_home'); // Uses teamInfo.id
      expect(normalized.awayTeam.name).toBe('Manchester City');
      expect(normalized.awayTeam.id).toBe('different_id'); // Uses teamInfo.id
    });
  });
});
