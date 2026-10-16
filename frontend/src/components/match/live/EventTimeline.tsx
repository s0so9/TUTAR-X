/**
 * "Özet" — the match's events on the page's two-sided grid: home events in the
 * left column, away events in the right, the minute (and the score after a
 * goal) in the centre column. Newest on top while the match is being played,
 * kick-off on top once it is over. Events that arrive with a poll slide in.
 */

import { useEffect, useMemo, useRef } from 'react';
import type { LiveCenterStatus, LiveEvent, LivePersonRef } from '../../../types/liveCenter';
import {
  eventKey,
  formatMinute,
  formatScorePair,
  isGoalEvent,
  isInPlay,
  periodEndLabel,
  sortEvents,
  UNAVAILABLE,
} from './liveCenterModel';
import { BallGlyph, CardGlyph, MissedPenaltyGlyph, SubGlyph, VarGlyph } from './LiveGlyphs';

interface EventTimelineProps {
  events: LiveEvent[] | null;
  status: LiveCenterStatus;
  teams: { home: string; away: string };
  missingReason: string | null;
}

function name(p: LivePersonRef | null | undefined): string {
  return p?.name?.trim() ? p.name : 'oyuncu bilgisi yok';
}

function EventBody({ e }: { e: LiveEvent }) {
  const detail = e.detail?.trim() ? e.detail : null;
  switch (e.type) {
    case 'goal':
    case 'penalty_goal':
    case 'own_goal':
      return (
        <>
          <span className="lc-ev__icon lc-ev__icon--goal"><BallGlyph /></span>
          <span className="lc-ev__text">
            <span className="lc-ev__main lc-ev__main--strong">
              {name(e.player)}
              {e.type === 'penalty_goal' && <span className="lc-ev__tag">Penaltı</span>}
              {e.type === 'own_goal' && <span className="lc-ev__tag">Kendi kalesine</span>}
            </span>
            {e.assist && <span className="lc-ev__sub">Asist: {name(e.assist)}</span>}
            {detail && <span className="lc-ev__sub">{detail}</span>}
          </span>
        </>
      );
    case 'penalty_missed':
      return (
        <>
          <span className="lc-ev__icon"><MissedPenaltyGlyph /></span>
          <span className="lc-ev__text">
            <span className="lc-ev__main">{name(e.player)}</span>
            <span className="lc-ev__sub">Kaçan penaltı{detail ? ` · ${detail}` : ''}</span>
          </span>
        </>
      );
    case 'yellow_card':
    case 'second_yellow':
    case 'red_card':
      return (
        <>
          <span className="lc-ev__icon">
            <CardGlyph tone={e.type === 'yellow_card' ? 'yellow' : e.type === 'red_card' ? 'red' : 'second'} />
          </span>
          <span className="lc-ev__text">
            <span className="lc-ev__main">{name(e.player)}</span>
            <span className="lc-ev__sub">
              {e.type === 'yellow_card' ? 'Sarı kart' : e.type === 'red_card' ? 'Kırmızı kart' : 'İkinci sarıdan kırmızı'}
              {detail ? ` · ${detail}` : ''}
            </span>
          </span>
        </>
      );
    case 'substitution':
      return (
        <>
          <span className="lc-ev__icon lc-ev__icon--sub" aria-hidden="true">
            <SubGlyph direction="in" />
          </span>
          <span className="lc-ev__text">
            <span className="lc-ev__main lc-ev__in">
              <span className="sr-only">Giren: </span>
              {e.player_in ? e.player_in.name : UNAVAILABLE}
            </span>
            <span className="lc-ev__sub lc-ev__out">
              <SubGlyph direction="out" size={10} />
              <span className="sr-only">Çıkan: </span>
              {e.player_out ? e.player_out.name : UNAVAILABLE}
            </span>
          </span>
        </>
      );
    case 'var':
      return (
        <>
          <span className="lc-ev__icon"><VarGlyph /></span>
          <span className="lc-ev__text">
            <span className="lc-ev__main">{detail ?? 'VAR incelemesi'}</span>
            {e.player && <span className="lc-ev__sub">{e.player.name}</span>}
          </span>
        </>
      );
    default:
      return (
        <span className="lc-ev__text">
          <span className="lc-ev__main">{detail ?? e.type}</span>
        </span>
      );
  }
}

export function EventTimeline({ events, status, teams, missingReason }: EventTimelineProps) {
  const ordered = useMemo(() => {
    const chrono = sortEvents(events);
    return isInPlay(status) ? [...chrono].reverse() : chrono;
  }, [events, status]);

  // Keys rendered before: events missing from this set arrived with a poll.
  const seen = useRef<Set<string> | null>(null);
  const keys = ordered.map((e, i) => eventKey(e, i));
  const fresh = seen.current ? new Set(keys.filter((k) => !seen.current?.has(k))) : new Set<string>();
  useEffect(() => {
    const next = seen.current ?? new Set<string>();
    keys.forEach((k) => next.add(k));
    seen.current = next;
  });

  if (events === null) {
    return (
      <p className="lc-empty">
        Olay akışı: {UNAVAILABLE}
        {missingReason ? ` — ${missingReason}` : ''}
      </p>
    );
  }
  if (ordered.length === 0) {
    return <p className="lc-empty">{status === 'SCHEDULED' ? 'Maç henüz başlamadı.' : 'Henüz olay yok.'}</p>;
  }

  return (
    <div className="lc-timeline">
      <p className="lc-caption">{isInPlay(status) ? 'En yeni olay üstte' : 'Başlama vuruşundan itibaren'}</p>
      <ol className="lc-tl" aria-label="Maç olayları">
        {ordered.map((e, i) => {
          const key = keys[i];
          const isNew = fresh.has(key);
          if (e.type === 'period_end') {
            const score = formatScorePair(e.score_after);
            return (
              <li key={key} className={`lc-tl__marker${isNew ? ' lc-tl--new' : ''}`} data-event-type={e.type}>
                <span>{periodEndLabel(e)}</span>
                {score && <span className="numeral lc-tl__marker-score">{score}</span>}
              </li>
            );
          }
          const minute = formatMinute(e.minute, e.added_time) ?? '–';
          const score = isGoalEvent(e) ? formatScorePair(e.score_after) : null;
          const side = e.side;
          const teamName = side === 'home' ? teams.home : side === 'away' ? teams.away : null;
          return (
            <li
              key={key}
              className={`lc-tl__row lc-tl__row--${side ?? 'none'}${isGoalEvent(e) ? ' lc-tl__row--goal' : ''}${isNew ? ' lc-tl--new' : ''}`}
              data-event-type={e.type}
            >
              <div className="lc-tl__side lc-tl__side--home">
                {side === 'home' && (
                  <div className="lc-ev lc-ev--home">
                    <EventBody e={e} />
                  </div>
                )}
              </div>
              <div className="lc-tl__minute">
                <span className="numeral">{minute}</span>
                {score && <span className="numeral lc-tl__score">{score}</span>}
                {teamName && <span className="sr-only">{teamName}</span>}
              </div>
              <div className="lc-tl__side lc-tl__side--away">
                {side !== 'home' && (
                  <div className="lc-ev lc-ev--away">
                    <EventBody e={e} />
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
