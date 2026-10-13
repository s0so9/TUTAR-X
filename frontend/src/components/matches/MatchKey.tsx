/**
 * MatchKey - the centre key of a rail line: kickoff time, live score + minute
 * (rubric), or the final score. Scores are only shown once a match has started;
 * a scheduled match never shows a 0-0 placeholder.
 */

import type { MatchStatus } from '../../api/types';
import { hasDisplayableScore } from './types';
import { MATCH_STATUS_TEXT, formatLiveMinute } from './lineFormat';
import './matches.css';

export interface MatchKeyProps {
  status: MatchStatus;
  /** Formatted kickoff time ("22:00"); null when unknown. */
  kickoff: string | null;
  homeScore: number | null;
  awayScore: number | null;
  minute?: number | null;
  addedTime?: number | null;
  /** Replaces the status note (e.g. "Devre arası" for a live match at half-time). */
  noteOverride?: string | null;
}

export function MatchKey({ status, kickoff, homeScore, awayScore, minute, addedTime, noteOverride }: MatchKeyProps) {
  const showScore = hasDisplayableScore({ status, homeScore, awayScore });
  const liveMinute = status === 'LIVE' && !noteOverride ? formatLiveMinute(minute, addedTime) : null;
  const note = noteOverride ?? liveMinute ?? MATCH_STATUS_TEXT[status]?.note ?? null;

  return (
    <span className="tx-key">
      <span className="tx-key__figure">
        {showScore ? (
          <>
            {homeScore}
            <span className="tx-key__sep" aria-hidden="true">
              –
            </span>
            {awayScore}
          </>
        ) : (
          kickoff ?? <span className="tx-key__unknown">saat yok</span>
        )}
      </span>
      {note && (
        <span className={`tx-key__note${liveMinute ? ' tx-key__note--minute' : ''}`}>
          {status === 'LIVE' && <span className="tx-key__marker" aria-hidden="true" />}
          {note}
        </span>
      )}
    </span>
  );
}
