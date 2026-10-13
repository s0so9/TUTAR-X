/**
 * MatchLine - the centre-rail line shared by every list surface.
 *
 * Home name right-aligned in the left column, a narrow key between them
 * (see MatchKey), away name left-aligned in the right column. The whole line
 * is one real <Link>; controls such as the favourite button sit outside it
 * so no interactive element is nested inside the link.
 */

import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { MatchLineTone } from './lineFormat';
import './matches.css';

export interface MatchLineProps {
  to: string;
  /** Full accessible name of the link (teams, score/kickoff, status). */
  ariaLabel: string;
  home: string;
  away: string;
  /** Content of the centre key, normally a <MatchKey />. */
  centre: ReactNode;
  tone: MatchLineTone;
  /** Optional trailing cell inside the link (e.g. model 1·X·2). */
  aside?: ReactNode;
  /** Optional controls outside the link (favourite, kombine). */
  actions?: ReactNode;
  className?: string;
}

export function MatchLine({
  to,
  ariaLabel,
  home,
  away,
  centre,
  tone,
  aside,
  actions,
  className,
}: MatchLineProps) {
  return (
    <li className={`tx-line tx-line--${tone}${className ? ` ${className}` : ''}`}>
      <Link
        to={to}
        className={`tx-line__link${aside !== undefined ? ' tx-line__link--aside' : ''}`}
        aria-label={ariaLabel}
      >
        <span className="tx-line__side tx-line__side--home">
          <span className="tx-line__name" title={home}>
            {home}
          </span>
        </span>
        <span className="tx-line__key">{centre}</span>
        <span className="tx-line__side tx-line__side--away">
          <span className="tx-line__name" title={away}>
            {away}
          </span>
        </span>
        {aside !== undefined && <span className="tx-line__aside">{aside}</span>}
      </Link>
      {actions && <span className="tx-line__actions">{actions}</span>}
    </li>
  );
}
