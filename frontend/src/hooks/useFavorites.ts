/**
 * useFavorites Hook
 * 
 * Manages favorite match IDs in localStorage with type-safe operations.
 * Provides toggle, check, and list functionality for favorite matches.
 */

import { useState, useEffect, useCallback } from 'react';

const STORAGE_KEY = 'mensione_favorites';

/**
 * Load favorites from localStorage
 */
function loadFavorites(): Set<string> {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      return new Set(Array.isArray(parsed) ? parsed : []);
    }
  } catch (error) {
    console.error('Failed to load favorites from localStorage:', error);
  }
  return new Set();
}

/**
 * Save favorites to localStorage
 */
function saveFavorites(favorites: Set<string>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(favorites)));
  } catch (error) {
    console.error('Failed to save favorites to localStorage:', error);
  }
}

export interface UseFavoritesReturn {
  /** Set of favorite match IDs */
  favorites: Set<string>;
  /** Toggle favorite status for a match ID */
  toggleFavorite: (matchId: string) => void;
  /** Check if a match ID is favorited */
  isFavorite: (matchId: string) => boolean;
  /** Clear all favorites */
  clearFavorites: () => void;
}

/**
 * Custom hook for managing favorite matches
 */
export function useFavorites(): UseFavoritesReturn {
  const [favorites, setFavorites] = useState<Set<string>>(loadFavorites);

  // Sync to localStorage whenever favorites change
  useEffect(() => {
    saveFavorites(favorites);
  }, [favorites]);

  const toggleFavorite = useCallback((matchId: string) => {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(matchId)) {
        next.delete(matchId);
      } else {
        next.add(matchId);
      }
      return next;
    });
  }, []);

  const isFavorite = useCallback(
    (matchId: string) => favorites.has(matchId),
    [favorites]
  );

  const clearFavorites = useCallback(() => {
    setFavorites(new Set());
  }, []);

  return {
    favorites,
    toggleFavorite,
    isFavorite,
    clearFavorites,
  };
}
