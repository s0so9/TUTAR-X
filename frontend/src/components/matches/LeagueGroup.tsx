/**
 * LeagueGroup - a competition's fixtures as hairline-ruled rail lines under a
 * small-caps heading. The heading is a real button that collapses the list.
 */

import { useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { MatchRow } from './MatchRow';
import { leagueNameLang } from './types';
import type { MatchRowData } from './types';
import './matches.css';

export interface LeagueGroupProps {
  leagueName: string;
  matches: MatchRowData[];
  /** Optional secondary line, e.g. the country. */
  subtitle?: string;
  defaultExpanded?: boolean;
  isFavorite?: (matchId: string) => boolean;
  onToggleFavorite?: (matchId: string) => void;
  /**
   * Show the model 1·X·2 column. Pages pass one value for every group so the
   * column (and the rail) line up across groups; when omitted the group shows
   * it only if one of its own rows has probabilities.
   */
  showProbabilities?: boolean;
}

export function LeagueGroup({
  leagueName,
  matches,
  subtitle,
  defaultExpanded = true,
  isFavorite,
  onToggleFavorite,
  showProbabilities,
}: LeagueGroupProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const listId = useId();
  const liveCount = matches.filter((m) => m.status === 'LIVE').length;
  const withProbabilities = showProbabilities ?? matches.some((m) => !!m.probabilities);

  const sortedMatches = [...matches].sort(
    (a, b) => new Date(a.scheduledAt).getTime() - new Date(b.scheduledAt).getTime()
  );

  return (
    <section
      className={`tx-league-group${expanded ? '' : ' tx-league-group--collapsed'}`}
      aria-label={`${leagueName} maçları`}
    >
      <h3 className="tx-league-group__heading">
        <button
          type="button"
          className="tx-league-group__toggle"
          aria-expanded={expanded}
          aria-controls={listId}
          onClick={() => setExpanded((prev) => !prev)}
        >
          <ChevronDown className="tx-league-group__chevron" size={16} strokeWidth={1.5} aria-hidden="true" />
          <span className="tx-league-group__titles">
            <span className="tx-league-group__name" lang={leagueNameLang(leagueName)}>
              {leagueName}
            </span>
            {subtitle && <span className="tx-league-group__subtitle">{subtitle}</span>}
          </span>
          <span className="tx-league-group__meta">
            {liveCount > 0 && <span className="tx-league-group__live">{liveCount} canlı</span>}
            <span className="tx-league-group__count">{matches.length} maç</span>
          </span>
        </button>
      </h3>

      {expanded && withProbabilities && (
        <div
          className={`tx-league-group__columns${onToggleFavorite ? ' tx-league-group__columns--actions' : ''}`}
          aria-hidden="true"
        >
          <span className="tx-league-group__columns-label">Model</span>
          <span className="tx-probs tx-probs--heads">
            <span className="tx-probs__cell">1</span>
            <span className="tx-probs__cell">X</span>
            <span className="tx-probs__cell">2</span>
          </span>
        </div>
      )}

      <ul id={listId} className="tx-league-group__list" hidden={!expanded}>
        {sortedMatches.map((match) => (
          <MatchRow
            key={match.id}
            match={match}
            isFavorite={isFavorite ? isFavorite(match.id) : false}
            onToggleFavorite={onToggleFavorite}
            showProbabilities={withProbabilities}
          />
        ))}
      </ul>
    </section>
  );
}
