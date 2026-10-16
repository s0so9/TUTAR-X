import { useState, useEffect } from 'react';
import { getMatches } from '../api/client';
import type { MatchResponse } from '../api/types';
import { normalizeMatch } from '../utils/matchNormalizer';
import { FavoriteButton } from '../components/FavoriteButton';
import './pages.css';

export function Completed() {
  const [matches, setMatches] = useState<MatchResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchCompletedMatches() {
      try {
        setLoading(true);
        setError(null);

        // Fetch completed matches with date filtering to reduce timeout risk
        const today = new Date();
        const pastDate = new Date(today);
        pastDate.setDate(pastDate.getDate() - 30); // Last 30 days only
        
        const formatDateForAPI = (date: Date): string => {
          const year = date.getFullYear();
          const month = String(date.getMonth() + 1).padStart(2, '0');
          const day = String(date.getDate()).padStart(2, '0');
          return `${year}-${month}-${day}`;
        };

        const response = await getMatches({
          status: 'FINISHED',
          from_date: formatDateForAPI(pastDate),
          to_date: formatDateForAPI(today),
        });
        
        // Filter for completed matches with strict status checking
        const completedMatches = response.matches.filter(match => {
          // Primary completed status
          if (match.status === 'FINISHED') return true;
          
          // Exclude postponed, cancelled, suspended - these are not "completed"
          if (match.status === 'POSTPONED' || match.status === 'CANCELLED' || match.status === 'SUSPENDED') {
            return false;
          }
          
          return false;
        });

        setMatches(completedMatches);
      } catch (err) {
        console.error('Error fetching completed matches:', err);
        setError(err instanceof Error ? err.message : 'Tamamlanan maçlar yüklenirken hata oluştu');
      } finally {
        setLoading(false);
      }
    }

    fetchCompletedMatches();
  }, []);

  const formatDateTime = (dateString: string) => {
    const date = new Date(dateString);
    // Convert to Istanbul timezone
    const istanbulTime = new Date(date.toLocaleString("en-US", {timeZone: "Europe/Istanbul"}));
    
    return istanbulTime.toLocaleDateString('tr-TR', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  if (loading) {
    return (
      <div className="page-container">
        <div className="page-header">
          <h1 className="page-title">Tamamlanan Maçlar</h1>
          <p className="page-subtitle">Bitmiş maçlar ve sonuçları</p>
        </div>
        <div className="loading-state">
          <div className="loading-spinner"></div>
          <p>Tamamlanan maçlar yükleniyor...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-container">
        <div className="page-header">
          <h1 className="page-title">Tamamlanan Maçlar</h1>
          <p className="page-subtitle">Bitmiş maçlar ve sonuçları</p>
        </div>
        <div className="error-state">
          <p className="error-message">❌ {error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Tamamlanan Maçlar</h1>
        <p className="page-subtitle">Bitmiş maçlar ve sonuçları ({matches.length} maç)</p>
      </div>

      {matches.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">⚽</div>
          <p className="empty-title">Tamamlanan maç bulunamadı</p>
          <p className="empty-description">
            Henüz tamamlanan maç bulunmamaktadır. Maçlar bittiğinde burada görüntülenecektir.
          </p>
        </div>
      ) : (
        <div className="matches-grid">
          {matches.map(match => {
            const normalizedMatch = normalizeMatch(match);
            const matchTime = formatDateTime(match.scheduled_at);
            
            return (
              <div key={match.id} className="match-card-container">
                <div 
                  className="match-card match-card--completed"
                  onClick={() => window.location.href = `/matches/${match.id}`}
                >
                  <div className="match-card-header">
                    <div className="competition-info">
                      <span className="competition-name">
                        {/^\d+$/.test(normalizedMatch.competitionId) ? 'Bilinmeyen lig' : normalizedMatch.competitionId}
                      </span>
                      {match.round && <span className="round-info">{match.round}. Hafta</span>}
                    </div>
                    <div className="match-time">{matchTime}</div>
                  </div>
                  
                  <div className="match-teams">
                    <div className="team home-team">
                      <div className="team-logo-container">
                        {normalizedMatch.homeTeam.logoUrl ? (
                          <img 
                            src={normalizedMatch.homeTeam.logoUrl}
                            alt={normalizedMatch.homeTeam.name || 'Home team'}
                            className="team-logo"
                            onError={(e) => {
                              e.currentTarget.style.display = 'none';
                            }}
                          />
                        ) : (
                          <div className="team-logo-placeholder">
                            {normalizedMatch.homeTeam.code || normalizedMatch.homeTeam.name.substring(0, 3).toUpperCase()}
                          </div>
                        )}
                      </div>
                      <span className="team-name">{normalizedMatch.homeTeam.name}</span>
                      {match.home_score !== undefined && (
                        <span className="team-score">{match.home_score}</span>
                      )}
                    </div>
                    
                    <div className="match-vs">
                      <span className="vs-text">
                        {match.home_score !== undefined && match.away_score !== undefined
                          ? `${match.home_score} - ${match.away_score}`
                          : 'vs'
                        }
                      </span>
                      <span className="match-status">Tamamlandı</span>
                    </div>
                    
                    <div className="team away-team">
                      <div className="team-logo-container">
                        {normalizedMatch.awayTeam.logoUrl ? (
                          <img 
                            src={normalizedMatch.awayTeam.logoUrl}
                            alt={normalizedMatch.awayTeam.name || 'Away team'}
                            className="team-logo"
                            onError={(e) => {
                              e.currentTarget.style.display = 'none';
                            }}
                          />
                        ) : (
                          <div className="team-logo-placeholder">
                            {normalizedMatch.awayTeam.code || normalizedMatch.awayTeam.name.substring(0, 3).toUpperCase()}
                          </div>
                        )}
                      </div>
                      <span className="team-name">{normalizedMatch.awayTeam.name}</span>
                      {match.away_score !== undefined && (
                        <span className="team-score">{match.away_score}</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Favorite Button */}
                <FavoriteButton
                  match={match}
                  className="match-card-favorite"
                  style={{
                    position: 'absolute',
                    top: '0.75rem',
                    right: '0.75rem',
                    zIndex: 10,
                  }}
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}