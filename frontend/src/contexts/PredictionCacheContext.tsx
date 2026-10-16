import { createContext, useContext, useState, useCallback, useRef, ReactNode } from 'react';
import type { MatchPredictionResponse } from '../api/types';

/**
 * Prediction Cache Context
 * 
 * Provides a centralized cache for match predictions to avoid duplicate
 * API requests and enable lazy loading of predictions.
 */

interface PredictionState {
  prediction: MatchPredictionResponse | null;
  loading: boolean;
  error: Error | null;
}

interface PredictionCacheContextType {
  // Get cached prediction or current loading state
  getPrediction: (matchId: string) => PredictionState | undefined;
  
  // Set a prediction in the cache (from Dashboard preload or lazy load)
  setPrediction: (matchId: string, prediction: MatchPredictionResponse) => void;
  
  // Mark a prediction as loading to prevent duplicate requests
  setLoading: (matchId: string) => void;
  
  // Mark a prediction as errored
  setError: (matchId: string, error: Error) => void;
  
  // Clear loading state without setting error (for aborted requests)
  clearLoading: (matchId: string) => void;
  
  // Check if a prediction is already cached or loading
  has: (matchId: string) => boolean;
  
  // Check if a prediction request is currently in-flight
  isLoading: (matchId: string) => boolean;
  
  // Clear all cached predictions (for refresh)
  clear: () => void;
}

const PredictionCacheContext = createContext<PredictionCacheContextType | undefined>(undefined);

export function PredictionCacheProvider({ children }: { children: ReactNode }) {
  const [, forceUpdate] = useState({});
  const cacheRef = useRef<Map<string, PredictionState>>(new Map());
  const inFlightRef = useRef<Set<string>>(new Set());

  // Stable callbacks that read from ref instead of state
  // This prevents infinite loops while keeping current values
  const getPrediction = useCallback((matchId: string): PredictionState | undefined => {
    return cacheRef.current.get(matchId);
  }, []);

  const setPrediction = useCallback((matchId: string, prediction: MatchPredictionResponse) => {
    inFlightRef.current.delete(matchId); // Clear in-flight tracking
    cacheRef.current.set(matchId, {
      prediction,
      loading: false,
      error: null,
    });
    forceUpdate({}); // Trigger re-render for components that read from cache
  }, []);

  const setLoading = useCallback((matchId: string) => {
    // If already loading, don't update (prevents duplicate simultaneous requests)
    if (inFlightRef.current.has(matchId)) {
      return;
    }
    inFlightRef.current.add(matchId);
    
    cacheRef.current.set(matchId, {
      prediction: null,
      loading: true,
      error: null,
    });
    forceUpdate({}); // Trigger re-render
  }, []);

  const setError = useCallback((matchId: string, error: Error) => {
    inFlightRef.current.delete(matchId); // Clear in-flight tracking
    cacheRef.current.set(matchId, {
      prediction: null,
      loading: false,
      error,
    });
    forceUpdate({}); // Trigger re-render
  }, []);

  const has = useCallback((matchId: string): boolean => {
    return cacheRef.current.has(matchId);
  }, []);

  const isLoading = useCallback((matchId: string): boolean => {
    return inFlightRef.current.has(matchId);
  }, []);

  // Clear loading state without setting an error
  const clearLoading = useCallback((matchId: string) => {
    inFlightRef.current.delete(matchId); // Clear in-flight tracking
    cacheRef.current.delete(matchId); // Remove from cache entirely
    forceUpdate({}); // Trigger re-render
  }, []);

  const clear = useCallback(() => {
    cacheRef.current.clear();
    inFlightRef.current.clear();
    forceUpdate({}); // Trigger re-render
  }, []);

  return (
    <PredictionCacheContext.Provider
      value={{
        getPrediction,
        setPrediction,
        setLoading,
        setError,
        clearLoading,
        has,
        isLoading,
        clear,
      }}
    >
      {children}
    </PredictionCacheContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components -- hook is co-located with its provider
export function usePredictionCache() {
  const context = useContext(PredictionCacheContext);
  if (!context) {
    throw new Error('usePredictionCache must be used within PredictionCacheProvider');
  }
  return context;
}
