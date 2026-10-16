/**
 * Display helpers of the frozen headline picks. Payloads are TEST FIXTURES (made-up values).
 */

import { describe, it, expect } from 'vitest';
import type { HeadlinePickItem, MatchHeadlineRecord } from '../../api/headlineRecord';
import {
  cardPickStatus,
  cardStatusLines,
  describeFrozen,
  describeLineup,
  formatFinalScore,
  formatRate,
  frozenPickStatus,
  groupByMatch,
  headlinePickStatus,
  lineupWord,
  pickCardNote,
  pickStatusLabel,
  pickStatusLine,
  resultMark,
  type PickStatusInfo,
} from '../headlineRecord';

describe('headlinePickStatus ("Ön tahmin" / "Kesin" of the live picks)', () => {
  it('confirmed line-ups in the prediction make them final (FotMob "standard" = confirmed)', () => {
    for (const value of ['confirmed', 'standard', ' Standard ']) {
      expect(
        headlinePickStatus({ predictionLineups: { home: value, away: 'confirmed' }, centreLineups: null }).status,
      ).toBe('kesin');
    }
  });

  it('predicted or one-sided line-ups never do', () => {
    for (const lineups of [
      { home: 'predicted', away: 'predicted' },
      { home: 'confirmed', away: 'predicted' },
      { home: 'confirmed', away: null },
      { home: 'last_starting11', away: 'last_starting11' },
    ]) {
      expect(headlinePickStatus({ predictionLineups: lineups, centreLineups: lineups })).toEqual({
        status: 'on_tahmin',
        reason: 'lineups_pending',
      });
    }
  });

  it('confirmed line-ups only in the live centre: the picks were computed before them', () => {
    const info = headlinePickStatus({
      predictionLineups: { home: 'predicted', away: 'predicted' },
      centreLineups: { home: 'confirmed', away: 'confirmed' },
    });
    expect(info).toEqual({ status: 'on_tahmin', reason: 'lineups_after_pick' });
    expect(pickStatusLine(info)).toBe('Kadrolar açıklandı; bu seçim kadrolardan önce hesaplandı.');
  });

  it('labels and the one-line hints', () => {
    expect(pickStatusLabel('kesin')).toBe('Kesin');
    expect(pickStatusLabel('on_tahmin')).toBe('Ön tahmin');
    expect(pickStatusLabel('kaydedildi')).toBe('Kaydedildi');
    expect(pickStatusLabel('kayit_disi')).toBe('Kayıtlı değil');
    expect(pickStatusLine({ status: 'on_tahmin', reason: 'lineups_pending' })).toBe(
      'Kadrolar açıklanınca (maçtan ~20 dk önce) kesinleşir.',
    );
    expect(pickStatusLine({ status: 'kaydedildi', reason: 'frozen_unconfirmed' })).toBe(
      'Resmi kadrolar gelmeden kaydedildi; kesin sayılmaz.',
    );
    expect(pickStatusLine({ status: 'kesin', reason: 'frozen' })).toBeNull();
    expect(pickStatusLine({ status: 'kayit_disi', reason: 'differs_from_frozen' })).toBeNull();
    expect(pickCardNote({ status: 'kayit_disi', reason: 'not_frozen' })).toBe('Maç öncesi kayıtta bu seçim yoktu.');
    expect(pickCardNote({ status: 'kayit_disi', reason: 'differs_from_frozen' })).toBeNull();
  });
});

describe('frozenPickStatus / cardPickStatus (per card)', () => {
  const pending: PickStatusInfo = { status: 'on_tahmin', reason: 'lineups_pending' };
  const confirmedLive: PickStatusInfo = { status: 'kesin', reason: 'confirmed_lineups' };
  const confirmed = pick();
  const predicted = pick({ lineup_type: { home: 'predicted', away: 'predicted', source: null } });

  it('a frozen pick is kesin only with confirmed line-ups on both sides', () => {
    expect(frozenPickStatus(confirmed)).toEqual({ status: 'kesin', reason: 'frozen' });
    for (const lineup of [
      { home: 'predicted', away: 'predicted', source: null },
      { home: 'confirmed', away: 'predicted', source: null },
      { home: null, away: null, source: null },
      { home: 'last_starting11', away: 'last_starting11', source: null },
    ] as HeadlinePickItem['lineup_type'][]) {
      expect(frozenPickStatus(pick({ lineup_type: lineup }))).toEqual({ status: 'kaydedildi', reason: 'frozen_unconfirmed' });
    }
  });

  it('the live pick is the frozen pick: the frozen status', () => {
    expect(cardPickStatus({ livePickKey: 'HOME_OR_DRAW', frozen: confirmed, matchFrozen: true, live: pending })).toEqual({
      shown: { status: 'kesin', reason: 'frozen' },
      recorded: null,
    });
    expect(cardPickStatus({ livePickKey: 'HOME_OR_DRAW', frozen: predicted, matchFrozen: true, live: pending }).shown).toEqual({
      status: 'kaydedildi',
      reason: 'frozen_unconfirmed',
    });
    // the same pick computed from confirmed line-ups since: kesin
    expect(
      cardPickStatus({ livePickKey: 'HOME_OR_DRAW', frozen: predicted, matchFrozen: true, live: confirmedLive }).shown,
    ).toEqual(confirmedLive);
  });

  it('the live pick differs from the frozen one: not recorded; the frozen status goes on its own line', () => {
    for (const live of [pending, confirmedLive]) {
      expect(cardPickStatus({ livePickKey: 'OVER_1_5', frozen: confirmed, matchFrozen: true, live })).toEqual({
        shown: { status: 'kayit_disi', reason: 'differs_from_frozen' },
        recorded: { status: 'kesin', reason: 'frozen' },
      });
    }
  });

  it('nothing of this kind frozen while the match was: the live pick is not recorded, never kesin', () => {
    for (const live of [pending, confirmedLive]) {
      expect(cardPickStatus({ livePickKey: 'OVER_1_5', frozen: null, matchFrozen: true, live }).shown).toEqual({
        status: 'kayit_disi',
        reason: 'not_frozen',
      });
    }
  });

  it('no live pick: the card shows the frozen pick with its status; before any freeze the live status', () => {
    expect(cardPickStatus({ livePickKey: null, frozen: confirmed, matchFrozen: true, live: pending })).toEqual({
      shown: { status: 'kesin', reason: 'frozen' },
      recorded: null,
    });
    expect(cardPickStatus({ livePickKey: 'OVER_1_5', frozen: null, matchFrozen: false, live: confirmedLive }).shown).toEqual(
      confirmedLive,
    );
    expect(cardPickStatus({ livePickKey: 'OVER_1_5', frozen: null, matchFrozen: false, live: pending }).shown).toEqual(pending);
  });

  it('the lines under the cards: each reason once', () => {
    const differs = cardPickStatus({ livePickKey: 'OVER_1_5', frozen: predicted, matchFrozen: true, live: pending });
    const same = cardPickStatus({ livePickKey: 'HOME_OR_DRAW', frozen: predicted, matchFrozen: true, live: pending });
    expect(cardStatusLines([differs, same])).toEqual(['Resmi kadrolar gelmeden kaydedildi; kesin sayılmaz.']);
    expect(cardStatusLines([{ shown: pending, recorded: null }, { shown: pending, recorded: null }])).toEqual([
      'Kadrolar açıklanınca (maçtan ~20 dk önce) kesinleşir.',
    ]);
    expect(cardStatusLines([])).toEqual([]);
  });
});

function pick(over: Partial<HeadlinePickItem> = {}): HeadlinePickItem {
  return {
    id: 'p',
    match_id: 'fotmob_1',
    kind: 'banko',
    stage: 'headline_banko',
    home_team: 'Mock Ev',
    away_team: 'Mock Dep',
    competition_id: '42',
    competition_name: 'Mock Kupa',
    kickoff_at: '2026-10-14T19:00:00Z',
    frozen_at: '2026-10-14T18:40:00Z',
    minutes_before_kickoff: 20,
    market_key: 'HOME_OR_DRAW',
    label: '1X',
    selection_text: '1X',
    market_name: 'Çifte Şans',
    probability: 0.81,
    fair_odds: 1.23,
    odds: null,
    lineup_type: { home: 'confirmed', away: 'confirmed', source: 'test' },
    model_1x2: null,
    result: null,
    final_score: null,
    settled_at: null,
    source: 'live_freeze',
    rule_version: 'headline_v1',
    ...over,
  };
}

function record(banko: HeadlinePickItem | null, oranli: HeadlinePickItem | null = null): MatchHeadlineRecord {
  return { match_id: 'fotmob_1', frozen: !!(banko || oranli), picks: { banko, oranli } };
}

describe('resultMark', () => {
  it('uses the two result marks and nothing for a pending pick', () => {
    expect(resultMark('won')?.symbol).toBe('✅');
    expect(resultMark('lost')?.symbol).toBe('❌');
    expect(resultMark('void')?.label).toMatch(/İptal/);
    expect(resultMark(null)).toBeNull();
  });
});

describe('formatRate / formatFinalScore', () => {
  it('says "veri yok" instead of 0', () => {
    expect(formatRate(null)).toBe('veri yok');
    expect(formatRate(undefined)).toBe('veri yok');
    expect(formatRate(0)).toBe('%0');
    expect(formatRate(5 / 7)).toBe('%71');
    expect(formatFinalScore(null)).toBe('veri yok');
    expect(formatFinalScore({ home: null, away: 1 })).toBe('veri yok');
    expect(formatFinalScore({ home: 2, away: 4 })).toBe('2–4');
    expect(formatFinalScore({ home: 0, away: 0 })).toBe('0–0');
  });
});

describe('describeLineup / lineupWord', () => {
  it('names confirmed, predicted, mixed and unknown line-ups', () => {
    expect(describeLineup({ home: 'confirmed', away: 'confirmed', source: null })).toBe('resmi kadro');
    expect(describeLineup({ home: 'predicted', away: 'predicted', source: null })).toBe('tahmini kadro');
    expect(describeLineup({ home: 'confirmed', away: 'predicted', source: null })).toBe('kadro: ev sahibi resmi, deplasman tahmini');
    expect(describeLineup({ home: 'confirmed', away: null, source: null })).toBe('kadro: ev sahibi resmi, deplasman bilgi yok');
    expect(describeLineup({ home: null, away: null, source: null })).toBe('kadro bilgisi yok');
    expect(describeLineup(null)).toBe('kadro bilgisi yok');
    expect(lineupWord({ home: 'confirmed', away: 'confirmed', source: null })).toBe('Resmi');
    expect(lineupWord({ home: 'predicted', away: 'predicted', source: null })).toBe('Tahmini');
    expect(lineupWord({ home: 'confirmed', away: 'predicted', source: null })).toBe('Karışık');
    expect(lineupWord(null)).toBe('veri yok');
  });
});

describe('describeFrozen', () => {
  it('writes the one-line note', () => {
    expect(describeFrozen(record(pick()))).toBe('Maçtan 20 dk önce kaydedildi · resmi kadro');
    expect(describeFrozen(record(pick({ minutes_before_kickoff: 19.6, lineup_type: { home: 'predicted', away: 'predicted', source: null } }))))
      .toBe('Maçtan 20 dk önce kaydedildi · tahmini kadro');
  });

  it('falls back to the Oranlı when only that was frozen, and to nothing when nothing was', () => {
    expect(describeFrozen(record(null, pick({ kind: 'oranli', minutes_before_kickoff: 12 })))).toBe(
      'Maçtan 12 dk önce kaydedildi · resmi kadro',
    );
    expect(describeFrozen(record(null, null))).toBeNull();
    expect(describeFrozen(null)).toBeNull();
  });

  it('marks hand records and missing timing honestly', () => {
    expect(describeFrozen(record(pick({ source: 'manual_record_2026-10-14', minutes_before_kickoff: 2 })))).toBe(
      'Maçtan 2 dk önce elle kaydedildi · resmi kadro',
    );
    expect(describeFrozen(record(pick({ minutes_before_kickoff: null })))).toBe('Maç öncesi kaydedildi · resmi kadro');
  });
});

describe('groupByMatch', () => {
  it('puts Banko and Oranlı of a match in one row, newest kick-off first', () => {
    const rows = groupByMatch([
      pick({ id: '1', match_id: 'a', kickoff_at: '2026-10-14T16:45:00Z' }),
      pick({ id: '2', match_id: 'b', kickoff_at: '2026-10-14T19:00:00Z', kind: 'oranli' }),
      pick({ id: '3', match_id: 'a', kickoff_at: '2026-10-14T16:45:00Z', kind: 'oranli', final_score: { home: 1, away: 1 } }),
      pick({ id: '4', match_id: 'c', kickoff_at: null }),
    ]);
    expect(rows.map((r) => r.match_id)).toEqual(['b', 'a', 'c']);
    expect(rows[1].banko?.id).toBe('1');
    expect(rows[1].oranli?.id).toBe('3');
    expect(rows[1].final_score).toEqual({ home: 1, away: 1 });
    expect(rows[0].banko).toBeNull();
  });
});
