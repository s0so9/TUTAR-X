/**
 * The centre of the page header once the match has kicked off: state with a
 * pulse while the ball is rolling, score (ticks when it changes), minute with
 * added time, half-time and penalty scores.
 */

import { useEffect, useRef, useState } from 'react';
import type { LiveCenterResponse } from '../../../types/liveCenter';
import { formatMinute, formatScorePair, isRunning, periodLabel, statusLabel, UNAVAILABLE } from './liveCenterModel';
import './LiveCenter.css';

interface LiveScoreHeadProps {
  data: LiveCenterResponse;
}

export function LiveScoreHead({ data }: LiveScoreHeadProps) {
  const score = formatScorePair(data.score);
  const running = isRunning(data.status);

  const prev = useRef(score);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (prev.current !== score) {
      prev.current = score;
      setTick((t) => t + 1);
    }
  }, [score]);

  const minute = running ? formatMinute(data.minute, data.added_time) : null;
  const period = running ? periodLabel(data.period) : null;
  const ht = formatScorePair(data.halftime_score);
  const showHt = !!ht && data.status !== 'HALF_TIME' && data.period !== '1H';
  const pens = formatScorePair(data.penalty_score);

  return (
    <div className={`lc-head${running ? ' lc-head--running' : ''}`}>
      <span className="lc-head__state">
        {running && <span className="lc-pulse" aria-hidden="true" />}
        {data.status === 'LIVE' ? period ?? statusLabel(data.status) : statusLabel(data.status)}
      </span>
      {score ? (
        <span
          key={tick}
          className={`teams__score numeral${tick > 0 ? ' lc-score--tick' : ''}`}
          aria-label={`Skor ${score}`}
          aria-live="polite"
        >
          {data.score.home}
          <span className="teams__score-sep">–</span>
          {data.score.away}
        </span>
      ) : (
        <span className="lc-head__noscore">Skor: {UNAVAILABLE}</span>
      )}
      {minute && <span className="lc-head__minute numeral">{minute}</span>}
      {(showHt || pens) && (
        <span className="lc-head__sub numeral">
          {showHt && <span title="İlk yarı skoru">İY {ht}</span>}
          {pens && <span title="Penaltı atışları">Pen. {pens}</span>}
        </span>
      )}
    </div>
  );
}
