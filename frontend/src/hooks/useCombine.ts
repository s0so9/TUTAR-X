/**
 * useCombine Hook
 *
 * Manages combine selections in localStorage for building combo bets.
 * Stores match predictions that can be combined into parlays/accumulators.
 */

import { useState, useEffect, useCallback } from 'react';

const STORAGE_KEY = 'mensione_combine';

export interface CombineItem {
  /** Match ID */
  matchId: string;
  /** Market name (e.g., "İlk Yarı 0.5+ Gol") */
  marketName: string;
  /** Outcome/selection */
  outcome: string;
  /** Real market odds ONLY - never confidence, fair odds, or fabricated values */
  marketOdds: number | null;
  /** AI confidence score (0-1) for display only, NOT for calculation; null when unavailable */
  confidence: number | null;
  /** Team names for display */
  homeTeam: string;
  awayTeam: string;
  /**
   * Optional: model probability (0-1) of this pick, used only for the slip's
   * combined model probability. Missing/null renders "veri yok".
   */
  probability?: number | null;
  /**
   * Optional: where marketOdds came from (backend odds_source);
   * "manual_user_supplied" is labelled unverified in the slip.
   */
  oddsSource?: string | null;
}

/**
 * Load combine items from localStorage
 */
function loadCombineItems(): CombineItem[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      return Array.isArray(parsed) ? parsed : [];
    }
  } catch (error) {
    console.error('Failed to load combine items from localStorage:', error);
  }
  return [];
}

/**
 * Save combine items to localStorage
 */
function saveCombineItems(items: CombineItem[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch (error) {
    console.error('Failed to save combine items to localStorage:', error);
  }
}

export interface UseCombineReturn {
  /** Array of combine items */
  combineItems: CombineItem[];
  /** Add item to combine */
  addToCombine: (item: CombineItem) => void;
  /** Remove item from combine by match ID */
  removeFromCombine: (matchId: string) => void;
  /** Check if match is in combine */
  isInCombine: (matchId: string) => boolean;
  /** Clear all combine items */
  clearCombine: () => void;
  /** Toggle item in combine (add if not present, remove if present) */
  toggleCombine: (item: CombineItem) => void;
}

/**
 * Custom hook for managing combine selections
 */
export function useCombine(): UseCombineReturn {
  const [combineItems, setCombineItems] = useState<CombineItem[]>(loadCombineItems);

  // Sync to localStorage whenever combine items change
  useEffect(() => {
    saveCombineItems(combineItems);
  }, [combineItems]);

  const addToCombine = useCallback((item: CombineItem) => {
    setCombineItems((prev) => {
      // Check if already in combine (by matchId)
      if (prev.some((i) => i.matchId === item.matchId)) {
        return prev; // Already exists, don't duplicate
      }
      return [...prev, item];
    });
  }, []);

  const removeFromCombine = useCallback((matchId: string) => {
    setCombineItems((prev) => prev.filter((item) => item.matchId !== matchId));
  }, []);

  const isInCombine = useCallback(
    (matchId: string) => combineItems.some((item) => item.matchId === matchId),
    [combineItems]
  );

  const clearCombine = useCallback(() => {
    setCombineItems([]);
  }, []);

  const toggleCombine = useCallback((item: CombineItem) => {
    setCombineItems((prev) => {
      const exists = prev.some((i) => i.matchId === item.matchId);
      if (exists) {
        return prev.filter((i) => i.matchId !== item.matchId);
      }
      return [...prev, item];
    });
  }, []);

  return {
    combineItems,
    addToCombine,
    removeFromCombine,
    isInCombine,
    clearCombine,
    toggleCombine,
  };
}
