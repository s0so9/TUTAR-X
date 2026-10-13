import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Volume2 } from 'lucide-react';
import { getLiveMatches } from '../api/client';
import type { LiveMatchesResponse, MatchStatus } from '../api/types';
import { formatMatchStatus } from '../utils/formatters';
import FeedLiveMatches from '../components/live/FeedLiveMatches';
import { MatchKey, MatchLine, formatLiveMinute, matchLineTone } from '../components/matches';
import AudioSettings from '../components/AudioSettings';
import { playGoal } from '../services/audioService';
import './Live.css';

/** Display name for the live provider key the backend sends (e.g. "fotmob"). */
function formatProviderName(provider: string | null | undefined): string | null {
  if (!provider) return null;
  const key = provider.trim().toLowerCase();
  if (key === 'fotmob') return 'FotMob';
  return provider.trim();
}

/**
 * Canlı — live list. Every row opens the regular match page (/matches/:id),
 * which already follows a live match (score, minute and live statistics).
 */
export function Live() {
  const [matches, setMatches] = useState<LiveMatchesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAudioSettings, setShowAudioSettings] = useState(false);
  // Last seen goal total per match; the goal sound plays when a real total rises between polls.
  const goalTotalsRef = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    let mounted = true;

    async function fetchLiveMatches() {
      try {
        setLoading(true);
        setError(null);
        const data = await getLiveMatches();
        if (!mounted) return;

        let scored = false;
        const seen = goalTotalsRef.current;
        for (const m of data.matches) {
          if (m.home_score === null || m.away_score === null) continue;
          const total = m.home_score + m.away_score;
          const previous = seen.get(m.match_id);
          // First observation only sets the baseline.
          if (previous !== undefined && total > previous) scored = true;
          seen.set(m.match_id, total);
        }
        if (scored) playGoal();

        setMatches(data);
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : 'Canlı maçlar yüklenirken bir hata oluştu');
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    fetchLiveMatches();

    // Poll every 30 seconds while the app is visible
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') {
        fetchLiveMatches();
      }
    }, 30000);

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && mounted) {
        fetchLiveMatches();
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      mounted = false;
      clearInterval(interval);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  if (loading && !matches) {
    return (
      <div className="live-page">
        <div className="live-page__header">
          <h1 className="live-page__title">Canlı maçlar</h1>
        </div>
        <div className="live-page__loading">Yükleniyor...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="live-page">
        <div className="live-page__header">
          <h1 className="live-page__title">Canlı maçlar</h1>
        </div>
        <div className="live-page__error">
          <p>{error}</p>
          <button
            type="button"
            className="live-page__back-btn"
            onClick={() => window.location.reload()}
          >
            Tekrar dene
          </button>
        </div>
      </div>
    );
  }

  if (!matches || matches.matches.length === 0) {
    // Live providers returned nothing: fall back to LIVE matches in the regular match feed.
    return (
      <div className="live-page">
        <div className="live-page__header">
          <h1 className="live-page__title">Canlı maçlar</h1>
        </div>
        <FeedLiveMatches />
      </div>
    );
  }

  const provider = formatProviderName(matches.provider_used);

  return (
    <div className="live-page">
      <div className="live-page__header">
        <div className="live-page__title-section">
          <h1 className="live-page__title">Canlı maçlar</h1>
          <button
            type="button"
            className="live-page__audio-btn"
            onClick={() => setShowAudioSettings(true)}
            title="Ses ayarları"
            aria-label="Ses ayarları"
          >
            <Volume2 size={18} strokeWidth={1.5} aria-hidden="true" />
          </button>
        </div>
        <p className="live-page__subtitle">
          {matches.matches.length} maç · canlı veri akışında izlenenler
          {provider ? ` · Kaynak: ${provider}` : ' · Kaynak bilgisi yok'}
        </p>
        <p className="live-page__scope">
          Bu liste yalnızca canlı veri akışının izlediği maçları içerir.{' '}
          <Link to="/matches?status=live" className="live-page__scope-link">
            Tüm canlı maçlar Maç Merkezi'nde
          </Link>
        </p>
      </div>

      <ul className="tx-league-group__list live-page__list">
        {matches.matches.map((match) => {
          // The live feed also sends HALF_TIME, which is not in MatchStatus:
          // show it as a live match with its score and a "Devre arası" note.
          const halfTime = (match.status as string) === 'HALF_TIME';
          const status: MatchStatus = halfTime ? 'LIVE' : match.status;
          const statusText = halfTime ? 'Devre arası' : formatMatchStatus(match.status);
          const flags = [
            match.data_quality_flags.has_xg ? 'xG' : null,
            match.data_quality_flags.has_events ? 'Olaylar' : null,
            match.data_quality_flags.has_shots ? 'Şutlar' : null,
          ].filter((flag): flag is string => flag !== null);
          const minuteText = formatLiveMinute(match.minute, match.added_time);
          return (
            <MatchLine
              key={match.match_id}
              to={`/matches/${match.match_id}`}
              ariaLabel={`${match.home_team} - ${match.away_team}, skor ${match.home_score} - ${match.away_score}, ${statusText}${minuteText && !halfTime ? `, dakika ${minuteText}` : ''}. Maç sayfasına git`}
              home={match.home_team}
              away={match.away_team}
              tone={matchLineTone(status)}
              centre={
                <MatchKey
                  status={status}
                  noteOverride={halfTime ? 'Devre arası' : null}
                  kickoff={null}
                  homeScore={match.home_score}
                  awayScore={match.away_score}
                  minute={match.minute}
                  addedTime={match.added_time}
                />
              }
              aside={
                <span className="live-page__flags">
                  {flags.length > 0 ? flags.join(' · ') : 'Ek veri yok'}
                </span>
              }
            />
          );
        })}
      </ul>

      {matches.data_quality.matches_with_xg > 0 && (
        <p className="live-page__provider-status">
          xG verisi olan maç: {matches.data_quality.matches_with_xg}
        </p>
      )}

      <AudioSettings
        isOpen={showAudioSettings}
        onClose={() => setShowAudioSettings(false)}
      />
    </div>
  );
}
