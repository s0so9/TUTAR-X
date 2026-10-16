/**
 * "Kadrolar" — both starting elevens on one pitch (home attacking right on
 * desktop, upwards on a phone), with shirt numbers, ratings and the events each
 * player was involved in; then bench (with the minute a substitute came on),
 * coach and unavailable players per side. Positions come from the source grid;
 * when it is missing the starters are listed instead of guessing a shape.
 */

import type { CSSProperties } from 'react';
import type { LiveLineupPlayer, LiveTeamLineup } from '../../../types/liveCenter';
import { describeAbsenceReason, describeExpectedReturn } from '../../../utils/squadInfo';
import {
  lineupTypeLabel,
  pitchLayout,
  ratingTone,
  shortPlayerName,
  UNAVAILABLE,
  type PitchSpot,
} from './liveCenterModel';
import { BallGlyph, CardGlyph, SubGlyph } from './LiveGlyphs';

type Side = 'home' | 'away';

interface LineupsPanelProps {
  lineups: { home: LiveTeamLineup | null; away: LiveTeamLineup | null } | null;
  teams: { home: string; away: string };
  missingReason: string | null;
  unavailableMissingReason: string | null;
}

function isCount(v: number | null | undefined): v is number {
  return typeof v === 'number' && Number.isFinite(v) && v > 0;
}

function PlayerMarks({ p, compact = false }: { p: LiveLineupPlayer; compact?: boolean }) {
  const marks: JSX.Element[] = [];
  if (isCount(p.goals)) {
    marks.push(
      <span className="lc-mark lc-mark--goal" key="g" title={`${p.goals} gol`}>
        <BallGlyph size={11} />
        {p.goals > 1 && <span className="numeral">{p.goals}</span>}
      </span>,
    );
  }
  if (isCount(p.assists)) {
    marks.push(
      <span className="lc-mark lc-mark--assist" key="a" title={`${p.assists} asist`}>
        A{p.assists > 1 && <span className="numeral">{p.assists}</span>}
      </span>,
    );
  }
  const yellow = isCount(p.yellow) ? p.yellow : 0;
  const red = isCount(p.red) ? p.red : 0;
  if (yellow >= 2 && red > 0) {
    marks.push(
      <span className="lc-mark" key="c" title="İkinci sarıdan kırmızı">
        <CardGlyph tone="second" size={11} />
      </span>,
    );
  } else {
    if (yellow > 0) {
      marks.push(
        <span className="lc-mark" key="y" title="Sarı kart">
          <CardGlyph tone="yellow" size={11} />
        </span>,
      );
    }
    if (red > 0) {
      marks.push(
        <span className="lc-mark" key="r" title="Kırmızı kart">
          <CardGlyph tone="red" size={11} />
        </span>,
      );
    }
  }
  if (!compact && typeof p.sub_out_minute === 'number') {
    marks.push(
      <span className="lc-mark lc-mark--out" key="o" title={`${p.sub_out_minute}. dakikada çıktı`}>
        <SubGlyph direction="out" size={10} />
        <span className="numeral">{p.sub_out_minute}'</span>
      </span>,
    );
  }
  if (marks.length === 0) return null;
  return <span className="lc-marks">{marks}</span>;
}

function RatingChip({ rating }: { rating: number | null }) {
  if (typeof rating !== 'number' || !Number.isFinite(rating)) return null;
  return (
    <span className={`lc-rating lc-rating--${ratingTone(rating)} numeral`} title="FotMob reytingi">
      {rating.toFixed(1)}
    </span>
  );
}

function playerTitle(p: LiveLineupPlayer): string {
  const parts = [p.shirt !== null && p.shirt !== undefined ? `${p.shirt} · ${p.name}` : p.name];
  if (p.captain) parts.push('kaptan');
  if (typeof p.rating === 'number') parts.push(`reyting ${p.rating.toFixed(1)}`);
  return parts.join(', ');
}

function pct(v: number): string {
  return `${(v * 100).toFixed(2)}%`;
}

function PitchPlayer({ spot, side }: { spot: PitchSpot; side: Side }) {
  const { player: p, depth, lateral } = spot;
  const style = {
    '--x': pct(side === 'home' ? depth / 2 : 1 - depth / 2),
    '--y': pct(side === 'home' ? lateral : 1 - lateral),
    '--vx': pct(side === 'home' ? lateral : 1 - lateral),
    '--vy': pct(side === 'home' ? 1 - depth / 2 : depth / 2),
  } as CSSProperties;
  return (
    <li className={`lc-player lc-player--${side}`} style={style} title={playerTitle(p)}>
      <span className="lc-player__disc numeral">
        {p.shirt ?? '–'}
        {p.captain && <span className="lc-player__cap" aria-label="kaptan">K</span>}
        <RatingChip rating={p.rating} />
      </span>
      <span className="lc-player__name">{shortPlayerName(p.name)}</span>
      <PlayerMarks p={p} />
    </li>
  );
}

function PitchMarkings() {
  return (
    <>
      <svg className="lc-pitch__lines lc-pitch__lines--h" viewBox="0 0 105 68" preserveAspectRatio="none" aria-hidden="true">
        <rect x="0.4" y="0.4" width="104.2" height="67.2" />
        <line x1="52.5" y1="0.4" x2="52.5" y2="67.6" />
        <circle cx="52.5" cy="34" r="9.15" />
        <rect x="0.4" y="13.84" width="16.5" height="40.32" />
        <rect x="88.1" y="13.84" width="16.5" height="40.32" />
        <rect x="0.4" y="24.84" width="5.5" height="18.32" />
        <rect x="99.1" y="24.84" width="5.5" height="18.32" />
      </svg>
      <svg className="lc-pitch__lines lc-pitch__lines--v" viewBox="0 0 68 105" preserveAspectRatio="none" aria-hidden="true">
        <rect x="0.4" y="0.4" width="67.2" height="104.2" />
        <line x1="0.4" y1="52.5" x2="67.6" y2="52.5" />
        <circle cx="34" cy="52.5" r="9.15" />
        <rect x="13.84" y="0.4" width="40.32" height="16.5" />
        <rect x="13.84" y="88.1" width="40.32" height="16.5" />
        <rect x="24.84" y="0.4" width="18.32" height="5.5" />
        <rect x="24.84" y="99.1" width="18.32" height="5.5" />
      </svg>
    </>
  );
}

function StarterList({ lineup }: { lineup: LiveTeamLineup }) {
  return (
    <ul className="lc-bench">
      {lineup.starters.map((p, i) => (
        <li key={`${p.id ?? p.name}-${i}`} className="lc-bench__row">
          <span className="lc-bench__shirt numeral">{p.shirt ?? '–'}</span>
          <span className="lc-bench__name">
            {p.name}
            {p.captain && <span className="lc-bench__cap"> (K)</span>}
          </span>
          <PlayerMarks p={p} />
          <RatingChip rating={p.rating} />
        </li>
      ))}
    </ul>
  );
}

function TeamExtras({
  lineup,
  side,
  teamName,
  unavailableMissingReason,
}: {
  lineup: LiveTeamLineup | null;
  side: Side;
  teamName: string;
  unavailableMissingReason: string | null;
}) {
  if (!lineup) {
    return (
      <section className={`lc-team-extra lc-team-extra--${side}`} aria-label={`${teamName} kadro`}>
        <p className="lc-empty">{teamName} kadrosu: {UNAVAILABLE}</p>
      </section>
    );
  }
  const subsOn = lineup.substitutes.filter((p) => typeof p.sub_in_minute === 'number');
  const bench = [
    ...subsOn.sort((a, b) => (a.sub_in_minute as number) - (b.sub_in_minute as number)),
    ...lineup.substitutes.filter((p) => typeof p.sub_in_minute !== 'number'),
  ];
  return (
    <section className={`lc-team-extra lc-team-extra--${side}`} aria-label={`${teamName} yedekler ve eksikler`}>
      <h3 className="lc-team-extra__title">
        <span className={`lc-key lc-key--${side}`} aria-hidden="true" />
        {teamName}
      </h3>

      <h4 className="apparatus lc-team-extra__label">Teknik direktör</h4>
      <p className="lc-team-extra__coach">{lineup.coach?.name ?? UNAVAILABLE}</p>

      <h4 className="apparatus lc-team-extra__label">Yedekler</h4>
      {bench.length === 0 ? (
        <p className="lc-empty">Yedek listesi: {UNAVAILABLE}</p>
      ) : (
        <ul className="lc-bench">
          {bench.map((p, i) => (
            <li key={`${p.id ?? p.name}-${i}`} className={`lc-bench__row${typeof p.sub_in_minute === 'number' ? ' lc-bench__row--on' : ''}`}>
              <span className="lc-bench__shirt numeral">{p.shirt ?? '–'}</span>
              <span className="lc-bench__name">{p.name}</span>
              {typeof p.sub_in_minute === 'number' && (
                <span className="lc-bench__in" title={`${p.sub_in_minute}. dakikada girdi`}>
                  <SubGlyph direction="in" size={10} />
                  <span className="numeral">{p.sub_in_minute}'</span>
                </span>
              )}
              <PlayerMarks p={p} compact />
              <RatingChip rating={p.rating} />
            </li>
          ))}
        </ul>
      )}

      <h4 className="apparatus lc-team-extra__label">Eksikler</h4>
      {unavailableMissingReason ? (
        <p className="lc-empty">{UNAVAILABLE} — {unavailableMissingReason}</p>
      ) : lineup.unavailable.length === 0 ? (
        <p className="lc-empty">Bildirilen eksik yok</p>
      ) : (
        <ul className="lc-out-list">
          {lineup.unavailable.map((p, i) => (
            <li key={`${p.id ?? p.name}-${i}`}>
              <span className="lc-out-list__name">{p.name}</span>
              <span className="lc-out-list__meta">
                {describeAbsenceReason(p.reason)} · dönüş: {describeExpectedReturn(p.expected_return)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function TeamHead({ lineup, side, teamName }: { lineup: LiveTeamLineup | null; side: Side; teamName: string }) {
  const type = lineupTypeLabel(lineup?.lineup_type);
  return (
    <div className={`lc-lineups__team lc-lineups__team--${side}`}>
      <span className={`lc-key lc-key--${side}`} aria-hidden="true" />
      <span className="lc-lineups__name">{teamName}</span>
      <span className="lc-lineups__formation numeral">{lineup?.formation ?? 'diziliş: veri yok'}</span>
      {type && <span className={`lc-tag${lineup?.lineup_type === 'confirmed' ? '' : ' lc-tag--soft'}`}>{type}</span>}
    </div>
  );
}

export function LineupsPanel({ lineups, teams, missingReason, unavailableMissingReason }: LineupsPanelProps) {
  const home = lineups?.home ?? null;
  const away = lineups?.away ?? null;
  if (!home && !away) {
    return (
      <p className="lc-empty">
        Kadrolar: {UNAVAILABLE}
        {missingReason ? ` — ${missingReason}` : ''}
      </p>
    );
  }

  const homeSpots = pitchLayout(home?.starters);
  const awaySpots = pitchLayout(away?.starters);
  const showPitch = homeSpots !== null || awaySpots !== null;

  return (
    <div className="lc-lineups">
      <div className="lc-lineups__head">
        <TeamHead lineup={home} side="home" teamName={teams.home} />
        <TeamHead lineup={away} side="away" teamName={teams.away} />
      </div>

      {showPitch && (
        <div className="lc-pitch" role="group" aria-label={`İlk 11'ler: ${teams.home} ve ${teams.away}`}>
          <PitchMarkings />
          <ul className="lc-pitch__players">
            {homeSpots?.map((s, i) => <PitchPlayer key={`h-${s.player.id ?? i}`} spot={s} side="home" />)}
            {awaySpots?.map((s, i) => <PitchPlayer key={`a-${s.player.id ?? i}`} spot={s} side="away" />)}
          </ul>
          {!homeSpots && <p className="lc-pitch__note lc-pitch__note--home">{home ? 'Saha dizilişi verisi yok' : `Kadro: ${UNAVAILABLE}`}</p>}
          {!awaySpots && <p className="lc-pitch__note lc-pitch__note--away">{away ? 'Saha dizilişi verisi yok' : `Kadro: ${UNAVAILABLE}`}</p>}
        </div>
      )}

      {(!homeSpots || !awaySpots) && (home || away) && (
        <div className="lc-lineups__cols">
          <div>{!homeSpots && home && <StarterList lineup={home} />}</div>
          <div>{!awaySpots && away && <StarterList lineup={away} />}</div>
        </div>
      )}

      <div className="lc-lineups__cols">
        <TeamExtras lineup={home} side="home" teamName={teams.home} unavailableMissingReason={unavailableMissingReason} />
        <TeamExtras lineup={away} side="away" teamName={teams.away} unavailableMissingReason={unavailableMissingReason} />
      </div>
    </div>
  );
}
