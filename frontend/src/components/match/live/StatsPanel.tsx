/**
 * "İstatistikler" — paired values with a two-way bar, grouped Genel / Şutlar /
 * Pas / Savunma / Disiplin, for the whole match or either half. Only the
 * statistics the source sent are listed; a side the source left empty reads
 * "veri yok" and gets no bar.
 */

import { useState } from 'react';
import type { LiveStats } from '../../../types/liveCenter';
import {
  formatStatValue,
  groupStats,
  STAT_HALVES,
  statLeader,
  statShares,
  statsForHalf,
  UNAVAILABLE,
  type StatHalf,
} from './liveCenterModel';

interface StatsPanelProps {
  stats: LiveStats | null;
  teams: { home: string; away: string };
  missingReason: string | null;
  halfMissingReason: { first_half: string | null; second_half: string | null };
}

export function StatsPanel({ stats, teams, missingReason, halfMissingReason }: StatsPanelProps) {
  const [half, setHalf] = useState<StatHalf>('all');

  if (!stats || !statsForHalf(stats, 'all')) {
    return (
      <p className="lc-empty">
        İstatistik: {UNAVAILABLE}
        {missingReason ? ` — ${missingReason}` : ''}
      </p>
    );
  }

  const items = statsForHalf(stats, half);
  const groups = groupStats(items);
  const halfReason = half === 'all' ? null : halfMissingReason[half];

  return (
    <div className="lc-stats">
      <div className="lc-stats__bar">
        <div className="lc-seg" role="group" aria-label="Maç bölümü">
          {STAT_HALVES.map((h) => {
            const available = statsForHalf(stats, h.key) !== null;
            return (
              <button
                key={h.key}
                type="button"
                className={`lc-seg__btn${half === h.key ? ' lc-seg__btn--on' : ''}`}
                aria-pressed={half === h.key}
                onClick={() => setHalf(h.key)}
                title={available ? undefined : `${h.label}: ${UNAVAILABLE}`}
              >
                {h.label}
              </button>
            );
          })}
        </div>
        <p className="lc-stats__teams" aria-hidden="true">
          <span className="lc-key lc-key--home" />
          {teams.home}
          <span className="lc-stats__teams-sep">·</span>
          <span className="lc-key lc-key--away" />
          {teams.away}
        </p>
      </div>

      {groups.length === 0 ? (
        <p className="lc-empty">
          {STAT_HALVES.find((h) => h.key === half)?.label} istatistikleri: {UNAVAILABLE}
          {halfReason ? ` — ${halfReason}` : ''}
        </p>
      ) : (
        <div className="lc-stats__groups" key={half}>
          {groups.map((g) => (
            <section className="lc-stat-group" key={g.group} aria-label={g.group}>
              <h3 className="lc-stat-group__title apparatus">{g.group}</h3>
              <ul className="lc-stat-list">
                {g.items.map((item) => {
                  const shares = statShares(item);
                  const leader = statLeader(item);
                  const homeText = formatStatValue(item, 'home');
                  const awayText = formatStatValue(item, 'away');
                  return (
                    <li className="lc-stat" key={item.key} data-stat-key={item.key}>
                      <span
                        className={`lc-stat__v lc-stat__v--home numeral${leader === 'home' ? ' lc-stat__v--lead' : ''}${homeText === UNAVAILABLE ? ' lc-stat__v--na' : ''}`}
                      >
                        {homeText}
                      </span>
                      <span className="lc-stat__label">{item.label_tr}</span>
                      <span
                        className={`lc-stat__v lc-stat__v--away numeral${leader === 'away' ? ' lc-stat__v--lead' : ''}${awayText === UNAVAILABLE ? ' lc-stat__v--na' : ''}`}
                      >
                        {awayText}
                      </span>
                      {shares && (
                        <div className="lc-stat__bars" aria-hidden="true">
                          <span className="lc-stat__track lc-stat__track--home">
                            <span
                              className={`lc-stat__fill lc-stat__fill--home${leader === 'away' ? ' lc-stat__fill--trail' : ''}`}
                              style={{ width: `${(shares.home * 100).toFixed(1)}%` }}
                            />
                          </span>
                          <span className="lc-stat__track lc-stat__track--away">
                            <span
                              className={`lc-stat__fill lc-stat__fill--away${leader === 'home' ? ' lc-stat__fill--trail' : ''}`}
                              style={{ width: `${(shares.away * 100).toFixed(1)}%` }}
                            />
                          </span>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
