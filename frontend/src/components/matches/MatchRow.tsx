/**
 * MatchRow - one fixture as a centre-rail line: home | key | away, an optional
 * model 1·X·2 column, and the favourite toggle outside the link.
 */

import { Star } from 'lucide-react';
import { formatProbability } from '../../utils/displayValue';
import { MatchLine } from './MatchLine';
import { MatchKey } from './MatchKey';
import { OutcomeProbabilities } from './OutcomeProbabilities';
import { hasCompleteProbabilities, hasDisplayableScore } from './types';
import type { MatchRowData } from './types';
import { MATCH_STATUS_TEXT, formatKickoffTime, formatLiveMinute, matchLineTone } from './lineFormat';
import './matches.css';

export interface MatchRowProps {
  match: MatchRowData;
  isFavorite?: boolean;
  onToggleFavorite?: (matchId: string) => void;
  /**
   * Render the model 1·X·2 column. Set by the list when at least one of its
   * rows has a loaded prediction, so the column lines up row to row.
   */
  showProbabilities?: boolean;
}

function buildLinkLabel(match: MatchRowData, kickoff: string | null): string {
  const status = MATCH_STATUS_TEXT[match.status] ?? MATCH_STATUS_TEXT.SCHEDULED;
  const parts = [`${match.homeTeam.name} - ${match.awayTeam.name}`];
  if (hasDisplayableScore(match)) {
    parts.push(`skor ${match.homeScore} - ${match.awayScore}`);
  } else {
    parts.push(kickoff ? `başlama saati ${kickoff}` : 'başlama saati bilinmiyor');
  }
  const minute = match.status === 'LIVE' ? formatLiveMinute(match.minute) : null;
  parts.push(minute ? `${status.aria}, dakika ${minute}` : status.aria);
  if (hasCompleteProbabilities(match.probabilities)) {
    const { home, draw, away } = match.probabilities;
    parts.push(
      `model olasılıkları ev ${formatProbability(home)}, beraberlik ${formatProbability(draw)}, deplasman ${formatProbability(away)}`
    );
  }
  return `${parts.join(', ')}. Maç detayına git`;
}

export function MatchRow({
  match,
  isFavorite = false,
  onToggleFavorite,
  showProbabilities = false,
}: MatchRowProps) {
  const kickoff = formatKickoffTime(match.scheduledAt);
  const pairLabel = `${match.homeTeam.name} - ${match.awayTeam.name}`;

  return (
    <MatchLine
      to={`/matches/${match.id}`}
      ariaLabel={buildLinkLabel(match, kickoff)}
      home={match.homeTeam.name}
      away={match.awayTeam.name}
      tone={matchLineTone(match.status)}
      centre={
        <MatchKey
          status={match.status}
          kickoff={kickoff}
          homeScore={match.homeScore}
          awayScore={match.awayScore}
          minute={match.minute}
        />
      }
      aside={
        showProbabilities ? <OutcomeProbabilities probabilities={match.probabilities} /> : undefined
      }
      actions={
        onToggleFavorite ? (
          <button
            type="button"
            className={`tx-line__icon-button${isFavorite ? ' tx-line__icon-button--on' : ''}`}
            onClick={() => onToggleFavorite(match.id)}
            aria-pressed={isFavorite}
            aria-label={isFavorite ? `${pairLabel} favorilerden çıkar` : `${pairLabel} favorilere ekle`}
            title={isFavorite ? 'Favorilerden çıkar' : 'Favorilere ekle'}
          >
            <Star size={16} strokeWidth={1.5} fill={isFavorite ? 'currentColor' : 'none'} aria-hidden="true" />
          </button>
        ) : undefined
      }
    />
  );
}
