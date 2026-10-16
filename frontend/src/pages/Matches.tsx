import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { getMatches, getCompetitions } from '../api';
import type { CompetitionResponse } from '../api/types';
import { normalizeMatches, type NormalizedMatch } from '../utils/matchNormalizer';
import { formatCompetitionName, formatMatchDateTime, formatMatchStatus } from '../utils/formatters';
import { LeagueSelector } from '../components/LeagueSelector';
import './Matches.css';

export function Matches() {
  const [competitions, setCompetitions] = useState<CompetitionResponse[]>([]);
  const [selectedCompetitionId, setSelectedCompetitionId] = useState<string | null>(null);
  const [matches, setMatches] = useState<NormalizedMatch[]>([]);
  const [competitionsLoading, setCompetitionsLoading] = useState(true);
  const [matchesLoading, setMatchesLoading] = useState(false);
  const [competitionsError, setCompetitionsError] = useState<string | null>(null);
  const [matchesError, setMatchesError] = useState<string | null>(null);
  const [isDevelopmentData, setIsDevelopmentData] = useState(false);

  // Effect 1: Load competitions on mount
  useEffect(() => {
    let isMounted = true;

    async function fetchCompetitions() {
      try {
        setCompetitionsLoading(true);
        setCompetitionsError(null);

        console.log('[DEBUG Matches.tsx] Fetching competitions...');
        const response = await getCompetitions();
        
        if (!isMounted) return;
        
        setCompetitions(response.competitions);
        console.log('[DEBUG Matches.tsx] Loaded', response.count, 'competitions');
      } catch (err) {
        if (!isMounted) return;
        console.error('[DEBUG Matches.tsx] Error loading competitions:', err);
        setCompetitionsError(err instanceof Error ? err.message : 'Ligler yüklenirken bir hata oluştu');
      } finally {
        if (isMounted) {
          setCompetitionsLoading(false);
        }
      }
    }

    fetchCompetitions();

    return () => {
      isMounted = false;
    };
  }, []);

  // Effect 2: Load matches when competition selected
  useEffect(() => {
    if (!selectedCompetitionId) {
      // No competition selected yet — clear matches
      setMatches([]);
      return;
    }

    let isMounted = true;
    const abortController = new AbortController();

    async function fetchMatches() {
      try {
        setMatchesLoading(true);
        setMatchesError(null);

        console.log('[DEBUG Matches.tsx] Fetching matches for competition:', selectedCompetitionId);
        
        // Use UTC date range for filtering
        const today = new Date();
        const fromDate = formatDateForAPI(today);
        const futureDate = new Date(today);
        futureDate.setDate(futureDate.getDate() + 7);
        const toDate = formatDateForAPI(futureDate);

        const response = await getMatches({
          competition_id: selectedCompetitionId as string,
          from_date: fromDate,
          to_date: toDate,
          status: 'SCHEDULED',
        });
        
        if (!isMounted) return;

        const normalizedMatches = normalizeMatches(response.matches);
        setMatches(normalizedMatches);
        setIsDevelopmentData(response.is_development_data);
        
        console.log('[DEBUG Matches.tsx] Loaded', normalizedMatches.length, 'matches');
      } catch (err) {
        if (!isMounted) return;
        console.error('[DEBUG Matches.tsx] Error loading matches:', err);
        setMatchesError(err instanceof Error ? err.message : 'Maçlar yüklenirken bir hata oluştu');
      } finally {
        if (isMounted) {
          setMatchesLoading(false);
        }
      }
    }

    fetchMatches();

    return () => {
      isMounted = false;
      abortController.abort();
    };
  }, [selectedCompetitionId]);

  // Helper function
  function formatDateForAPI(date: Date): string {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  if (competitionsLoading) {
    return (
      <div className="page-container">
        <div className="page-header">
          <h1>Maçlar</h1>
          <p className="page-subtitle">Yaklaşan maçlar ve tahminler</p>
        </div>
        <div className="loading-state">
          <div className="loading-spinner"></div>
          <p>Ligler yükleniyor...</p>
        </div>
      </div>
    );
  }

  if (competitionsError) {
    return (
      <div className="page-container">
        <div className="page-header">
          <h1>Maçlar</h1>
          <p className="page-subtitle">Yaklaşan maçlar ve tahminler</p>
        </div>
        <div className="error-state">
          <p className="error-message">{competitionsError}</p>
          <p className="error-hint">Backend sunucusunun çalıştığından emin olun.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>Maçlar</h1>
        <p className="page-subtitle">
          Yaklaşan maçlar ve tahminler
          {isDevelopmentData && (
            <span className="dev-badge">Geliştirme Verisi</span>
          )}
        </p>
      </div>

      <LeagueSelector
        competitions={competitions}
        selectedId={selectedCompetitionId}
        onChange={setSelectedCompetitionId}
        loading={false}
      />

      {!selectedCompetitionId && (
        <div className="empty-state">
          <div className="empty-icon">⚽</div>
          <p className="empty-title">Bir lig seçin</p>
          <p className="empty-description">
            Maçları görüntülemek için yukarıdan bir lig seçin.
          </p>
        </div>
      )}

      {selectedCompetitionId && matchesLoading && (
        <div className="loading-state">
          <div className="loading-spinner"></div>
          <p>Maçlar yükleniyor...</p>
        </div>
      )}

      {selectedCompetitionId && matchesError && (
        <div className="error-state">
          <p className="error-message">{matchesError}</p>
          <p className="error-hint">Lütfen tekrar deneyin veya başka bir lig seçin.</p>
        </div>
      )}

      {selectedCompetitionId && !matchesLoading && !matchesError && matches.length === 0 && (
        <div className="empty-state">
          <div className="empty-icon">⚽</div>
          <p className="empty-title">Bu ligde yaklaşan maç bulunamadı</p>
          <p className="empty-description">
            Seçilen ligde önümüzdeki 7 günde planlanmış maç bulunmamaktadır.
          </p>
        </div>
      )}

      {selectedCompetitionId && !matchesLoading && !matchesError && matches.length > 0 && (
        <div className="matches-list">
          {matches.map((match) => {
            const dateTime = formatMatchDateTime(match.scheduledAt);

            return (
              <Link
                key={match.id}
                to={`/matches/${match.id}`}
                className="match-card"
              >
                <div className="match-card__header">
                  <div className="match-card__competition">
                    {formatCompetitionName(match.competitionId)}
                    {match.round && ` - ${match.round}. Hafta`}
                  </div>
                  <span className={`match-status match-status--${match.status}`}>
                    {formatMatchStatus(match.status as import('../api/types').MatchStatus)}
                  </span>
                </div>

                <div className="match-card__body">
                  <div className="match-card__datetime">
                    <div className="match-date">{dateTime.date}</div>
                    <div className="match-time">{dateTime.time}</div>
                  </div>

                  <div className="match-card__teams">
                    <div className="team team--home">
                      <span className="team-name">{match.homeTeam.name}</span>
                      {match.homeTeam.logoUrl ? (
                        <img 
                          src={match.homeTeam.logoUrl} 
                          alt={match.homeTeam.name}
                          className="team-logo"
                          onError={(e) => {
                            e.currentTarget.style.display = 'none';
                          }}
                        />
                      ) : (
                        <div className="team-logo-placeholder">
                          {match.homeTeam.code || match.homeTeam.name.substring(0, 3).toUpperCase()}
                        </div>
                      )}
                    </div>

                    <div className="match-vs">
                      {/* CRITICAL: Scheduled matches must NEVER show scores */}
                      {(match.status === 'FINISHED' || match.status === 'LIVE') && 
                       match.homeScore !== null && match.awayScore !== null ? (
                        <div className="match-score">
                          {match.homeScore} - {match.awayScore}
                        </div>
                      ) : (
                        <span className="vs-text">vs</span>
                      )}
                    </div>

                    <div className="team team--away">
                      {match.awayTeam.logoUrl ? (
                        <img 
                          src={match.awayTeam.logoUrl} 
                          alt={match.awayTeam.name}
                          className="team-logo"
                          onError={(e) => {
                            e.currentTarget.style.display = 'none';
                          }}
                        />
                      ) : (
                        <div className="team-logo-placeholder">
                          {match.awayTeam.code || match.awayTeam.name.substring(0, 3).toUpperCase()}
                        </div>
                      )}
                      <span className="team-name">{match.awayTeam.name}</span>
                    </div>
                  </div>

                  {match.status === 'SCHEDULED' && (
                    <div className="match-card__indicator">
                      <span className="prediction-indicator">
                        📊 Tahmin Mevcut
                      </span>
                    </div>
                  )}
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
