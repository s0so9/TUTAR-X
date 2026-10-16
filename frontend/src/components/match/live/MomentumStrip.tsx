/**
 * Momentum strip: FotMob's per-minute pressure value (−100…100) as thin bars,
 * home above the axis, away below, goals marked on the edge of their side.
 */

import type { LiveEvent, LiveMomentumPoint } from '../../../types/liveCenter';
import { isGoalEvent, momentumSeries } from './liveCenterModel';

interface MomentumStripProps {
  points: LiveMomentumPoint[];
  events: LiveEvent[] | null;
  teams: { home: string; away: string };
}

const H = 22; // half height in view units

export function MomentumStrip({ points, events, teams }: MomentumStripProps) {
  const series = momentumSeries(points);
  if (series.length === 0) return null;
  const last = series[series.length - 1].minute;
  const span = Math.max(90, last + 1);
  const goals = (events ?? []).filter(
    (e) => isGoalEvent(e) && typeof e.minute === 'number' && (e.side === 'home' || e.side === 'away'),
  );

  return (
    <figure className="lc-momentum">
      <figcaption className="lc-momentum__cap">
        <span className="apparatus">Baskı</span>
        <span className="lc-momentum__legend">
          <span className="lc-key lc-key--home" aria-hidden="true" /> {teams.home} yukarı
          <span className="lc-momentum__sep">·</span>
          <span className="lc-key lc-key--away" aria-hidden="true" /> {teams.away} aşağı
        </span>
      </figcaption>
      <svg
        className="lc-momentum__svg"
        viewBox={`0 ${-H - 4} ${span} ${2 * H + 8}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`Maç baskı grafiği, ${series.length} dakika (FotMob)`}
      >
        <line className="lc-momentum__axis" x1="0" y1="0" x2={span} y2="0" />
        {span > 45 && <line className="lc-momentum__half" x1="45" y1={-H - 4} x2="45" y2={H + 4} />}
        {series.map((p) => {
          const h = (Math.abs(p.value) / 100) * H;
          if (h === 0) return null;
          return (
            <rect
              key={p.minute}
              className={`lc-momentum__bar lc-momentum__bar--${p.value > 0 ? 'home' : 'away'}`}
              x={p.minute - 0.42}
              width={0.84}
              y={p.value > 0 ? -h : 0}
              height={h}
            />
          );
        })}
        {goals.map((g, i) => (
          <rect
            key={`${g.id}-${i}`}
            className="lc-momentum__goal"
            x={(g.minute as number) - 0.6}
            width={1.2}
            y={g.side === 'home' ? -H - 4 : H + 1}
            height={3}
          />
        ))}
      </svg>
      <div className="lc-momentum__ticks numeral" aria-hidden="true">
        <span>0'</span>
        <span style={{ left: `${(45 / span) * 100}%` }}>45'</span>
        <span style={{ left: `${(90 / span) * 100}%` }}>90'</span>
      </div>
    </figure>
  );
}
