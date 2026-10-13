/**
 * Tests for getCompetitionPriorityRank.
 * Numeric (FotMob) IDs use the explicit ID allow-list; other ID formats use name keywords.
 */

import { describe, it, expect } from 'vitest';
import { getCompetitionPriorityRank } from '../popularCompetitions';

const NOT_PRIORITY = Number.MAX_SAFE_INTEGER;

describe('getCompetitionPriorityRank', () => {
  it('ranks UEFA competitions above domestic leagues for FotMob IDs', () => {
    const ucl = getCompetitionPriorityRank('Champions League', '42');
    const uel = getCompetitionPriorityRank('Europa League', '73');
    const epl = getCompetitionPriorityRank('Premier League', '47');
    expect(ucl).toBe(0);
    expect(ucl).toBeLessThan(uel);
    expect(uel).toBeLessThan(epl);
    expect(epl).toBeLessThan(NOT_PRIORITY);
  });

  it('keeps the same rank for other stages of an allow-listed competition ID', () => {
    expect(getCompetitionPriorityRank('Champions League Qualification', '42')).toBe(0);
  });

  it('does not promote same-named leagues from other countries (numeric IDs)', () => {
    // Real ids/names seen in the 13 Oct 2026 FotMob feed.
    expect(getCompetitionPriorityRank('Premier League', '519')).toBe(NOT_PRIORITY);
    expect(getCompetitionPriorityRank('Premier League', '9066')).toBe(NOT_PRIORITY);
    expect(getCompetitionPriorityRank('Ligue 1', '516')).toBe(NOT_PRIORITY);
    expect(getCompetitionPriorityRank('Championship', '123')).toBe(NOT_PRIORITY);
    expect(getCompetitionPriorityRank('USL Championship', '8972')).toBe(NOT_PRIORITY);
    expect(getCompetitionPriorityRank('AFC Champions League Elite West', '525')).toBe(NOT_PRIORITY);
    expect(getCompetitionPriorityRank('UEFA Youth League - League Stage', '9741')).toBe(NOT_PRIORITY);
  });

  it('ranks the English Championship (48) but not other "Championship" leagues', () => {
    expect(getCompetitionPriorityRank('Championship', '48')).toBeLessThan(NOT_PRIORITY);
  });

  it('falls back to name keywords for non-numeric provider IDs', () => {
    const ucl = getCompetitionPriorityRank('UEFA Champions League', 'UCL');
    const epl = getCompetitionPriorityRank('Premier League', 'EPL');
    expect(ucl).toBe(0);
    expect(ucl).toBeLessThan(epl);
  });

  it('keeps non-UEFA "Champions League" below major leagues in the name fallback', () => {
    const afc = getCompetitionPriorityRank('AFC Champions League Elite West', 'afc-cl');
    const epl = getCompetitionPriorityRank('Premier League', 'EPL');
    expect(afc).toBeGreaterThan(epl);
    expect(afc).toBeLessThan(NOT_PRIORITY);
  });

  it('does not rank women/youth competitions in the name fallback', () => {
    expect(getCompetitionPriorityRank("Women's Champions League", 'uwcl')).toBe(NOT_PRIORITY);
    expect(getCompetitionPriorityRank('Premier League U18', 'pl-u18')).toBe(NOT_PRIORITY);
  });

  it('returns MAX_SAFE_INTEGER for competitions outside the priority list', () => {
    expect(getCompetitionPriorityRank('Regionalliga Bayern', '512')).toBe(NOT_PRIORITY);
    expect(getCompetitionPriorityRank(null, undefined)).toBe(NOT_PRIORITY);
  });
});
