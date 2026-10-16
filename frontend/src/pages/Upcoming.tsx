import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { getMatches, getCompetitions } from '../api/client';
import type { CompetitionResponse } from '../api/types';
import { normalizeMatches, type NormalizedMatch } from '../utils/matchNormalizer';
import { formatCompetitionName, formatMatchDateTime, formatMatchStatus } from '../utils/formatters';
import { normalizeCompetitionName } from '../utils/popularCompetitions';
import { FavoriteButton } from '../components/FavoriteButton';
import './Matches.css';

export function Upcoming() {
  const [competitions, setCompetitions] = useState<CompetitionResponse[]>([]);
  const [matches, setMatches] = useState<NormalizedMatch[]>([]);
  const [rawMatches, setRawMatches] = useState<import('../api/types').MatchResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDevelopmentData, setIsDevelopmentData] = useState(false);

  // Load all upcoming matches from all competitions
  useEffect(() => {
    let isMounted = true;
    const abortController = new AbortController();

    async function fetchUpcomingMatches() {
      try {
        setLoading(true);
        setError(null);

        // Fetch competitions first for display names (non-blocking)
        getCompetitions().then(competitionsResponse => {
          if (isMounted) {
            setCompetitions(competitionsResponse.competitions);
          }
        }).catch(err => {
          // Competition fetch failure should not block match display
          console.warn('Failed to fetch competitions:', err);
        });

        // Calculate UTC "now" for consistent filtering across requests
        const now = new Date();
        const scheduledAfterUTC = now.toISOString();

        // Use date range for next 7 days (matching UI text)
        const today = new Date();
        const fromDate = formatDateForAPI(today);
        const futureDate = new Date(today);
        futureDate.setDate(futureDate.getDate() + 7);  // Changed from 30 to 7
        const toDate = formatDateForAPI(futureDate);

        // Fetch upcoming matches with server-side datetime filter
        const matchesResponse = await getMatches({
          from_date: fromDate,
          to_date: toDate,
          status: 'SCHEDULED',
          scheduled_after: scheduledAfterUTC,  // Server-side filter
          limit: 300,
        }, abortController.signal);
        
        if (!isMounted) return;

        const normalizedMatches = normalizeMatches(matchesResponse.matches);
        setRawMatches(matchesResponse.matches);
        
        // Server already filtered by scheduled_after, no client-side time filter needed
        // Just sort by kick-off time (earliest first)
        normalizedMatches.sort((a, b) => 
          new Date(a.scheduledAt).getTime() - new Date(b.scheduledAt).getTime()
        );
        
        setMatches(normalizedMatches);
        setIsDevelopmentData(matchesResponse.is_development_data);
      } catch (err) {
        if (!isMounted) return;
        
        // Don't show error if request was aborted
        if (err instanceof DOMException && err.name === 'AbortError') {
          return;
        }
        if (err instanceof Error && err.name === 'AbortError') {
          return;
        }
        
        console.error('Error loading upcoming matches:', err);
        setError(err instanceof Error ? err.message : 'Yaklaşan maçlar yüklenirken bir hata oluştu');
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    fetchUpcomingMatches();

    return () => {
      isMounted = false;
      abortController.abort();
    };
  }, []);

  // Helper function
  function formatDateForAPI(date: Date): string {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  if (loading) {
    return (
      <div className="page-container">
        <div className="page-header">
          <h1>Yaklaşan Maçlar</h1>
          <p className="page-subtitle">Önümüzdeki 7 günün tüm maçları</p>
        </div>
        <div className="loading-state">
          <div className="loading-spinner"></div>
          <p>Yaklaşan maçlar yükleniyor...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-container">
        <div className="page-header">
          <h1>Yaklaşan Maçlar</h1>
          <p className="page-subtitle">Önümüzdeki 7 günün tüm maçları</p>
        </div>
        <div className="error-state">
          <p className="error-message">{error}</p>
          <p className="error-hint">Backend sunucusunun çalıştığından emin olun.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>Yaklaşan Maçlar</h1>
        <p className="page-subtitle">
          Önümüzdeki 7 günün tüm maçları
          {isDevelopmentData && (
            <span className="dev-badge">Geliştirme Verisi</span>
          )}
        </p>
      </div>

      {matches.length === 0 && (
        <div className="empty-state">
          <div className="empty-icon">⚽</div>
          <p className="empty-title">Yaklaşan maç bulunamadı</p>
          <p className="empty-description">
            Önümüzdeki 7 günde planlanmış maç bulunmamaktadır.
          </p>
        </div>
      )}

      {matches.length > 0 && (
        <div className="matches-list">
          {(() => {
            // Group matches by competition
            const matchesByCompetition = matches.reduce((groups, match) => {
              const competition = competitions.find(c => c.id === match.competitionId);
              let competitionName: string;
              
              // Priority 1: Use match.competition_name from provider if available
              // Priority 2: Use competition from competitions endpoint
              // Priority 3: Format competition_id
              if (match.competitionName) {
                const normalizedFromProvider = normalizeCompetitionName(match.competitionName);
                competitionName = normalizedFromProvider || match.competitionName;
              } else if (competition) {
                const normalizedName = normalizeCompetitionName(competition.name);
                competitionName = normalizedName || competition.name;
              } else if (/^\d+$/.test(match.competitionId)) {
                competitionName = 'Bilinmeyen lig';
              } else {
                competitionName = formatCompetitionName(match.competitionId);
              }
              
              if (!groups[competitionName]) {
                groups[competitionName] = [];
              }
              groups[competitionName].push(match);
              return groups;
            }, {} as Record<string, NormalizedMatch[]>);

            // Sort competitions by name and render grouped matches
            return Object.keys(matchesByCompetition)
              .sort((a, b) => a.localeCompare(b, 'tr'))
              .map(competitionName => (
                <div key={competitionName} className="competition-group">
                  <h3 className="competition-group__title">
                    {competitionName}
                    <span className="competition-group__count">
                      ({matchesByCompetition[competitionName].length} maç)
                    </span>
                  </h3>
                  
                  <div className="competition-group__matches">
                    {matchesByCompetition[competitionName].map((match) => {
                      const dateTime = formatMatchDateTime(match.scheduledAt);
                      // Find corresponding raw match for FavoriteButton
                      const rawMatch = rawMatches.find(r => r.id === match.id);

                      return (
                        <div key={match.id} className="match-card-container">
                          <Link
                            to={`/matches/${match.id}`}
                            className="match-card"
                          >
                            <div className="match-card__header">
                              <div className="match-card__competition">
                                {competitionName}
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
                                  <span className="vs-text">vs</span>
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

                              <div className="match-card__indicator">
                                {/* Only show prediction indicator if we know predictions are available */}
                                {/* For now, show "Match Details" for all matches */}
                                <span className="prediction-indicator">
                                  📊 Maç Detayları
                                </span>
                              </div>
                            </div>
                          </Link>

                          {/* Favorite Button - Outside of Link */}
                          {rawMatch && (
                            <FavoriteButton
                              match={rawMatch}
                              className="match-card-favorite"
                              style={{
                                position: 'absolute',
                                top: '0.75rem',
                                right: '0.75rem',
                                zIndex: 10,
                              }}
                            />
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ));
          })()}
        </div>
      )}
    </div>
  );
}