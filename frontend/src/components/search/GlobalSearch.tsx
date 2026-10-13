import { useState, useRef, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { getMatches } from '../../api';
import { normalizeMatches, type NormalizedMatch } from '../../utils/matchNormalizer';
import { formatMatchDateTime } from '../../utils/formatters';
import { normalizeSearchText } from '../../utils/searchNormalizer';
import './GlobalSearch.css';

interface GlobalSearchProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
}

interface SearchResult extends NormalizedMatch {
  relevanceScore: number;
  matchReason: string;
}

const DEBOUNCE_MS = 300;
const MIN_SEARCH_LENGTH = 2;
const MAX_RESULTS = 10;

export function GlobalSearch({ isOpen, onOpenChange }: GlobalSearchProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);

  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const debounceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Search function with Turkish character normalization
  const performSearch = useCallback(async (term: string) => {
    if (term.length < MIN_SEARCH_LENGTH) {
      setResults([]);
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);

      // Get recent and upcoming matches from API
      const today = new Date();
      const pastDate = new Date(today);
      pastDate.setDate(pastDate.getDate() - 7);
      const futureDate = new Date(today);
      futureDate.setDate(futureDate.getDate() + 14);

      const formatDateForAPI = (date: Date): string => {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
      };

      const response = await getMatches({
        from_date: formatDateForAPI(pastDate),
        to_date: formatDateForAPI(futureDate),
        limit: 200 // Get more matches for better search results
      });

      const normalizedMatches = normalizeMatches(response.matches);

      // Normalize search term
      const normalizedTerm = normalizeSearchText(term);
      const searchWords = normalizedTerm.split(/\s+/).filter(word => word.length > 0);

      // Search and score matches
      const searchResults: SearchResult[] = [];

      for (const match of normalizedMatches) {
        let relevanceScore = 0;
        const matchReasons: string[] = [];

        // Normalize team names and competition name
        const homeTeamNorm = normalizeSearchText(match.homeTeam.name);
        const awayTeamNorm = normalizeSearchText(match.awayTeam.name);
        const competitionNorm = match.competitionName ? normalizeSearchText(match.competitionName) : '';

        // Check each search word
        for (const word of searchWords) {
          // Exact team name match (highest score)
          if (homeTeamNorm === word || awayTeamNorm === word) {
            relevanceScore += 100;
            matchReasons.push('Tam takım adı eşleşmesi');
          }
          // Team name contains search word
          else if (homeTeamNorm.includes(word)) {
            relevanceScore += 80;
            matchReasons.push(`Ev sahibi: ${match.homeTeam.name}`);
          }
          else if (awayTeamNorm.includes(word)) {
            relevanceScore += 80;
            matchReasons.push(`Deplasman: ${match.awayTeam.name}`);
          }
          // Competition name match
          else if (competitionNorm.includes(word)) {
            relevanceScore += 60;
            matchReasons.push(`Lig: ${match.competitionName || 'Bilinmeyen lig'}`);
          }
          // Short team codes (3 letters)
          else if (word.length >= 3) {
            const homeCodeNorm = normalizeSearchText(match.homeTeam.code || '');
            const awayCodeNorm = normalizeSearchText(match.awayTeam.code || '');

            if (homeCodeNorm.includes(word) || awayCodeNorm.includes(word)) {
              relevanceScore += 40;
              matchReasons.push('Takım kodu eşleşmesi');
            }
          }
        }

        // Special case: both team names mentioned (like "Real Madrid Barcelona")
        if (searchWords.length >= 2) {
          const hasHomeTeam = searchWords.some(word => homeTeamNorm.includes(word));
          const hasAwayTeam = searchWords.some(word => awayTeamNorm.includes(word));

          if (hasHomeTeam && hasAwayTeam) {
            relevanceScore += 150; // Very high relevance
            matchReasons.push('Her iki takım da eşleşti');
          }
        }

        // Boost score for recent/upcoming matches
        const matchDate = new Date(match.scheduledAt);
        const daysDiff = Math.abs((matchDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));

        if (daysDiff <= 1) relevanceScore += 20; // Today or yesterday
        else if (daysDiff <= 7) relevanceScore += 10; // This week

        // Add to results if relevant
        if (relevanceScore > 0) {
          searchResults.push({
            ...match,
            relevanceScore,
            matchReason: matchReasons.join(', ')
          });
        }
      }

      // Sort by relevance score and limit results
      const sortedResults = searchResults
        .sort((a, b) => b.relevanceScore - a.relevanceScore)
        .slice(0, MAX_RESULTS);

      setResults(sortedResults);
      setSelectedIndex(0);

    } catch (err) {
      console.error('Search error:', err);
      setError('Arama sırasında bir hata oluştu');
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Debounced search
  useEffect(() => {
    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
    }

    debounceTimeoutRef.current = setTimeout(() => {
      if (searchTerm.trim()) {
        performSearch(searchTerm.trim());
      } else {
        setResults([]);
        setLoading(false);
      }
    }, DEBOUNCE_MS);

    return () => {
      if (debounceTimeoutRef.current) {
        clearTimeout(debounceTimeoutRef.current);
      }
    };
  }, [searchTerm, performSearch]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  // Handle keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) return;

    switch (e.key) {
      case 'Escape':
        onOpenChange(false);
        setSearchTerm('');
        break;
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex(prev => Math.min(prev + 1, results.length - 1));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex(prev => Math.max(prev - 1, 0));
        break;
      case 'Enter':
        if (results[selectedIndex]) {
          onOpenChange(false);
          setSearchTerm('');
          // Navigate to match detail - handled by Link component
        }
        break;
    }
  };

  // Handle click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (resultsRef.current && !resultsRef.current.contains(event.target as Node)) {
        onOpenChange(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen, onOpenChange]);

  const handleResultClick = () => {
    onOpenChange(false);
    setSearchTerm('');
  };

  if (!isOpen) {
    return (
      <button
        className="global-search-trigger"
        onClick={() => onOpenChange(true)}
        aria-label="Maç ara"
        title="Maç ara (Ctrl+K)"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M21 21L16.514 16.506M19 10.5C19 15.194 15.194 19 10.5 19S2 15.194 2 10.5 5.806 2 10.5 2 19 5.806 19 10.5Z"
                stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        <span>Maç ara...</span>
        <kbd>Ctrl+K</kbd>
      </button>
    );
  }

  return (
    <div className="global-search" ref={resultsRef}>
      <div className="global-search-input-container">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className="search-icon">
          <path d="M21 21L16.514 16.506M19 10.5C19 15.194 15.194 19 10.5 19S2 15.194 2 10.5 5.806 2 10.5 2 19 5.806 19 10.5Z"
                stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>

        <input
          ref={inputRef}
          type="text"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Takım veya lig ara..."
          className="global-search-input"
          autoComplete="off"
        />

        {searchTerm && (
          <button
            onClick={() => {
              setSearchTerm('');
              setResults([]);
            }}
            className="search-clear"
            aria-label="Temizle"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          </button>
        )}
      </div>

      {/* Results */}
      {searchTerm.length >= MIN_SEARCH_LENGTH && (
        <div className="global-search-results">
          {loading && (
            <div className="search-loading">
              <div className="loading-spinner"></div>
              <span>Aranıyor...</span>
            </div>
          )}

          {error && !loading && (
            <div className="search-error">
              <span>{error}</span>
            </div>
          )}

          {!loading && !error && results.length === 0 && searchTerm.length >= MIN_SEARCH_LENGTH && (
            <div className="search-no-results">
              <span>"{searchTerm}" için sonuç bulunamadı</span>
            </div>
          )}

          {!loading && !error && results.length > 0 && (
            <div className="search-results-list">
              {results.map((match, index) => {
                const dateTime = formatMatchDateTime(match.scheduledAt);
                const isSelected = index === selectedIndex;

                return (
                  <Link
                    key={match.id}
                    to={`/matches/${match.id}`}
                    className={`search-result-item ${isSelected ? 'selected' : ''}`}
                    onClick={handleResultClick}
                    onMouseEnter={() => setSelectedIndex(index)}
                  >
                    <div className="result-teams">
                      <span className="result-home-team">{match.homeTeam.name}</span>
                      <span className="result-vs">vs</span>
                      <span className="result-away-team">{match.awayTeam.name}</span>
                    </div>

                    <div className="result-details">
                      <span className="result-competition">
                        {match.competitionName || 'Bilinmeyen lig'}
                      </span>
                      <span className="result-date">{dateTime.date} {dateTime.time}</span>
                      <span className={`result-status status-${match.status.toLowerCase()}`}>
                        {match.status === 'SCHEDULED' && 'Yaklaşan'}
                        {match.status === 'LIVE' && 'Canlı'}
                        {match.status === 'FINISHED' && 'Bitti'}
                        {match.status === 'POSTPONED' && 'Ertelendi'}
                        {match.status === 'CANCELLED' && 'İptal'}
                      </span>
                    </div>

                    <div className="result-score">
                      {match.status === 'LIVE' || match.status === 'FINISHED' ? (
                        match.homeScore !== null && match.awayScore !== null ? (
                          <span>{match.homeScore} - {match.awayScore}</span>
                        ) : (
                          <span>-</span>
                        )
                      ) : (
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                          <path d="M9 5L16 12L9 19" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                      )}
                    </div>
                  </Link>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}