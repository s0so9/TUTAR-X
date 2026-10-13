import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

export interface FavoriteMatch {
  matchId: string;
  homeTeam: string;
  awayTeam: string;
  competition: string;
  scheduledAt: string;
  status: string;
  addedAt: string;
}

interface FavoritesContextType {
  favorites: FavoriteMatch[];
  addToFavorites: (match: Omit<FavoriteMatch, 'addedAt'>) => void;
  removeFromFavorites: (matchId: string) => void;
  isFavorite: (matchId: string) => boolean;
  clearFavorites: () => void;
}

const FavoritesContext = createContext<FavoritesContextType | undefined>(undefined);

const STORAGE_KEY = 'tutar-x-favorites';

export function FavoritesProvider({ children }: { children: ReactNode }) {
  const [favorites, setFavorites] = useState<FavoriteMatch[]>([]);

  // Load favorites from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) {
          setFavorites(parsed);
        }
      }
    } catch (error) {
      console.error('Error loading favorites from localStorage:', error);
    }
  }, []);

  // Save favorites to localStorage whenever favorites change
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(favorites));
    } catch (error) {
      console.error('Error saving favorites to localStorage:', error);
    }
  }, [favorites]);

  const addToFavorites = (match: Omit<FavoriteMatch, 'addedAt'>) => {
    const newFavorite: FavoriteMatch = {
      ...match,
      addedAt: new Date().toISOString(),
    };

    setFavorites(prev => {
      // Check if already exists
      const exists = prev.some(fav => fav.matchId === match.matchId);
      if (exists) {
        return prev; // Don't add duplicates
      }
      return [newFavorite, ...prev]; // Add to beginning
    });
  };

  const removeFromFavorites = (matchId: string) => {
    setFavorites(prev => prev.filter(fav => fav.matchId !== matchId));
  };

  const isFavorite = (matchId: string) => {
    return favorites.some(fav => fav.matchId === matchId);
  };

  const clearFavorites = () => {
    setFavorites([]);
  };

  return (
    <FavoritesContext.Provider
      value={{
        favorites,
        addToFavorites,
        removeFromFavorites,
        isFavorite,
        clearFavorites,
      }}
    >
      {children}
    </FavoritesContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components -- hook is co-located with its provider
export function useFavorites() {
  const context = useContext(FavoritesContext);
  if (context === undefined) {
    throw new Error('useFavorites must be used within a FavoritesProvider');
  }
  return context;
}