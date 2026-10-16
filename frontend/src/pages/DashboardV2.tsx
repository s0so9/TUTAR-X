/**
 * TUTAR X - Bugün (dashboard)
 *
 * Today's model picks as a dense rail-grammar ledger (match line, pick market,
 * model %, odds with provenance, value assessment, confidence), followed by the
 * match centre for any day. Data flow is unchanged: upcoming matches are
 * fetched first, then predictions for up to 10 popular-league matches in the
 * next 24 hours are requested in the background (3 at a time, cached).
 */

import { useState, useEffect, useMemo } from 'react';
import { CalendarX } from 'lucide-react';
import { getUpcomingMatches, getMatchPrediction, getMatches, getCompetitions, formatDateForAPI } from '../api/client';
import type { MatchResponse, MatchPredictionResponse, CompetitionResponse } from '../api/types';
import { normalizeMatch } from '../utils/matchNormalizer';
import CombinePanel from '../components/combine/CombinePanel';
import { EmptyState } from '../components/ui';
import {
  DateStrip,
  LeagueGroup,
  MatchListSkeleton,
  PickLedger,
  probabilitiesFromPrediction,
  toMatchRowData,
} from '../components/matches';
import type { MatchRowData, PickLedgerEntry } from '../components/matches';
import { useFavorites } from '../hooks/useFavorites';
import { useCombine } from '../hooks/useCombine';
import { usePredictionCache } from '../contexts/PredictionCacheContext';
import { getCompetitionPriorityRank } from '../utils/popularCompetitions';
import { describePickMarket, VALUE_EVIDENCE_NOTE } from '../utils/pickMarket';
import './DashboardV2.css';

interface PickData {
  match: MatchResponse;
  prediction: MatchPredictionResponse;
}

/** Max number of predictions requested for the "Bugünün seçimleri" section. */
const MAX_DASHBOARD_PREDICTIONS = 10;
/** League groups expanded by default in the match center (popular leagues are always expanded). */
const DEFAULT_EXPANDED_GROUPS = 8;

/**
 * Run an async worker over items with at most `limit` workers in flight.
 * The worker must handle its own errors.
 */
async function runWithConcurrency<T>(
  items: T[],
  limit: number,
  worker: (item: T) => Promise<void>
): Promise<void> {
  let nextIndex = 0;
  const runners = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (nextIndex < items.length) {
      const item = items[nextIndex++];
      await worker(item);
    }
  });
  await Promise.all(runners);
}

function isSelectablePick(prediction: MatchPredictionResponse): boolean {
  return !!prediction.mensione_pick && !prediction.mensione_pick.pass_decision;
}

/** Ledger entry for a pick; every number is passed through unchanged. */
function toLedgerEntry({ match, prediction }: PickData): PickLedgerEntry {
  const normalizedMatch = normalizeMatch(match);
  const pick = prediction.mensione_pick!;
  const { marketName, outcome } = describePickMarket(pick.market, pick.selection, {
    home: normalizedMatch.homeTeam.name,
    away: normalizedMatch.awayTeam.name,
  });
  return {
    matchId: match.id,
    homeTeam: normalizedMatch.homeTeam.name,
    awayTeam: normalizedMatch.awayTeam.name,
    scheduledAt: match.scheduled_at,
    status: match.status,
    homeScore: match.home_score,
    awayScore: match.away_score,
    minute: match.minute,
    marketName,
    outcome,
    probability: pick.probability ?? null,
    fairOdds: pick.fair_odds ?? null,
    odds: pick.bookmaker_odds ?? null,
    oddsSource: pick.odds_source ?? null,
    valueClassification: pick.value_classification ?? null,
    confidence: pick.confidence ?? null,
  };
}

export function DashboardV2() {
  const [picksData, setPicksData] = useState<PickData[]>([]);
  const [loading, setLoading] = useState(true);
  const [predictionsLoading, setPredictionsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [picksReloadToken, setPicksReloadToken] = useState(0);

  // Match center state
  const [selectedDate, setSelectedDate] = useState(() => formatDateForAPI(new Date()));
  const [competitions, setCompetitions] = useState<CompetitionResponse[]>([]);
  const [matches, setMatches] = useState<MatchResponse[]>([]);
  const [matchesLoading, setMatchesLoading] = useState(true);
  const [matchesError, setMatchesError] = useState<string | null>(null);
  const [matchesReloadToken, setMatchesReloadToken] = useState(0);

  const { isFavorite, toggleFavorite } = useFavorites();
  const { isInCombine, toggleCombine, combineItems, removeFromCombine, clearCombine } = useCombine();
  // Only the stable (useCallback) cache functions are used as effect dependencies:
  // the context value object itself changes on every cache update, which previously
  // re-ran this effect, aborted in-flight prediction requests and left them "loading".
  const {
    getPrediction: getCachedPrediction,
    setLoading: markPredictionLoading,
    setPrediction: cachePrediction,
    setError: cachePredictionError,
    clearLoading: clearPredictionLoading,
  } = usePredictionCache();

  useEffect(() => {
    let isMounted = true;
    const abortController = new AbortController();

    async function fetchDashboardData() {
      try {
        setLoading(true);
        setError(null);

        // Fetch upcoming matches (today only for faster load)
        // Explicit limit: the backend default (100) can truncate busy match days.
        const matchesResponse = await getUpcomingMatches(1, 1000);

        if (!isMounted) return;

        // Render the page immediately; predictions load in the background.
        setLoading(false);

        await loadPredictions(matchesResponse.matches);
      } catch (err) {
        if (isMounted) {
          console.error('[DashboardV2] Error fetching data:', err);
          setError(err instanceof Error ? err.message : 'Veriler yüklenirken bir hata oluştu');
          setLoading(false);
          setPredictionsLoading(false);
        }
      }
    }

    async function loadPredictions(allMatches: MatchResponse[]) {
      if (!isMounted || allMatches.length === 0) return;

      const now = new Date();
      const next24Hours = new Date(now.getTime() + 24 * 60 * 60 * 1000);

      // Select candidate matches from popular competitions.
      // FotMob numeric IDs are ranked by an explicit allow-list (names like
      // "Premier League" are shared by many countries); see popularCompetitions.ts.
      const rankOf = (match: MatchResponse) =>
        getCompetitionPriorityRank(match.competition_name, match.competition_id);

      const candidateMatches = allMatches
        .filter((match) => {
          if (match.status !== 'SCHEDULED') return false;
          if (rankOf(match) === Number.MAX_SAFE_INTEGER) return false;
          const matchDate = new Date(match.scheduled_at);
          return matchDate >= now && matchDate <= next24Hours;
        })
        .sort(
          (a, b) =>
            rankOf(a) - rankOf(b) ||
            new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime()
        )
        .slice(0, MAX_DASHBOARD_PREDICTIONS);

      const order = new Map(candidateMatches.map((match, index) => [match.id, index]));
      const sortPicks = (picks: PickData[]) =>
        [...picks].sort((a, b) => (order.get(a.match.id) ?? 0) - (order.get(b.match.id) ?? 0));

      // Reuse predictions that are already cached; fetch the rest.
      const cachedPicks: PickData[] = [];
      const matchesToPredict: MatchResponse[] = [];
      for (const match of candidateMatches) {
        const cached = getCachedPrediction(match.id);
        if (cached?.prediction) {
          if (isSelectablePick(cached.prediction)) {
            cachedPicks.push({ match, prediction: cached.prediction });
          }
        } else if (!cached || (!cached.loading && !cached.error)) {
          matchesToPredict.push(match);
        }
      }

      setPicksData(sortPicks(cachedPicks));

      if (matchesToPredict.length === 0) {
        setPredictionsLoading(false);
        return;
      }

      setPredictionsLoading(true);

      await runWithConcurrency(matchesToPredict, 3, async (match) => {
        if (abortController.signal.aborted) return;
        markPredictionLoading(match.id);
        try {
          const prediction = await getMatchPrediction(match.id, abortController.signal);
          cachePrediction(match.id, prediction);
          // Only show picks with actual selections (not PASS); render progressively.
          if (isMounted && isSelectablePick(prediction)) {
            setPicksData((prev) =>
              sortPicks([...prev.filter((p) => p.match.id !== match.id), { match, prediction }])
            );
          }
        } catch (err) {
          const isAborted =
            (err instanceof DOMException && err.name === 'AbortError') ||
            (err instanceof Error && err.name === 'AbortError');
          if (isAborted) {
            clearPredictionLoading(match.id);
            return;
          }
          console.warn(`Failed to fetch prediction for match ${match.id}:`, err);
          cachePredictionError(match.id, err instanceof Error ? err : new Error('Unknown error'));
        }
      });

      if (isMounted) {
        setPredictionsLoading(false);
      }
    }

    fetchDashboardData();

    return () => {
      isMounted = false;
      abortController.abort();
    };
  }, [
    getCachedPrediction,
    markPredictionLoading,
    cachePrediction,
    cachePredictionError,
    clearPredictionLoading,
    picksReloadToken,
  ]);

  // Load matches for the match center section
  useEffect(() => {
    let isMounted = true;

    async function loadMatches() {
      try {
        setMatchesLoading(true);
        setMatchesError(null);

        // Load competitions and matches in parallel
        const [compsResponse, matchesResponse] = await Promise.all([
          getCompetitions(),
          getMatches({
            from_date: selectedDate,
            to_date: selectedDate,
            limit: 1000,
          }),
        ]);

        if (!isMounted) return;

        setCompetitions(compsResponse.competitions);
        setMatches(matchesResponse.matches);
      } catch (err) {
        if (!isMounted) return;
        console.error('[DashboardV2] Error loading matches:', err);
        setMatchesError(err instanceof Error ? err.message : 'Maçlar yüklenirken bir hata oluştu');
      } finally {
        if (isMounted) {
          setMatchesLoading(false);
        }
      }
    }

    loadMatches();

    return () => {
      isMounted = false;
    };
  }, [selectedDate, matchesReloadToken]);

  // Group matches by competition
  const matchesByCompetition = useMemo(() => {
    const grouped = new Map<string, { name: string; rank: number; matches: MatchRowData[] }>();

    matches.forEach((match) => {
      const compId = match.competition_id;
      const compName =
        match.competition_name || competitions.find((c) => c.id === compId)?.name || 'Lig bilgisi yok';
      // A provider competition ID can cover several stages/groups with different names.
      const groupKey = `${compId}|${compName}`;

      if (!grouped.has(groupKey)) {
        grouped.set(groupKey, {
          name: compName,
          rank: getCompetitionPriorityRank(compName, compId),
          matches: [],
        });
      }

      grouped.get(groupKey)!.matches.push(toMatchRowData(match, compName));
    });

    // Popular competitions first, then by match count (descending)
    return Array.from(grouped.entries())
      .map(([id, data]) => ({ id, ...data }))
      .sort((a, b) => a.rank - b.rank || b.matches.length - a.matches.length);
  }, [matches, competitions]);

  const leagueCount = useMemo(
    () => new Set(matches.map((match) => match.competition_id)).size,
    [matches]
  );

  // Predictions loaded above (or on a match page) add the model 1·X·2 column.
  // Read on every render: the cache context re-renders this page on updates.
  const renderedGroups = matchesByCompetition.map((group) => ({
    ...group,
    matches: group.matches.map((match) => ({
      ...match,
      probabilities: probabilitiesFromPrediction(getCachedPrediction(match.id)?.prediction),
    })),
  }));
  const showProbabilities = renderedGroups.some((group) =>
    group.matches.some((match) => !!match.probabilities)
  );

  const ledgerEntries = picksData.map(toLedgerEntry);
  const totalMatches = matches.length;

  const handleToggleCombine = (entry: PickLedgerEntry) => {
    toggleCombine({
      matchId: entry.matchId,
      marketName: entry.marketName,
      outcome: entry.outcome,
      marketOdds: entry.odds,
      confidence: entry.confidence,
      homeTeam: entry.homeTeam,
      awayTeam: entry.awayTeam,
      probability: entry.probability,
      oddsSource: entry.oddsSource,
    });
  };

  let picksContent;
  if (loading) {
    picksContent = <MatchListSkeleton rows={4} label="Bugünün maçları yükleniyor" />;
  } else if (error) {
    picksContent = (
      <div className="tx-dashboard__error" role="alert">
        <p className="tx-dashboard__error-message">Seçimler yüklenemedi: {error}</p>
        <button
          type="button"
          className="retry-button"
          onClick={() => setPicksReloadToken((token) => token + 1)}
        >
          Tekrar dene
        </button>
      </div>
    );
  } else if (predictionsLoading && ledgerEntries.length === 0) {
    picksContent = <MatchListSkeleton rows={4} label="Tahminler hazırlanıyor" />;
  } else if (ledgerEntries.length === 0) {
    picksContent = (
      <div className="tx-dashboard__empty">
        <p className="tx-dashboard__empty-title">Şu anda seçim yok</p>
        <p className="tx-dashboard__empty-description">
          Yaklaşan maçlar için yeterli veri olmayabilir ya da model incelenen maçların hepsinde pas
          geçmiş olabilir. Daha sonra tekrar kontrol edin.
        </p>
      </div>
    );
  } else {
    picksContent = (
      <PickLedger entries={ledgerEntries} isInCombine={isInCombine} onToggleCombine={handleToggleCombine} />
    );
  }

  return (
    <div className="tx-dashboard">
      <section className="tx-dashboard__section" aria-labelledby="tx-dashboard-picks-title">
        <header className="tx-dashboard__head">
          <h1 id="tx-dashboard-picks-title" className="tx-dashboard__title">
            Bugünün seçimleri
          </h1>
          {/* No count while predictions are still arriving: "0 seçim" would read as "no picks today". */}
          {!loading && !error && !predictionsLoading && (
            <p className="tx-dashboard__counts">
              <span>{ledgerEntries.length} seçim</span>
            </p>
          )}
          {predictionsLoading && ledgerEntries.length > 0 && (
            <span className="tx-dashboard__progress" role="status">
              <span className="loading-spinner" aria-hidden="true" />
              {ledgerEntries.length} seçim · diğer tahminler hazırlanıyor
            </span>
          )}
        </header>
        <p className="tx-dashboard__lede">
          10 büyük lig ve Avrupa kupalarında önümüzdeki 24 saatin en fazla {MAX_DASHBOARD_PREDICTIONS} maçı;
          her maç için modelin en güvendiği pazar.
          {ledgerEntries.some((e) => typeof e.odds === 'number' && e.odds > 1) && <> {VALUE_EVIDENCE_NOTE}</>}
        </p>
        {picksContent}
      </section>

      <div className="ruled tx-dashboard__divider" aria-hidden="true" />

      <section className="tx-dashboard__section" aria-labelledby="tx-dashboard-matches-title">
        <header className="tx-dashboard__head">
          <h2 id="tx-dashboard-matches-title" className="tx-dashboard__section-title">
            Tüm maçlar
          </h2>
          {!matchesLoading && !matchesError && (
            <p className="tx-dashboard__counts">
              <span>{totalMatches} maç</span>
              <span>{leagueCount} lig</span>
            </p>
          )}
        </header>

        <div className="tx-dashboard__date-filter">
          <DateStrip selectedDate={selectedDate} onDateChange={setSelectedDate} />
        </div>

        <div className="tx-dashboard__matches-content">
          {matchesLoading ? (
            <MatchListSkeleton rows={8} />
          ) : matchesError ? (
            <div className="tx-dashboard__error" role="alert">
              <p className="tx-dashboard__error-message">Maçlar yüklenemedi: {matchesError}</p>
              <button
                type="button"
                className="retry-button"
                onClick={() => setMatchesReloadToken((token) => token + 1)}
              >
                Tekrar dene
              </button>
            </div>
          ) : totalMatches === 0 ? (
            <EmptyState
              icon={<CalendarX size={18} strokeWidth={1.5} />}
              title="Maç bulunamadı"
              description="Seçilen tarih için hiç maç bulunmuyor. Başka bir tarih seçin."
            />
          ) : (
            <div className="tx-dashboard__matches-groups">
              {renderedGroups.map((group, index) => (
                <LeagueGroup
                  key={`${selectedDate}-${group.id}`}
                  leagueName={group.name}
                  matches={group.matches}
                  defaultExpanded={index < DEFAULT_EXPANDED_GROUPS || group.rank !== Number.MAX_SAFE_INTEGER}
                  isFavorite={isFavorite}
                  onToggleFavorite={toggleFavorite}
                  showProbabilities={showProbabilities}
                />
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Kombine slip */}
      <CombinePanel combineItems={combineItems} onRemoveItem={removeFromCombine} onClearAll={clearCombine} />
    </div>
  );
}
