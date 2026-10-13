/**
 * Match page — one two-sided sheet.
 *
 * Home reads in the left column, away in the right, and a centre rail of market
 * keys carries the decision between them. Pressing an outcome opens its
 * apparatus in the margin (model, market, odds and their source, edge), from
 * where it goes into the kombine. The same page follows the match live and
 * settles the picks after the final whistle.
 */

import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Star } from 'lucide-react';
import { getMatch } from '../api';
import type { MatchPredictionResponse, MatchResponse, TeamFormResponse } from '../api/types';
import type { LiveStats } from '../types/live';
import { formatCompetitionName, formatMatchDateTime, formatMatchStatus, formatTeamName } from '../utils/formatters';
import { describeAbsenceReason, describeExpectedReturn, formatMarketValueEur, isPredictedLineup } from '../utils/squadInfo';
import { formatNumber } from '../utils/displayValue';
import { describePickMarket, isManualUserSuppliedOdds } from '../utils/pickMarket';
import { useFavorites } from '../hooks/useFavorites';
import { useCombine } from '../hooks/useCombine';
import { useLiveMatch } from '../hooks/useLiveMatch';
import { useLazyPrediction } from '../hooks/useLazyPrediction';
import CombineDrawer from '../components/combine/CombineDrawer';
import { MarketRail } from '../components/match/rail/MarketRail';
import { OutcomeApparatus, PickNote } from '../components/match/rail/MarginNotes';
import { buildRailRows, settledOutcomeKeys, type RailOutcome, type RailRow } from '../components/match/rail/railModel';
import './MatchDetailV2.css';

const LIVE_STAT_ROWS: { key: keyof LiveStats; label: string; unit?: string; digits?: number }[] = [
  { key: 'possession', label: 'Topa sahip olma', unit: '%' },
  { key: 'xG', label: 'xG', digits: 2 },
  { key: 'shots', label: 'Şut' },
  { key: 'shotsOnTarget', label: 'İsabetli şut' },
  { key: 'bigChances', label: 'Net fırsat' },
  { key: 'corners', label: 'Korner' },
  { key: 'fouls', label: 'Faul' },
  { key: 'yellowCards', label: 'Sarı kart' },
  { key: 'redCards', label: 'Kırmızı kart' },
];

/** One sentence naming where the odds on this page came from. */
function describeOddsProvenance(rows: RailRow[]): string {
  const sources = new Set(
    rows
      .flatMap((r) => [r.left, r.centre, r.right])
      .map((o) => (o?.odds ? o.oddsSource ?? 'bilinmeyen kaynak' : null))
      .filter((s): s is string => s !== null),
  );
  if (sources.size === 0) return 'Bu maç için oran verisi yok.';
  if ([...sources].every((s) => isManualUserSuppliedOdds(s))) return 'Oranlar kullanıcı girişidir, doğrulanmadı.';
  return `Oranlar: ${[...sources].map((s) => (isManualUserSuppliedOdds(s) ? 'kullanıcı girişi (doğrulanmadı)' : s)).join(', ')}.`;
}

function TwinSection({
  id,
  railKey,
  title,
  left,
  right,
  centre,
}: {
  id: string;
  railKey: string;
  title: string;
  left: React.ReactNode;
  right: React.ReactNode;
  centre?: React.ReactNode;
}) {
  return (
    <section className="twin" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`} className="sr-only">{title}</h2>
      <div className="twin__side twin__side--left">{left}</div>
      <div className="twin__key">
        <span className="apparatus">{railKey}</span>
        {centre}
      </div>
      <div className="twin__side twin__side--right">{right}</div>
    </section>
  );
}

function FormSide({ form }: { form: TeamFormResponse | null | undefined }) {
  if (!form) return <p className="twin__empty">Form verisi yok</p>;
  // The form window is the matches behind the W/D/L counts; matches_analyzed
  // counts a wider sample and must not be used as the points denominator.
  const played = form.wins + form.draws + form.losses;
  if (!Number.isFinite(played) || played <= 0) return <p className="twin__empty">Form verisi yok</p>;
  return (
    <>
      <p className="twin__caption">Son {played} maç</p>
      <dl className="twin-ledger">
        <div><dt className="ledger-term">G · B · M</dt><dd className="numeral">{form.wins} · {form.draws} · {form.losses}</dd></div>
        <div><dt className="ledger-term">Gol</dt><dd className="numeral">{form.goals_for} – {form.goals_against}</dd></div>
        <div><dt className="ledger-term">Puan</dt><dd className="numeral">{form.points} / {played * 3}</dd></div>
      </dl>
    </>
  );
}

function SquadSide({ team }: { team: NonNullable<MatchPredictionResponse['squad_info']>['home'] | undefined }) {
  if (!team) return <p className="twin__empty">Kadro verisi yok</p>;
  const missing = Array.isArray(team.unavailable) ? team.unavailable : null;
  return (
    <div className="squad">
      <p className="squad__value">
        <span className="numeral">{formatMarketValueEur(team.starter_value)}</span>
        <span className="squad__value-label">
          <span className="squad__value-part">ilk 11 değeri</span>
          {isPredictedLineup(team.lineup_type) && <span className="squad__value-part"> · tahmini kadro</span>}
        </span>
      </p>
      {missing === null ? (
        <p className="twin__empty">Eksik oyuncu verisi yok</p>
      ) : missing.length === 0 ? (
        <p className="twin__empty">Bildirilen eksik yok</p>
      ) : (
        <ul className="squad__missing">
          {missing.map((p, i) => (
            <li key={`${p.name}-${i}`}>
              <span className="squad__name">{p.name}</span>
              <span className="squad__meta">
                {describeAbsenceReason(p.reason)} · {describeExpectedReturn(p.expected_return)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function MatchDetailV2() {
  const { id } = useParams<{ id: string }>();
  const [match, setMatch] = useState<MatchResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDevelopmentData, setIsDevelopmentData] = useState(false);
  const [selected, setSelected] = useState<RailOutcome | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const { isFavorite, toggleFavorite } = useFavorites();
  const { combineItems, isInCombine, toggleCombine, removeFromCombine, clearCombine } = useCombine();

  // The model's pre-match view is shown before, during and after the match.
  const shouldLoadPrediction = !!match && match.status !== 'CANCELLED';
  const { prediction, loading: predictionLoading, error: predictionError } = useLazyPrediction(
    shouldLoadPrediction ? id : null,
  );

  // The feed also sends HALF_TIME (not in MatchStatus); it is followed as a live match.
  const isHalfTime = (match?.status as string | undefined) === 'HALF_TIME';
  const isMatchLive = match?.status === 'LIVE' || isHalfTime;
  const { liveMatch, lastUpdated } = useLiveMatch(id || '', { enabled: isMatchLive });

  useEffect(() => {
    let cancelled = false;
    async function fetchMatchData() {
      if (!id) {
        setError('Geçersiz maç kimliği');
        setLoading(false);
        return;
      }
      try {
        setLoading(true);
        setError(null);
        const response = await getMatch(id);
        if (cancelled) return;
        setMatch(response.match);
        setIsDevelopmentData(response.is_development_data);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error && err.message.includes('404') ? 'Maç bulunamadı' : 'Maç yüklenemedi');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchMatchData();
    return () => {
      cancelled = true;
    };
  }, [id, reloadKey]);

  const homeTeam = match ? (match.home_team ? match.home_team.name : formatTeamName(match.home_team_id)) : '';
  const awayTeam = match ? (match.away_team ? match.away_team.name : formatTeamName(match.away_team_id)) : '';
  const teams = useMemo(() => ({ home: homeTeam, away: awayTeam }), [homeTeam, awayTeam]);

  const rows = useMemo(() => (prediction ? buildRailRows(prediction, teams) : []), [prediction, teams]);

  if (loading) {
    return (
      <div className="sheet sheet--loading" aria-busy="true">
        <div className="loading-spinner" />
        <p className="sheet__muted">Maç yükleniyor</p>
      </div>
    );
  }

  if (error || !match) {
    return (
      <div className="sheet sheet--message">
        <h1 className="sheet__message-title">{error || 'Maç bulunamadı'}</h1>
        <p className="sheet__message-body">
          {error && error !== 'Maç bulunamadı'
            ? 'Bağlantıyı kontrol edip tekrar deneyin ya da maç listesine dönün.'
            : 'Maç listesine dönüp başka bir maç seçebilirsiniz.'}
        </p>
        <div className="sheet__message-actions">
          {error && error !== 'Maç bulunamadı' && (
            <button type="button" className="retry-button" onClick={() => setReloadKey((k) => k + 1)}>
              Tekrar dene
            </button>
          )}
          <Link to="/matches" className="back-link">
            <ArrowLeft size={14} strokeWidth={1.5} aria-hidden="true" /> Maç Merkezi
          </Link>
        </div>
      </div>
    );
  }

  const dateTime = formatMatchDateTime(match.scheduled_at);
  const competition = match.competition_name || formatCompetitionName(match.competition_id);
  const live = isMatchLive;
  const finished = match.status === 'FINISHED';

  const homeScore = live ? liveMatch?.homeScore ?? match.home_score : match.home_score;
  const awayScore = live ? liveMatch?.awayScore ?? match.away_score : match.away_score;
  const showScore = (live || finished) && homeScore !== null && homeScore !== undefined && awayScore !== null && awayScore !== undefined;
  const minute = liveMatch?.minute ?? match.minute ?? null;
  const addedTime = liveMatch?.addedTime ?? match.added_time ?? null;

  const settled = finished && showScore ? settledOutcomeKeys(homeScore as number, awayScore as number) : null;
  const pick = prediction?.mensione_pick ?? null;
  const pickKey = pick && !pick.pass_decision && pick.market ? pick.market.toUpperCase() : null;
  const pickLanded = settled && pickKey ? settled.has(pickKey) : null;

  const favorite = isFavorite(match.id);
  const combineHas = isInCombine(match.id);

  const toggleCombineFor = (
    marketName: string,
    outcome: string,
    odds: number | null,
    confidence: number | null,
    probability: number | null,
    oddsSource: string | null,
  ) =>
    toggleCombine({
      matchId: match.id,
      marketName,
      outcome,
      marketOdds: odds,
      confidence,
      homeTeam,
      awayTeam,
      probability,
      oddsSource,
    });

  const togglePickCombine = () => {
    if (!pick || pick.pass_decision) return;
    const label = describePickMarket(pick.market, pick.selection, teams);
    toggleCombineFor(
      label.marketName,
      label.outcome,
      pick.bookmaker_odds ?? null,
      pick.confidence ?? null,
      pick.probability ?? null,
      pick.odds_source ?? null,
    );
  };

  const focusPick = () => {
    const outcome = rows.flatMap((r) => [r.left, r.centre, r.right]).find((o) => o?.key === pickKey);
    if (outcome) setSelected(outcome);
  };

  const homeStats = liveMatch?.homeStats;
  const awayStats = liveMatch?.awayStats;
  const liveStatRows = LIVE_STAT_ROWS.filter(
    (s) => typeof homeStats?.[s.key] === 'number' || typeof awayStats?.[s.key] === 'number',
  );

  return (
    <div className="sheet">
      <div className="sheet__topline">
        <Link to="/matches" className="back-link">
          <ArrowLeft size={14} strokeWidth={1.5} aria-hidden="true" /> Maç Merkezi
        </Link>
        <p className="sheet__meta">
          <span>{competition}{match.round ? ` · ${match.round}. hafta` : ''}</span>
          <span className="sheet__meta-sep" aria-hidden="true">·</span>
          <time dateTime={match.scheduled_at}>{dateTime.full}</time>
          <span className={`sheet__status sheet__status--${live ? 'live' : match.status.toLowerCase()}`}>
            {isHalfTime ? 'Devre arası' : formatMatchStatus(match.status)}
          </span>
          {isDevelopmentData && <span className="sheet__dev">Geliştirme verisi</span>}
        </p>
        <button
          type="button"
          className={`sheet__favorite${favorite ? ' sheet__favorite--on' : ''}`}
          onClick={() => toggleFavorite(match.id)}
          aria-pressed={favorite}
          aria-label={favorite ? 'Favorilerden çıkar' : 'Favorilere ekle'}
        >
          <Star size={16} strokeWidth={1.5} fill={favorite ? 'currentColor' : 'none'} aria-hidden="true" />
        </button>
      </div>

      <div className="sheet__grid">
        <div className="sheet__main">
          <header className="teams">
            <h1 className="teams__name teams__name--home">{homeTeam}</h1>
            <div className={`teams__head${live ? ' teams__head--live' : ''}`}>
              {showScore ? (
                <>
                  <span className="teams__score numeral" aria-label={`Skor ${homeScore} – ${awayScore}`}>
                    {homeScore}<span className="teams__score-sep">–</span>{awayScore}
                  </span>
                  <span className="teams__clock">
                    {live
                      ? isHalfTime
                        ? 'Devre arası'
                        : minute !== null
                          ? `${minute}'${addedTime ? `+${addedTime}` : ''}`
                          : 'Canlı'
                      : 'Maç sonu'}
                  </span>
                </>
              ) : (
                <>
                  <span className="teams__kickoff numeral">{dateTime.time}</span>
                  <span className="teams__clock">{dateTime.date}</span>
                </>
              )}
              {prediction?.predicted_score && (
                <span className="teams__forecast">
                  <span className="teams__forecast-label">Model skoru</span>{' '}
                  <span className="numeral">{prediction.predicted_score.replace('-', '–')}</span>
                </span>
              )}
            </div>
            <h1 className="teams__name teams__name--away">{awayTeam}</h1>
          </header>

          {(live || finished) && prediction && (
            <p className="sheet__note">
              Aşağıdaki olasılıklar modelin maç öncesi görüşüdür; maç {live ? 'devam ederken' : 'bittikten sonra'} güncellenmez.
            </p>
          )}

          {predictionLoading && (
            <div className="sheet__state" aria-busy="true">
              <div className="loading-spinner" />
              <p className="sheet__muted">Model hesaplıyor</p>
            </div>
          )}

          {predictionError && !predictionLoading && (
            <div className="sheet__state sheet__state--error" role="alert">
              <p className="sheet__state-title">Tahmin oluşturulamadı</p>
              <p className="sheet__state-body">
                {predictionError.message.includes('Insufficient data')
                  ? 'Bu maç için yeterli geçmiş veri yok.'
                  : 'Model şu an yanıt vermiyor. Biraz sonra tekrar deneyin.'}
              </p>
            </div>
          )}

          {prediction && !predictionLoading && (
            <>
              <MarketRail
                rows={rows}
                selectedKey={selected?.key ?? null}
                pickKey={pickKey}
                settled={settled}
                onSelect={(o) => setSelected((cur) => (cur?.key === o.key ? null : o))}
              />

              <TwinSection
                id="xg"
                railKey="Beklenen gol"
                title="Beklenen gol"
                left={<p className="twin__figure numeral">{formatNumber(prediction.home_xg, 2)}</p>}
                right={<p className="twin__figure numeral">{formatNumber(prediction.away_xg, 2)}</p>}
              />

              {live && liveStatRows.length > 0 && (
                <section className="live-stats" aria-label="Canlı istatistikler">
                  {liveStatRows.map((s) => {
                    const h = homeStats?.[s.key];
                    const a = awayStats?.[s.key];
                    const fmt = (v: number | undefined) =>
                      typeof v === 'number' ? `${v.toFixed(s.digits ?? 0)}${s.unit ?? ''}` : 'veri yok';
                    return (
                      <div className="live-stats__row" key={s.key}>
                        <span className="numeral">{fmt(h as number | undefined)}</span>
                        <span className="apparatus">{s.label}</span>
                        <span className="numeral">{fmt(a as number | undefined)}</span>
                      </div>
                    );
                  })}
                  {lastUpdated && (
                    <p className="live-stats__stamp">
                      Son güncelleme {new Date(lastUpdated).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </p>
                  )}
                </section>
              )}

              <TwinSection
                id="squad"
                railKey="Kadro"
                title="Kadro durumu"
                left={<SquadSide team={prediction.squad_info?.home} />}
                right={<SquadSide team={prediction.squad_info?.away} />}
                centre={prediction.squad_info ? <span className="twin__source">FotMob</span> : null}
              />

              <TwinSection
                id="form"
                railKey="Son form"
                title="Son form"
                left={<FormSide form={prediction.home_form} />}
                right={<FormSide form={prediction.away_form} />}
              />

              <TwinSection
                id="h2h"
                railKey="Aralarında"
                title="Aralarındaki maçlar"
                left={
                  prediction.head_to_head && prediction.head_to_head.total_matches > 0 ? (
                    <p className="twin__figure numeral">{prediction.head_to_head.home_wins}</p>
                  ) : (
                    <p className="twin__empty">Kayıtlı maç yok</p>
                  )
                }
                right={
                  prediction.head_to_head && prediction.head_to_head.total_matches > 0 ? (
                    <p className="twin__figure numeral">{prediction.head_to_head.away_wins}</p>
                  ) : null
                }
                centre={
                  prediction.head_to_head && prediction.head_to_head.total_matches > 0 ? (
                    <span className="numeral twin__centre-figure">
                      {prediction.head_to_head.draws} beraberlik · {prediction.head_to_head.total_matches} maç
                    </span>
                  ) : null
                }
              />
            </>
          )}
        </div>

        <aside className="sheet__margin" aria-label="Seçim ve pazar detayı">
          {prediction && !predictionLoading && (
            <PickNote
              pick={pick}
              teams={teams}
              inCombine={combineHas}
              onToggleCombine={togglePickCombine}
              landed={pickLanded}
              onFocusPick={focusPick}
            />
          )}
          {selected && (
            <OutcomeApparatus
              outcome={selected}
              inCombine={combineHas}
              onToggleCombine={() =>
                toggleCombineFor(
                  selected.marketName,
                  selected.outcomeName,
                  selected.odds,
                  pickKey === selected.key ? pick?.confidence ?? null : null,
                  selected.probability,
                  selected.oddsSource,
                )
              }
              onClose={() => setSelected(null)}
            />
          )}
          {prediction && !predictionLoading && (
            <p className="sheet__provenance">
              Olasılıklar: TUTAR X modeli (takım reytingi + ilk 11 değeri).
              {prediction.squad_info ? ' Kadro: FotMob.' : ''} {describeOddsProvenance(rows)}
            </p>
          )}
        </aside>
      </div>

      <CombineDrawer items={combineItems} onRemove={removeFromCombine} onClear={clearCombine} />
    </div>
  );
}
