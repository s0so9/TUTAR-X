/**
 * "Şut haritası" — every shot the source plotted, home attacking right and away
 * attacking left. Marker size follows xG (a shot without xG keeps the minimum
 * size and is named as such), goals are filled in the rubric colour. Pressing a
 * shot shows its minute, player, outcome, xG / xGOT, situation and body part.
 */

import { useMemo, useState } from 'react';
import type { LiveShot } from '../../../types/liveCenter';
import {
  formatMinute,
  shotBodyPartLabel,
  shotFrame,
  shotOutcomeLabel,
  shotPoint,
  shotRadius,
  shotSituationLabel,
  shotTotals,
  UNAVAILABLE,
} from './liveCenterModel';

type Filter = 'all' | 'home' | 'away';

interface ShotMapProps {
  shots: LiveShot[];
  teams: { home: string; away: string };
}

function fmtXg(v: number | null): string {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(2) : UNAVAILABLE;
}

function shotLabel(s: LiveShot, teams: { home: string; away: string }): string {
  const minute = formatMinute(s.minute) ?? 'dakika yok';
  return `${minute} ${s.player?.name ?? 'oyuncu bilgisi yok'} (${s.side === 'home' ? teams.home : teams.away}), ${shotOutcomeLabel(s.outcome)}, xG ${fmtXg(s.xg)}`;
}

export function ShotMap({ shots, teams }: ShotMapProps) {
  const [filter, setFilter] = useState<Filter>('all');
  const [selected, setSelected] = useState<number | null>(null);

  const frame = useMemo(() => shotFrame(shots), [shots]);
  const plotted = useMemo(
    () =>
      shots
        .map((s, i) => ({ s, i, pt: shotPoint(s, frame) }))
        .filter((d): d is { s: LiveShot; i: number; pt: { x: number; y: number } } => d.pt !== null)
        // Goals last so they sit on top.
        .sort((a, b) => Number(a.s.outcome === 'goal') - Number(b.s.outcome === 'goal')),
    [shots, frame],
  );
  const unplotted = shots.length - plotted.length;
  const totals = { home: shotTotals(shots, 'home'), away: shotTotals(shots, 'away') };
  const current = selected !== null ? shots[selected] ?? null : null;

  return (
    <div className="lc-shots">
      <div className="lc-stats__bar">
        <div className="lc-seg" role="group" aria-label="Takım filtresi">
          {(
            [
              ['all', 'Tümü'],
              ['home', teams.home],
              ['away', teams.away],
            ] as [Filter, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`lc-seg__btn${filter === key ? ' lc-seg__btn--on' : ''}`}
              aria-pressed={filter === key}
              onClick={() => setFilter(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="lc-shots__totals">
        {(['home', 'away'] as const).map((side) => {
          const t = totals[side];
          return (
            <p key={side} className={`lc-shots__total lc-shots__total--${side}`}>
              <span className={`lc-key lc-key--${side}`} aria-hidden="true" />
              <span className="numeral">{t.shots}</span> şut · <span className="numeral">{t.goals}</span> gol · xG{' '}
              <span className="numeral">{t.xg === null ? UNAVAILABLE : t.xg.toFixed(2)}</span>
              {t.xgMissing > 0 && t.xg !== null && <span className="lc-shots__note"> ({t.xgMissing} şutta xG yok)</span>}
            </p>
          );
        })}
      </div>

      <svg className="lc-shotmap" viewBox="-1 -1 107 70" role="group" aria-label="Şut haritası">
        <g className="lc-shotmap__lines" aria-hidden="true">
          <rect x="0" y="0" width="105" height="68" />
          <line x1="52.5" y1="0" x2="52.5" y2="68" />
          <circle cx="52.5" cy="34" r="9.15" />
          <rect x="0" y="13.84" width="16.5" height="40.32" />
          <rect x="88.5" y="13.84" width="16.5" height="40.32" />
          <rect x="0" y="24.84" width="5.5" height="18.32" />
          <rect x="99.5" y="24.84" width="5.5" height="18.32" />
          <line className="lc-shotmap__goal" x1="0" y1="30.34" x2="0" y2="37.66" />
          <line className="lc-shotmap__goal" x1="105" y1="30.34" x2="105" y2="37.66" />
        </g>
        {plotted.map(({ s, i, pt }) => {
          const dim = filter !== 'all' && s.side !== filter;
          return (
            <circle
              key={i}
              cx={pt.x}
              cy={pt.y}
              r={shotRadius(s.xg)}
              className={`lc-shot lc-shot--${s.side} lc-shot--${s.outcome}${dim ? ' lc-shot--dim' : ''}${selected === i ? ' lc-shot--on' : ''}`}
              tabIndex={dim ? -1 : 0}
              role="button"
              aria-label={shotLabel(s, teams)}
              aria-pressed={selected === i}
              onClick={() => setSelected((cur) => (cur === i ? null : i))}
              onKeyDown={(ev) => {
                if (ev.key === 'Enter' || ev.key === ' ') {
                  ev.preventDefault();
                  setSelected((cur) => (cur === i ? null : i));
                }
              }}
            />
          );
        })}
      </svg>

      <ul className="lc-shots__legend" aria-label="Gösterim">
        <li><span className="lc-legend lc-legend--goal" />Gol</li>
        <li><span className="lc-legend lc-legend--saved" />İsabetli, kurtarıldı</li>
        <li><span className="lc-legend lc-legend--missed" />Dışarı / direk</li>
        <li><span className="lc-legend lc-legend--blocked" />Engellendi</li>
        <li className="lc-shots__legend-size">Büyüklük: xG</li>
      </ul>

      <div className="lc-shots__detail" aria-live="polite">
        {current ? (
          <p>
            <span className="numeral lc-shots__detail-min">{formatMinute(current.minute) ?? '–'}</span>
            <span className="lc-shots__detail-name">{current.player?.name ?? 'oyuncu bilgisi yok'}</span>
            <span>{shotOutcomeLabel(current.outcome)}</span>
            <span>
              xG <span className="numeral">{fmtXg(current.xg)}</span>
            </span>
            <span>
              xGOT <span className="numeral">{fmtXg(current.xgot)}</span>
            </span>
            {shotSituationLabel(current.situation) && <span>{shotSituationLabel(current.situation)}</span>}
            {shotBodyPartLabel(current.body_part) && <span>{shotBodyPartLabel(current.body_part)}</span>}
          </p>
        ) : (
          <p className="lc-caption">Ayrıntı için bir şuta dokunun.</p>
        )}
        {unplotted > 0 && <p className="lc-caption">{unplotted} şutun konumu kaynakta yok; haritada gösterilmedi.</p>}
      </div>
    </div>
  );
}
