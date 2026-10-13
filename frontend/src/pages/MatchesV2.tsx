/**
 * TUTAR X Match Center (/matches)
 *
 * League-grouped list of real matches for a selected day.
 * URL state: ?date=YYYY-MM-DD&league=<competition_id>&status=<all|live|scheduled|finished>&q=<team>
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { CalendarX, Search, SearchX } from 'lucide-react';
import { getCompetitions, getMatches, formatDateForAPI } from '../api/client';
import type { CompetitionResponse, MatchResponse, MatchStatus } from '../api/types';
import {
  DateStrip,
  LeagueGroup,
  MatchListSkeleton,
  probabilitiesFromPrediction,
  toMatchRowData,
} from '../components/matches';
import type { MatchRowData } from '../components/matches';
import { EmptyState } from '../components/ui';
import { useFavorites } from '../hooks/useFavorites';
import { usePredictionCache } from '../contexts/PredictionCacheContext';
import { getCompetitionPriorityRank } from '../utils/popularCompetitions';
import { normalizeSearchText } from '../utils/searchNormalizer';
import './MatchesV2.css';

type StatusFilter = 'all' | 'live' | 'scheduled' | 'finished';

const STATUS_FILTERS: { value: StatusFilter; label: string; statuses: MatchStatus[] | null }[] = [
  { value: 'all', label: 'Tümü', statuses: null },
  { value: 'live', label: 'Canlı', statuses: ['LIVE'] },
  { value: 'scheduled', label: 'Yaklaşan', statuses: ['SCHEDULED'] },
  { value: 'finished', label: 'Biten', statuses: ['FINISHED'] },
];

const MATCH_FETCH_LIMIT = 1000;
const DEFAULT_EXPANDED_GROUPS = 8;

interface MatchGroup {
  key: string;
  competitionId: string;
  name: string;
  country?: string;
  rank: number;
  matches: MatchRowData[];
}

function isValidDateParam(value: string | null): value is string {
  return !!value && /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function isStatusFilter(value: string | null): value is StatusFilter {
  return value === 'all' || value === 'live' || value === 'scheduled' || value === 'finished';
}

export function MatchesV2() {
  const [searchParams, setSearchParams] = useSearchParams();
  const dateParam = searchParams.get('date');
  const selectedDate = isValidDateParam(dateParam) ? dateParam : formatDateForAPI(new Date());
  const leagueFilter = searchParams.get('league') ?? '';
  const statusParam = searchParams.get('status');
  const statusFilter: StatusFilter = isStatusFilter(statusParam) ? statusParam : 'all';
  const query = searchParams.get('q') ?? '';

  const [competitions, setCompetitions] = useState<CompetitionResponse[]>([]);
  const [matches, setMatches] = useState<MatchResponse[]>([]);
  const [isDevelopmentData, setIsDevelopmentData] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const { isFavorite, toggleFavorite } = useFavorites();
  // Predictions already loaded elsewhere (dashboard, match detail) add the
  // model 1·X·2 column; this page never requests predictions itself.
  const { getPrediction } = usePredictionCache();

  const updateParam = useCallback(
    (key: string, value: string | null) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (value === null || value === '') {
            next.delete(key);
          } else {
            next.set(key, value);
          }
          return next;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  // Competitions: loaded once, used for country subtitles only.
  useEffect(() => {
    let isMounted = true;
    getCompetitions()
      .then((response) => {
        if (isMounted) setCompetitions(response.competitions);
      })
      .catch((err) => {
        // Non-critical: groups fall back to the competition name on each match.
        console.warn('[MatchesV2] Competitions could not be loaded:', err);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  // Matches for the selected day.
  useEffect(() => {
    let isMounted = true;
    const abortController = new AbortController();

    async function loadMatches() {
      try {
        setLoading(true);
        setError(null);
        const response = await getMatches(
          { from_date: selectedDate, to_date: selectedDate, limit: MATCH_FETCH_LIMIT },
          abortController.signal
        );
        if (!isMounted) return;
        setMatches(response.matches);
        setIsDevelopmentData(response.is_development_data);
      } catch (err) {
        if (!isMounted) return;
        if (err instanceof DOMException && err.name === 'AbortError') return;
        setError(err instanceof Error ? err.message : 'Maçlar yüklenirken bir hata oluştu');
        setMatches([]);
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    loadMatches();

    return () => {
      isMounted = false;
      abortController.abort();
    };
  }, [selectedDate, reloadToken]);

  const competitionsById = useMemo(() => {
    const map = new Map<string, CompetitionResponse>();
    competitions.forEach((competition) => map.set(competition.id, competition));
    return map;
  }, [competitions]);

  // All groups for the day (before filters) - also feeds the league <select>.
  const allGroups = useMemo<MatchGroup[]>(() => {
    const grouped = new Map<string, MatchGroup>();

    matches.forEach((match) => {
      const competition = competitionsById.get(match.competition_id);
      const name = match.competition_name || competition?.name || 'Lig bilgisi yok';
      const key = `${match.competition_id}|${name}`;

      let group = grouped.get(key);
      if (!group) {
        group = {
          key,
          competitionId: match.competition_id,
          name,
          country: competition?.country ?? undefined,
          rank: getCompetitionPriorityRank(name, match.competition_id),
          matches: [],
        };
        grouped.set(key, group);
      }
      group.matches.push(toMatchRowData(match, name));
    });

    return Array.from(grouped.values()).sort(
      (a, b) =>
        a.rank - b.rank ||
        b.matches.length - a.matches.length ||
        a.name.localeCompare(b.name, 'tr')
    );
  }, [matches, competitionsById]);

  const leagueOptions = useMemo(() => {
    const options = new Map<string, { id: string; label: string; sampleTeam?: string; count: number }>();
    allGroups.forEach((group) => {
      const existing = options.get(group.competitionId);
      if (existing) {
        existing.count += group.matches.length;
      } else {
        options.set(group.competitionId, {
          id: group.competitionId,
          label: group.country ? `${group.name} (${group.country})` : group.name,
          sampleTeam: group.matches[0]?.homeTeam.name,
          count: group.matches.length,
        });
      }
    });

    // Many countries share league names ("Premier League", "Championship") and the
    // backend sends no country, so same-named options get a sample team as a hint.
    const labelCounts = new Map<string, number>();
    options.forEach((option) => labelCounts.set(option.label, (labelCounts.get(option.label) ?? 0) + 1));

    return Array.from(options.values()).map(({ sampleTeam, ...option }) => ({
      ...option,
      label:
        (labelCounts.get(option.label) ?? 0) > 1 && sampleTeam
          ? `${option.label} (ör. ${sampleTeam})`
          : option.label,
    }));
  }, [allGroups]);

  const visibleGroups = useMemo(() => {
    const statuses = STATUS_FILTERS.find((f) => f.value === statusFilter)?.statuses ?? null;
    const normalizedQuery = normalizeSearchText(query);

    return allGroups
      .filter((group) => !leagueFilter || group.competitionId === leagueFilter)
      .map((group) => ({
        ...group,
        matches: group.matches.filter((match) => {
          if (statuses && !statuses.includes(match.status)) return false;
          if (normalizedQuery) {
            const haystack = normalizeSearchText(
              `${match.homeTeam.name} ${match.awayTeam.name} ${group.name}`
            );
            if (!haystack.includes(normalizedQuery)) return false;
          }
          return true;
        }),
      }))
      .filter((group) => group.matches.length > 0);
  }, [allGroups, leagueFilter, statusFilter, query]);

  // Read from the cache on every render: the cache context re-renders this page
  // when a prediction arrives, while getPrediction itself is a stable callback.
  const renderedGroups = visibleGroups.map((group) => ({
    ...group,
    matches: group.matches.map((match) => ({
      ...match,
      probabilities: probabilitiesFromPrediction(getPrediction(match.id)?.prediction),
    })),
  }));
  const showProbabilities = renderedGroups.some((group) =>
    group.matches.some((match) => !!match.probabilities)
  );

  const totalMatches = matches.length;
  const liveMatches = matches.filter((m) => m.status === 'LIVE').length;
  const visibleMatchCount = visibleGroups.reduce((sum, group) => sum + group.matches.length, 0);
  const hasActiveFilters = !!leagueFilter || statusFilter !== 'all' || !!query;

  const clearFilters = () => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete('league');
        next.delete('status');
        next.delete('q');
        return next;
      },
      { replace: true }
    );
  };

  return (
    <div className="tx-matches">
      <header className="tx-matches__header">
        <h1 className="tx-matches__title">Maç Merkezi</h1>
        <p className="tx-matches__counts" aria-live="polite">
          {loading ? (
            <span>Yükleniyor</span>
          ) : (
            <>
              <span>{totalMatches} maç</span>
              <span>{leagueOptions.length} lig</span>
              {liveMatches > 0 && <span className="tx-matches__counts-live">{liveMatches} canlı</span>}
            </>
          )}
        </p>
        {isDevelopmentData && (
          <span className="tx-matches__dev-badge">Geliştirme verisi (gerçek maç verisi değil)</span>
        )}
      </header>

      <div className="tx-matches__date">
        <DateStrip selectedDate={selectedDate} onDateChange={(date) => updateParam('date', date)} />
      </div>

      <div className="tx-matches__filters">
        <label className="tx-matches__field tx-matches__field--league">
          <span className="tx-matches__field-label">Lig</span>
          <select
            className="tx-matches__select"
            value={leagueFilter}
            onChange={(event) => updateParam('league', event.target.value || null)}
            disabled={loading || leagueOptions.length === 0}
          >
            <option value="">Tüm ligler</option>
            {leagueOptions.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label} · {option.count} maç
              </option>
            ))}
          </select>
        </label>

        <label className="tx-matches__field tx-matches__field--search">
          <span className="tx-matches__field-label">Takım ara</span>
          <span className="tx-matches__search">
            <Search className="tx-matches__search-icon" size={16} strokeWidth={1.5} aria-hidden="true" />
            <input
              type="search"
              className="tx-matches__input"
              placeholder="ör. Galatasaray"
              value={query}
              onChange={(event) => updateParam('q', event.target.value || null)}
            />
          </span>
        </label>

        <div className="tx-matches__field">
          <span className="tx-matches__field-label" id="tx-matches-status-label">
            Durum
          </span>
          <div className="tx-matches__segments" role="group" aria-labelledby="tx-matches-status-label">
            {STATUS_FILTERS.map((filter) => (
              <button
                key={filter.value}
                type="button"
                className={`tx-matches__segment${statusFilter === filter.value ? ' tx-matches__segment--active' : ''}`}
                aria-pressed={statusFilter === filter.value}
                onClick={() => updateParam('status', filter.value === 'all' ? null : filter.value)}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="tx-matches__content">
        {loading ? (
          <MatchListSkeleton rows={8} label="Maçlar yükleniyor" />
        ) : error ? (
          <div className="tx-matches__error" role="alert">
            <p className="tx-matches__error-message">Maçlar yüklenemedi: {error}</p>
            <p className="tx-matches__error-hint">Backend sunucusunun çalıştığından emin olun.</p>
            <button
              type="button"
              className="retry-button"
              onClick={() => setReloadToken((token) => token + 1)}
            >
              Tekrar dene
            </button>
          </div>
        ) : totalMatches === 0 ? (
          <EmptyState
            icon={<CalendarX size={18} strokeWidth={1.5} />}
            title="Maç bulunamadı"
            description="Seçilen tarih için kayıtlı maç bulunmuyor. Başka bir tarih seçin."
            action={
              selectedDate !== formatDateForAPI(new Date())
                ? { label: 'Bugüne dön', onClick: () => updateParam('date', null) }
                : undefined
            }
          />
        ) : renderedGroups.length === 0 ? (
          <EmptyState
            icon={<SearchX size={18} strokeWidth={1.5} />}
            title="Filtreyle eşleşen maç yok"
            description="Lig, durum veya arama filtresini değiştirin."
            action={hasActiveFilters ? { label: 'Filtreleri temizle', onClick: clearFilters } : undefined}
          />
        ) : (
          <>
            {hasActiveFilters && (
              <p className="tx-matches__result-count" aria-live="polite">
                <span>{visibleMatchCount} maç gösteriliyor</span>
                <button type="button" className="tx-matches__clear" onClick={clearFilters}>
                  Filtreleri temizle
                </button>
              </p>
            )}
            <div className="tx-matches__groups">
              {renderedGroups.map((group, index) => (
                <LeagueGroup
                  key={`${selectedDate}-${group.key}`}
                  leagueName={group.name}
                  subtitle={group.country}
                  matches={group.matches}
                  defaultExpanded={
                    hasActiveFilters ||
                    index < DEFAULT_EXPANDED_GROUPS ||
                    group.rank !== Number.MAX_SAFE_INTEGER
                  }
                  isFavorite={isFavorite}
                  onToggleFavorite={toggleFavorite}
                  showProbabilities={showProbabilities}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
