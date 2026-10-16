import { Link } from 'react-router-dom';
import { useFavorites } from '../contexts/FavoritesContext';
import { formatMatchDateTime, formatMatchStatus } from '../utils/formatters';
import type { MatchStatus } from '../api/types';
import './pages.css';
import './Matches.css';

export function Favorites() {
  const { favorites, removeFromFavorites, clearFavorites } = useFavorites();

  if (favorites.length === 0) {
    return (
      <div className="page-container">
        <div className="page-header">
          <h1>Favori Maçlar</h1>
          <p className="page-subtitle">Favorilere eklediğiniz maçlar burada görüntülenir</p>
        </div>
        
        <div className="empty-state">
          <div className="empty-icon">⭐</div>
          <p className="empty-title">Henüz favori maç yok</p>
          <p className="empty-description">
            Maç kartlarındaki yıldız simgesine tıklayarak favori maçlarınızı ekleyebilirsiniz.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>Favori Maçlar</h1>
        <p className="page-subtitle">
          {favorites.length} favori maç
          {favorites.length > 1 && (
            <button 
              onClick={clearFavorites}
              className="clear-favorites-btn"
              style={{
                marginLeft: '1rem',
                padding: '0.25rem 0.75rem',
                fontSize: '0.75rem',
                background: 'transparent',
                color: '#666',
                border: '1px solid #ccc',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              Tümünü Temizle
            </button>
          )}
        </p>
      </div>

      <div className="matches-list">
        {favorites.map((favorite) => {
          const dateTime = formatMatchDateTime(favorite.scheduledAt);
          
          return (
            <div key={favorite.matchId} className="favorite-match-card">
              <Link
                to={`/matches/${favorite.matchId}`}
                className="match-card"
              >
                <div className="match-card__header">
                  <div className="match-card__competition">
                    {favorite.competition}
                  </div>
                  <span className={`match-status match-status--${favorite.status}`}>
                    {formatMatchStatus(favorite.status as MatchStatus)}
                  </span>
                </div>

                <div className="match-card__body">
                  <div className="match-card__datetime">
                    <div className="match-date">{dateTime.date}</div>
                    <div className="match-time">{dateTime.time}</div>
                  </div>

                  <div className="match-card__teams">
                    <div className="team team--home">
                      <div className="team-logo-container">
                        <img 
                          src={`/team-logos/${favorite.homeTeam?.toLowerCase().replace(/\s+/g, '-')}.png`}
                          alt={favorite.homeTeam || 'Home team'}
                          className="team-logo"
                          onError={(e) => {
                            const target = e.target as HTMLImageElement;
                            target.style.display = 'none';
                            const fallback = target.nextElementSibling as HTMLDivElement;
                            if (fallback) fallback.style.display = 'flex';
                          }}
                        />
                        <div className="team-logo-fallback" style={{ display: 'none' }}>
                          {favorite.homeTeam ? favorite.homeTeam.charAt(0).toUpperCase() : 'H'}
                        </div>
                      </div>
                      <span className="team-name">{favorite.homeTeam}</span>
                    </div>

                    <div className="match-vs">
                      <span className="vs-text">vs</span>
                    </div>

                    <div className="team team--away">
                      <div className="team-logo-container">
                        <img 
                          src={`/team-logos/${favorite.awayTeam?.toLowerCase().replace(/\s+/g, '-')}.png`}
                          alt={favorite.awayTeam || 'Away team'}
                          className="team-logo"
                          onError={(e) => {
                            const target = e.target as HTMLImageElement;
                            target.style.display = 'none';
                            const fallback = target.nextElementSibling as HTMLDivElement;
                            if (fallback) fallback.style.display = 'flex';
                          }}
                        />
                        <div className="team-logo-fallback" style={{ display: 'none' }}>
                          {favorite.awayTeam ? favorite.awayTeam.charAt(0).toUpperCase() : 'A'}
                        </div>
                      </div>
                      <span className="team-name">{favorite.awayTeam}</span>
                    </div>
                  </div>
                </div>
              </Link>

              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  removeFromFavorites(favorite.matchId);
                }}
                className="remove-favorite-btn"
                title="Favorilerden kaldır"
                style={{
                  position: 'absolute',
                  top: '0.75rem',
                  right: '0.75rem',
                  background: 'transparent',
                  border: 'none',
                  color: '#ff6b6b',
                  fontSize: '1.25rem',
                  cursor: 'pointer',
                  padding: '0.25rem',
                  borderRadius: '4px'
                }}
              >
                ★
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}