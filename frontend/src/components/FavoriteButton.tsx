import React from 'react';
import { useFavorites } from '../contexts/FavoritesContext';
import type { MatchResponse } from '../api/types';
import { normalizeMatch } from '../utils/matchNormalizer';

interface FavoriteButtonProps {
  match: MatchResponse;
  className?: string;
  style?: React.CSSProperties;
}

export function FavoriteButton({ match, className = '', style = {} }: FavoriteButtonProps) {
  const { addToFavorites, removeFromFavorites, isFavorite } = useFavorites();
  
  const isMatchFavorite = isFavorite(match.id);
  const normalizedMatch = normalizeMatch(match);

  const handleToggleFavorite = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    if (isMatchFavorite) {
      removeFromFavorites(match.id);
    } else {
      addToFavorites({
        matchId: match.id,
        homeTeam: normalizedMatch.homeTeam.name,
        awayTeam: normalizedMatch.awayTeam.name,
        competition: match.competition_id,
        scheduledAt: match.scheduled_at,
        status: match.status,
      });
    }
  };

  return (
    <button
      onClick={handleToggleFavorite}
      className={`favorite-button ${isMatchFavorite ? 'is-favorite' : ''} ${className}`}
      title={isMatchFavorite ? 'Favorilerden kaldır' : 'Favorilere ekle'}
      style={{
        background: 'transparent',
        border: 'none',
        color: isMatchFavorite ? '#ffb400' : '#ccc',
        fontSize: '1.25rem',
        cursor: 'pointer',
        padding: '0.25rem',
        borderRadius: '4px',
        transition: 'color 0.2s ease',
        ...style,
      }}
    >
      {isMatchFavorite ? '★' : '☆'}
    </button>
  );
}