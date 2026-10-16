/**
 * TEST FIXTURE — MOCK DATA, NOT REAL FOOTBALL DATA.
 *
 * Shaped like GET /api/v1/matches/{id}/live-center (src/types/liveCenter.ts) for
 * unit tests only. Teams, players, minutes and numbers are made up; this file is
 * never imported by application code.
 */

import type {
  LiveCenterResponse,
  LiveLineupPlayer,
  LiveStatItem,
  LiveTeamLineup,
} from '../../../../types/liveCenter';

function starter(
  id: string,
  name: string,
  shirt: number,
  position: LiveLineupPlayer['position'],
  row: number,
  col: number,
  extra: Partial<LiveLineupPlayer> = {},
): LiveLineupPlayer {
  return {
    id,
    name,
    shirt,
    position,
    grid: { row, col, rows_in_formation: 4 },
    captain: false,
    rating: null,
    goals: null,
    assists: null,
    yellow: null,
    red: null,
    sub_out_minute: null,
    ...extra,
  };
}

/** 4-4-2 style test shape with 3 lines + GK (rows 1..4). */
function testLineup(prefix: 'Ev' | 'Dep', withRatings: boolean): LiveTeamLineup {
  const r = (v: number) => (withRatings ? v : null);
  const starters: LiveLineupPlayer[] = [
    starter(`${prefix}-1`, `${prefix} Kaleci Test`, 1, 'GK', 1, 1, { rating: r(6.9) }),
    starter(`${prefix}-2`, `${prefix} Defans Bir`, 2, 'DEF', 2, 1, { rating: r(7.1) }),
    starter(`${prefix}-3`, `${prefix} Defans İki`, 3, 'DEF', 2, 2, { rating: r(6.4), yellow: prefix === 'Dep' ? 2 : null, red: prefix === 'Dep' ? 1 : null }),
    starter(`${prefix}-4`, `${prefix} Defans Üç`, 4, 'DEF', 2, 3, { rating: r(6.8) }),
    starter(`${prefix}-5`, `${prefix} Defans Dört`, 5, 'DEF', 2, 4, { rating: r(7.0) }),
    starter(`${prefix}-6`, `${prefix} Orta Bir`, 6, 'MID', 3, 1, { rating: r(7.4), captain: true }),
    starter(`${prefix}-7`, `${prefix} Orta İki`, 7, 'MID', 3, 2, { rating: r(6.2), sub_out_minute: prefix === 'Ev' ? 61 : null }),
    starter(`${prefix}-8`, `${prefix} Orta Üç`, 8, 'MID', 3, 3, { rating: r(7.8), assists: prefix === 'Ev' ? 1 : null }),
    starter(`${prefix}-9`, `${prefix} Orta Dört`, 10, 'MID', 3, 4, { rating: r(6.6), yellow: prefix === 'Ev' ? 1 : null }),
    starter(`${prefix}-10`, `${prefix} Forvet Bir`, 9, 'FWD', 4, 1, { rating: r(8.3), goals: prefix === 'Ev' ? 2 : null }),
    starter(`${prefix}-11`, `${prefix} Forvet İki`, 11, 'FWD', 4, 2, { rating: r(5.9), goals: prefix === 'Dep' ? 1 : null }),
  ];
  return {
    formation: '4-4-2',
    lineup_type: 'confirmed',
    coach: { id: `${prefix}-coach`, name: `${prefix} Teknik Direktör Test` },
    starters,
    substitutes: [
      {
        ...starter(`${prefix}-12`, `${prefix} Yedek Bir`, 14, 'MID', 0, 0, {
          rating: r(6.5),
          sub_in_minute: prefix === 'Ev' ? 61 : null,
        }),
        grid: null,
      },
      { ...starter(`${prefix}-13`, `${prefix} Yedek Kaleci`, 12, 'GK', 0, 0), grid: null, sub_in_minute: null },
    ],
    unavailable: prefix === 'Ev'
      ? [{ id: 'Ev-inj', name: 'Ev Sakat Oyuncu Test', reason: 'injury', expected_return: 'Kasım sonu' }]
      : [],
  };
}

function stat(
  key: string,
  label: string,
  group: LiveStatItem['group'],
  home: number | null,
  away: number | null,
  unit: LiveStatItem['unit'] = 'count',
  texts: { home?: string; away?: string } = {},
): LiveStatItem {
  return { key, label_tr: label, group, home, away, unit, home_text: texts.home ?? null, away_text: texts.away ?? null };
}

export const TEST_STATS_ALL: LiveStatItem[] = [
  stat('possession', 'Topa sahip olma', 'Genel', 58, 42, 'percent'),
  stat('xg', 'Gol beklentisi (xG)', 'Genel', 1.84, 0.62, 'decimal'),
  stat('total_shots', 'Toplam şut', 'Şutlar', 12, 5),
  stat('shots_on_target', 'İsabetli şut', 'Şutlar', 6, 2),
  stat('corners', 'Korner', 'Genel', 7, 1),
  stat('fouls', 'Faul', 'Disiplin', 9, 14),
  stat('offsides', 'Ofsayt', 'Genel', 2, 3),
  stat('yellow_cards', 'Sarı kart', 'Disiplin', 1, 2),
  stat('red_cards', 'Kırmızı kart', 'Disiplin', 0, 1),
  stat('passes', 'Pas', 'Pas', 421, 302),
  stat('accurate_passes', 'İsabetli pas', 'Pas', 371, 240, 'count', { home: '371 (88%)', away: '240 (79%)' }),
  stat('saves', 'Kurtarış', 'Savunma', 1, 4),
  stat('tackles', 'Top kapma', 'Savunma', null, 11),
];

export const TEST_STATS_FIRST_HALF: LiveStatItem[] = [
  stat('possession', 'Topa sahip olma', 'Genel', 61, 39, 'percent'),
  stat('total_shots', 'Toplam şut', 'Şutlar', 7, 2),
];

/** A live match in the 67th minute: events deliberately out of order. */
export function makeTestLiveCenter(overrides: Partial<LiveCenterResponse> = {}): LiveCenterResponse {
  return {
    match_id: 'test_fixture_0001',
    provider: 'fotmob',
    fetched_at: '2026-10-14T19:52:00Z',
    cache_ttl_seconds: 15,
    status: 'LIVE',
    minute: 67,
    added_time: null,
    period: '2H',
    kickoff: '2026-10-14T19:00:00Z',
    venue: 'Test Stadyumu',
    referee: 'Test Hakem',
    attendance: null,
    score: { home: 2, away: 1 },
    halftime_score: { home: 1, away: 0 },
    penalty_score: null,
    teams: {
      home: { id: 'test-home', name: 'Test Ev FK', short_name: 'Test Ev', logo_url: null },
      away: { id: 'test-away', name: 'Test Deplasman SK', short_name: 'Test Dep', logo_url: null },
    },
    events: [
      {
        id: 'e-sub-61', minute: 61, added_time: null, period: '2H', side: 'home', type: 'substitution',
        player: null, assist: null, player_in: { id: 'Ev-12', name: 'Ev Yedek Bir' }, player_out: { id: 'Ev-7', name: 'Ev Orta İki' },
        score_after: null, detail: null,
      },
      {
        id: 'e-goal-12', minute: 12, added_time: null, period: '1H', side: 'home', type: 'goal',
        player: { id: 'Ev-10', name: 'Ev Forvet Bir' }, assist: { id: 'Ev-8', name: 'Ev Orta Üç' }, player_in: null, player_out: null,
        score_after: { home: 1, away: 0 }, detail: null,
      },
      {
        id: 'e-ht', minute: 45, added_time: 2, period: 'HT', side: null, type: 'period_end',
        player: null, assist: null, player_in: null, player_out: null, score_after: { home: 1, away: 0 }, detail: 'HT',
      },
      {
        id: 'e-yc-45', minute: 45, added_time: 1, period: '1H', side: 'away', type: 'yellow_card',
        player: { id: 'Dep-3', name: 'Dep Defans İki' }, assist: null, player_in: null, player_out: null, score_after: null, detail: null,
      },
      {
        id: 'e-goal-52', minute: 52, added_time: null, period: '2H', side: 'away', type: 'goal',
        player: { id: 'Dep-11', name: 'Dep Forvet İki' }, assist: null, player_in: null, player_out: null,
        score_after: { home: 1, away: 1 }, detail: null,
      },
      {
        id: 'e-2y-58', minute: 58, added_time: null, period: '2H', side: 'away', type: 'second_yellow',
        player: { id: 'Dep-3', name: 'Dep Defans İki' }, assist: null, player_in: null, player_out: null, score_after: null, detail: null,
      },
      {
        id: 'e-var-60', minute: 60, added_time: null, period: '2H', side: 'home', type: 'var',
        player: { id: 'Ev-10', name: 'Ev Forvet Bir' }, assist: null, player_in: null, player_out: null, score_after: null,
        detail: 'Penaltı incelemesi',
      },
      {
        id: 'e-pen-60', minute: 60, added_time: null, period: '2H', side: 'home', type: 'penalty_goal',
        player: { id: 'Ev-10', name: 'Ev Forvet Bir' }, assist: null, player_in: null, player_out: null,
        score_after: { home: 2, away: 1 }, detail: null,
      },
      {
        id: 'e-yc-30', minute: 30, added_time: null, period: '1H', side: 'home', type: 'yellow_card',
        player: { id: 'Ev-9', name: 'Ev Orta Dört' }, assist: null, player_in: null, player_out: null, score_after: null, detail: null,
      },
    ],
    lineups: { home: testLineup('Ev', true), away: testLineup('Dep', true) },
    stats: { all: TEST_STATS_ALL, first_half: TEST_STATS_FIRST_HALF, second_half: null },
    shotmap: [
      { minute: 12, side: 'home', player: { id: 'Ev-10', name: 'Ev Forvet Bir' }, x: 94, y: 34, xg: 0.41, xgot: 0.72, outcome: 'goal', situation: 'RegularPlay', body_part: 'RightFoot' },
      { minute: 33, side: 'home', player: { id: 'Ev-8', name: 'Ev Orta Üç' }, x: 82, y: 25, xg: 0.06, xgot: null, outcome: 'missed', situation: 'RegularPlay', body_part: 'LeftFoot' },
      { minute: 52, side: 'away', player: { id: 'Dep-11', name: 'Dep Forvet İki' }, x: 90, y: 40, xg: 0.22, xgot: 0.51, outcome: 'goal', situation: 'FastBreak', body_part: 'Header' },
      { minute: 57, side: 'away', player: { id: 'Dep-10', name: 'Dep Forvet Bir' }, x: 78, y: 30, xg: null, xgot: null, outcome: 'blocked', situation: 'RegularPlay', body_part: 'RightFoot' },
    ],
    momentum: [
      { minute: 1, value: 10 },
      { minute: 2, value: 35 },
      { minute: 3, value: -20 },
      { minute: 4, value: -60 },
      { minute: 5, value: 15 },
    ],
    missing: [{ section: 'second_half', reason: 'Kaynak 2. yarı istatistiklerini henüz göndermedi.' }],
    ...overrides,
  };
}

/** Same test match before kick-off: predicted line-ups only, no play data. */
export function makeTestPreMatch(): LiveCenterResponse {
  const base = makeTestLiveCenter();
  return {
    ...base,
    status: 'SCHEDULED',
    minute: null,
    period: null,
    score: { home: null, away: null },
    halftime_score: null,
    events: [],
    lineups: {
      home: { ...testLineup('Ev', false), lineup_type: 'predicted' },
      away: { ...testLineup('Dep', false), lineup_type: 'predicted' },
    },
    stats: null,
    shotmap: null,
    momentum: null,
    missing: [
      { section: 'stats', reason: 'Maç başlamadı.' },
      { section: 'shotmap', reason: 'Maç başlamadı.' },
    ],
  };
}
