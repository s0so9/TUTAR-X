/**
 * FeedLiveMatches - fallback list for the Live page.
 *
 * Used when the live data providers return no matches. Shows the matches whose
 * status is LIVE in the regular match feed (/matches), grouped by league.
 * Scores and minutes are shown exactly as the feed sends them; when the feed
 * has no minute, the row shows the kickoff time with the "Canlı" badge.
 */

import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { getMatches, formatDateForAPI } from '../../api/client';
import type { MatchResponse } from '../../api/types';
import { LeagueGroup, toMatchRowData } from '../matches';
import type { MatchRowData } from '../matches';
import { useFavorites } from '../../hooks/useFavorites';
import { getCompetitionPriorityRank } from '../../utils/popularCompetitions';

const POLL_INTERVAL_MS = 60000;
const DAY_MS = 24 * 60 * 60 * 1000;

interface FeedGroup {
  key: string;
  name: string;
  rank: number;
  matches: MatchRowData[];
}

function isAbortError(err: unknown): boolean {
  return (
    (err instanceof DOMException && err.name === 'AbortError') ||
    (err instanceof Error && err.name === 'AbortError')
  );
}

export function FeedLiveMatches() {
  const [liveMatches, setLiveMatches] = useState<MatchResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { isFavorite, toggleFavorite } = useFavorites();

  useEffect(() => {
    let isMounted = true;
    let controller: AbortController | null = null;

    async function load() {
      controller?.abort();
      const current = new AbortController();
      controller = current;
      const now = new Date();
      try {
        // Yesterday..today: a match that kicked off before local midnight can still be live.
        const response = await getMatches(
          {
            from_date: formatDateForAPI(new Date(now.getTime() - DAY_MS)),
            to_date: formatDateForAPI(now),
            limit: 1000,
          },
          current.signal
        );
        if (!isMounted) return;
        // Filter client-side: the backend currently ignores the status filter.
        setLiveMatches(response.matches.filter((match) => match.status === 'LIVE'));
        setError(null);
      } catch (err) {
        if (!isMounted || isAbortError(err)) return;
        setError(err instanceof Error ? err.message : 'Maç listesi yüklenemedi');
      }
    }

    load();
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') load();
    }, POLL_INTERVAL_MS);

    return () => {
      isMounted = false;
      clearInterval(interval);
      controller?.abort();
    };
  }, []);

  const groups = useMemo<FeedGroup[]>(() => {
    const grouped = new Map<string, FeedGroup>();
    (liveMatches ?? []).forEach((match) => {
      const name = match.competition_name || 'Lig bilgisi yok';
      const key = `${match.competition_id}|${name}`;
      let group = grouped.get(key);
      if (!group) {
        group = { key, name, rank: getCompetitionPriorityRank(name, match.competition_id), matches: [] };
        grouped.set(key, group);
      }
      group.matches.push(toMatchRowData(match, name));
    });
    return Array.from(grouped.values()).sort(
      (a, b) => a.rank - b.rank || b.matches.length - a.matches.length || a.name.localeCompare(b.name, 'tr')
    );
  }, [liveMatches]);

  if (error && liveMatches === null) {
    return (
      <div className="live-page__feed" role="alert">
        <p className="live-page__feed-note">Canlı maç listesi yüklenemedi: {error}</p>
      </div>
    );
  }

  if (liveMatches === null) {
    return <div className="live-page__loading">Maç listesi kontrol ediliyor...</div>;
  }

  if (liveMatches.length === 0) {
    return (
      <div className="live-page__feed">
        <p className="live-page__subtitle">Şu anda canlı maç bulunmuyor</p>
        <Link to="/matches" className="live-page__feed-link">
          Bugünün maçlarına git
        </Link>
      </div>
    );
  }

  return (
    <section className="live-page__feed" aria-label="Maç listesindeki canlı maçlar">
      <p className="live-page__feed-note">
        Canlı veri sağlayıcısından şu anda veri gelmiyor. Aşağıdaki {liveMatches.length} canlı maç genel
        maç listesinden alınmıştır; saha görünümü ve anlık olaylar bu maçlar için mevcut değil.
        Dakika bilgisi gelmeyen maçlarda başlama saati gösterilir.
      </p>
      <div className="live-page__feed-groups">
        {groups.map((group) => (
          <LeagueGroup
            key={group.key}
            leagueName={group.name}
            matches={group.matches}
            defaultExpanded
            isFavorite={isFavorite}
            onToggleFavorite={toggleFavorite}
          />
        ))}
      </div>
    </section>
  );
}

export default FeedLiveMatches;
