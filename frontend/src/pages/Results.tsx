/**
 * Sonuçlar: how the two headline picks (Banko and Oranlı) did.
 *
 * Every number comes from GET /track-record/headline: the picks the backend froze about 20 minutes
 * before kick-off (never changed afterwards) and settled after full time. Pending and void picks
 * are shown but are not part of a hit rate; with nothing settled the page says "veri yok".
 *
 * One rule version at a time: the current rule (headline_v2) by default, the old one (headline_v1)
 * behind a switch, so the two never mix (while the other version loads, or when it fails, the figures
 * of the previous one are not shown). The "Banko" figure and the Banko columns count only the Bankos
 * with p >= 0.85 (banko_strong); the güçlü 0.70-0.85 picks are not Bankos and have their own row in
 * the tier table (Çok güçlü / Banko / Güçlü). One line says how far the record is from the ~300 Bankos
 * a ~90 % claim needs.
 */

import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  useHeadlineTrackRecord,
  type BankoProgress,
  type HeadlinePickItem,
  type HeadlineTrackRecord,
  type KindPair,
  type KindSummary,
} from '../api/headlineRecord';
import {
  BANKO_MIN_P,
  ODDS_MIN_P,
  ODDS_MIN_PRICE,
  PREVIOUS_RULE_VERSION,
  RULE_VERSION,
  TIER_BANKO_MIN_P,
  TIER_COK_GUCLU_MIN_P,
  type BankoTier,
} from '../utils/headlinePicks';
import {
  formatFinalScore,
  formatProbability,
  formatRate,
  groupByMatch,
  lineupWord,
  resultMark,
} from '../utils/headlineRecord';
import './Results.css';

const PERIODS = [
  { days: 7, label: 'Son 7 gün' },
  { days: 30, label: 'Son 30 gün' },
] as const;

/** "v2" of "headline_v2". */
function versionTag(version: string): string {
  return version.replace(/^headline_/, '');
}

const RULE_VERSIONS = [
  { version: RULE_VERSION, label: `Güncel kural (${versionTag(RULE_VERSION)})` },
  { version: PREVIOUS_RULE_VERSION, label: `Eski kural (${versionTag(PREVIOUS_RULE_VERSION)})` },
] as const;

/** "90" for 0.9 (rounded: thresholds times 100 are not exact in floating point). */
function whole(p: number): number {
  return Math.round(p * 100);
}

const TIER_ROWS: { tier: BankoTier; label: string; range: string }[] = [
  { tier: 'cok_guclu', label: 'Çok güçlü', range: `model %${whole(TIER_COK_GUCLU_MIN_P)} ve üstü` },
  { tier: 'banko', label: 'Banko', range: `model %${whole(TIER_BANKO_MIN_P)}–${whole(TIER_COK_GUCLU_MIN_P)}` },
  {
    tier: 'guclu',
    label: 'Güçlü',
    range: `model %${whole(BANKO_MIN_P)}–${whole(TIER_BANKO_MIN_P)}, banko sayılmaz`,
  },
];

/** The Oranlı floor of each rule version (headline_v1 had 0.45, see backend/app/prediction/headline_picks.py). */
function oranliRange(ruleVersion: string | undefined): string {
  if (ruleVersion === PREVIOUS_RULE_VERSION) return `eski kural: ihtimal %45 ve üstü, oran ${ODDS_MIN_PRICE.toFixed(2)} ve üstü`;
  return `ihtimal %${whole(ODDS_MIN_P)} ve üstü, oran ${ODDS_MIN_PRICE.toFixed(2)} ve üstü`;
}

const TIER_SHORT: Record<BankoTier, string> = { cok_guclu: 'çok güçlü', banko: 'banko', guclu: 'güçlü' };

function kickoffText(iso: string | null): string {
  if (!iso) return 'veri yok';
  return new Date(iso).toLocaleString('tr-TR', {
    timeZone: 'Europe/Istanbul',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function dayText(isoDate: string): string {
  return new Date(`${isoDate}T12:00:00Z`).toLocaleDateString('tr-TR', {
    timeZone: 'Europe/Istanbul',
    day: 'numeric',
    month: 'short',
  });
}

function Figure({ title, caption, summary }: { title: string; caption?: string; summary: KindSummary }) {
  const extras = [
    summary.lost > 0 ? `${summary.lost} tutmadı` : null,
    summary.pending > 0 ? `${summary.pending} bekliyor` : null,
    summary.void > 0 ? `${summary.void} iptal` : null,
  ].filter((x): x is string => x !== null);
  return (
    <div className="results-figure" role="group" aria-label={`${title} başarı oranı`}>
      <p className="results-figure__title apparatus">{title}</p>
      {caption && <p className="results-figure__caption">{caption}</p>}
      <p className="results-figure__rate numeral">{formatRate(summary.hit_rate)}</p>
      <p className="results-figure__counts numeral">
        {summary.settled > 0
          ? `${summary.won} / ${summary.settled} tuttu`
          : 'Henüz sonuçlanan seçim yok'}
      </p>
      {extras.length > 0 && <p className="results-figure__more numeral">{extras.join(' · ')}</p>}
    </div>
  );
}

function PickCell({ pick }: { pick: HeadlinePickItem | null }) {
  if (!pick) {
    return (
      <span className="results-pick results-pick--none" title="Bu maç için bu seçim kaydedilmedi">
        yok
      </span>
    );
  }
  const mark = resultMark(pick.result);
  return (
    <span className="results-pick" title={pick.selection_text ?? undefined}>
      <span className="results-pick__label">{pick.label}</span>
      <span className="results-pick__p numeral">{formatProbability(pick.probability)}</span>
      {pick.kind === 'banko' && pick.tier && <span className="results-pick__tier">{TIER_SHORT[pick.tier]}</span>}
      {mark ? (
        <span className={`results-pick__mark results-pick__mark--${pick.result}`} role="img" aria-label={mark.label} title={mark.label}>
          {mark.symbol}
        </span>
      ) : (
        <span className="results-pick__pending">bekliyor</span>
      )}
    </span>
  );
}

function BreakdownCell({ summary }: { summary: KindSummary | null }) {
  if (!summary) return <span className="results-muted">veri yok</span>;
  if (summary.settled === 0) return <span className="results-muted">—</span>;
  return (
    <span className="numeral">
      {summary.won}/{summary.settled} · {formatRate(summary.hit_rate)}
    </span>
  );
}

function TierTable({ data }: { data: HeadlineTrackRecord }) {
  const tiers = data.banko_tiers;
  if (!tiers) return null;
  return (
    <section className="results__tiers" aria-label="Güce göre">
      <table className="results-table results-table--small">
        <thead>
          <tr>
            <th scope="col">Seçim</th>
            <th scope="col">Tuttu</th>
            <th scope="col">Bekleyen</th>
            <th scope="col">İptal</th>
          </tr>
        </thead>
        <tbody>
          {TIER_ROWS.map((row) => (
            <TierRow key={row.tier} label={row.label} range={row.range} summary={tiers[row.tier]} />
          ))}
          <TierRow label="Oranlı" range={oranliRange(data.rule_version)} summary={data.summary.oranli} />
        </tbody>
      </table>
    </section>
  );
}

function TierRow({ label, range, summary }: { label: string; range: string; summary: KindSummary }) {
  return (
    <tr>
      <th scope="row">
        {label}
        <span className="results-table__meta">{range}</span>
      </th>
      <td>
        <BreakdownCell summary={summary} />
      </td>
      <td className="numeral">{summary.pending}</td>
      <td className="numeral">{summary.void}</td>
    </tr>
  );
}

/** How far the record is from the ~300 recorded Bankos (p >= 0.85) a ~90 % claim needs. */
function ProgressLine({ progress }: { progress: BankoProgress }) {
  const floor = `%${Math.round(progress.min_probability * 100)}`;
  return (
    <p className="results__progress">
      Banko’nun (model {floor} ve üstü) yaklaşık %90 tuttuğunu söyleyebilmek için yaklaşık {progress.target} kayıtlı
      Banko gerekir. Bu kural sürümünde şimdiye kadar <b className="numeral">{progress.settled}</b> Banko sonuçlandı
      {progress.pending > 0 ? `, ${progress.pending} bekliyor` : ''}. Daha az kayıtla görülen oran tesadüf olabilir.
    </p>
  );
}

export function Results() {
  const [days, setDays] = useState<number>(30);
  const [competition, setCompetition] = useState<string>('');
  const [ruleVersion, setRuleVersion] = useState<string>(RULE_VERSION);
  const { data: loaded, dataRuleVersion, state, reload } = useHeadlineTrackRecord(days, competition || null, ruleVersion);
  // never the figures of another rule version under the selected button: while the selected one loads, or
  // after its request failed, the previous version's answer is not shown
  const data = loaded && dataRuleVersion === ruleVersion ? loaded : null;
  // a backend older than headline_v2 ignores the rule version (and sends none back)
  const versionIgnored = !!data && data.rule_version !== ruleVersion;
  // the Bankos with p >= 0.85 only; absent from a backend older than headline_v2
  const strongBanko = data?.summary.banko_strong ?? null;
  const bankoColumn = (pair: KindPair): KindSummary | null => (strongBanko ? pair.banko_strong ?? null : pair.banko);
  const bankoColumnTitle = strongBanko ? `Banko (%${whole(TIER_BANKO_MIN_P)}+)` : 'Banko';

  const options = useMemo(() => loaded?.available_competitions ?? [], [loaded]);
  // a competition that has no picks in the new period is dropped from the filter
  useEffect(() => {
    if (state === 'ready' && competition && !options.some((o) => o.id === competition)) setCompetition('');
  }, [state, competition, options]);

  const rows = useMemo(() => groupByMatch(data?.picks ?? []), [data]);
  const hasManual = (data?.picks ?? []).some((p) => (p.source ?? '').startsWith('manual_record'));

  return (
    <div className="results">
      <header className="results__head">
        <h1 className="results__title">Sonuçlar</h1>
        <p className="results__lede">
          Banko ve Oranlı seçimleri maçtan yaklaşık 20 dakika önce otomatik kaydedilir, sonradan değiştirilmez ve maç
          bitince sonuçlanır. Başarı oranı = tutan ÷ (tutan + tutmayan); bekleyen ve iptal edilenler dahil değildir.
          Her kural sürümü ayrı sayılır; varsayılan güncel kuraldır.
        </p>
      </header>

      <div className="results__filters">
        <div className="results__periods" role="group" aria-label="Kural sürümü">
          {RULE_VERSIONS.map((r) => (
            <button
              key={r.version}
              type="button"
              className="results__period"
              aria-pressed={ruleVersion === r.version}
              onClick={() => setRuleVersion(r.version)}
            >
              {r.label}
            </button>
          ))}
        </div>
        <div className="results__periods" role="group" aria-label="Dönem">
          {PERIODS.map((p) => (
            <button
              key={p.days}
              type="button"
              className="results__period"
              aria-pressed={days === p.days}
              onClick={() => setDays(p.days)}
            >
              {p.label}
            </button>
          ))}
        </div>
        <label className="results__select-label">
          <span className="apparatus">Yarışma</span>
          <select
            className="results__select"
            value={competition}
            onChange={(e) => setCompetition(e.target.value)}
            aria-label="Yarışma"
          >
            <option value="">Tüm yarışmalar</option>
            {options.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
        </label>
        {state === 'loading' && data && <span className="results__busy">Güncelleniyor…</span>}
      </div>

      {state === 'loading' && !data && (
        <div className="results__status" aria-busy="true">
          <div className="loading-spinner" />
          <p>Sonuçlar yükleniyor</p>
        </div>
      )}

      {state === 'error' && (
        <div className="results__error" role="alert">
          <p>Sonuçlar yüklenemedi.</p>
          <button type="button" className="results__retry" onClick={reload}>
            Tekrar dene
          </button>
        </div>
      )}

      {data && (
        <>
          {versionIgnored && (
            <p className="results__version-warning" role="note">
              Sunucu bu kural sürümünü ayırmıyor; aşağıdaki sayılar tüm kayıtlı seçimleri birlikte gösterir.
            </p>
          )}
          <section className="results__figures" aria-label="Başarı oranı">
            {strongBanko ? (
              <Figure title="Banko" caption={`model %${whole(TIER_BANKO_MIN_P)} ve üstü`} summary={strongBanko} />
            ) : (
              <Figure title="Banko" caption="tüm güçler birlikte" summary={data.summary.banko} />
            )}
            <Figure title="Oranlı" summary={data.summary.oranli} />
          </section>
          {data.banko_tiers && (
            <p className="results__tiers-lede">
              {strongBanko
                ? `Güce göre. Yukarıdaki Banko oranı yalnız model %${whole(TIER_BANKO_MIN_P)} ve üstü seçimleri sayar; güçlü seçimler banko sayılmaz:`
                : 'Banko kartı güce göre (yukarıdaki Banko oranı üçünü birlikte sayar):'}
            </p>
          )}
          <TierTable data={data} />
          {data.banko_progress && <ProgressLine progress={data.banko_progress} />}

          {rows.length === 0 ? (
            <div className="results__empty">
              <p className="results__empty-title">Bu dönemde kayıtlı seçim yok</p>
              <p className="results__empty-body">
                Seçimler, öne çıkan liglerin ve Avrupa kupalarının maçları için kickoff&apos;tan yaklaşık 20 dakika önce
                kaydedilir. İlk kayıtlar maçlar oynandıkça burada görünür.
              </p>
            </div>
          ) : (
            <section className="results__table-wrap" aria-label="Son seçimler">
              <table className="results-table">
                <thead>
                  <tr>
                    <th scope="col">Maç</th>
                    <th scope="col">Banko</th>
                    <th scope="col">Oranlı</th>
                    <th scope="col">Skor</th>
                    <th scope="col">Kadro</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.match_id}>
                      <th scope="row" className="results-table__match">
                        <Link to={`/matches/${encodeURIComponent(row.match_id)}`}>
                          {row.home_team ?? 'veri yok'} – {row.away_team ?? 'veri yok'}
                        </Link>
                        <span className="results-table__meta">
                          {row.competition_name ?? 'yarışma bilgisi yok'} · {kickoffText(row.kickoff_at)}
                          {[row.banko, row.oranli].some((p) => (p?.source ?? '').startsWith('manual_record')) &&
                            ' · elle kayıt'}
                        </span>
                      </th>
                      <td>
                        <PickCell pick={row.banko} />
                      </td>
                      <td>
                        <PickCell pick={row.oranli} />
                      </td>
                      <td className="numeral results-table__score">
                        {row.final_score ? (
                          formatFinalScore(row.final_score)
                        ) : (
                          <span className="results-muted" title="Skor yok: maç bitmedi ya da iptal edildi">
                            —
                          </span>
                        )}
                      </td>
                      <td className="results-table__lineup">
                        {lineupWord((row.banko ?? row.oranli)?.lineup_type)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {hasManual && (
                <p className="results__footnote">
                  “Elle kayıt”: 14 Ekim gecesinin seçimleri o gece elle not edilmişti ve sonradan sisteme aktarıldı;
                  bahis oranı kaydedilmemişti.
                </p>
              )}
            </section>
          )}

          {(data.by_competition.length > 1 || data.by_week.length > 1) && (
            <details className="results__details">
              <summary>Yarışmaya ve haftaya göre dağılım</summary>
              {data.by_competition.length > 1 && (
                <table className="results-table results-table--small">
                  <thead>
                    <tr>
                      <th scope="col">Yarışma</th>
                      <th scope="col">{bankoColumnTitle}</th>
                      <th scope="col">Oranlı</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_competition.map((c) => (
                      <tr key={c.competition_id ?? 'none'}>
                        <th scope="row">{c.competition_name ?? 'yarışma bilgisi yok'}</th>
                        <td>
                          <BreakdownCell summary={bankoColumn(c)} />
                        </td>
                        <td>
                          <BreakdownCell summary={c.oranli} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {data.by_week.length > 1 && (
                <table className="results-table results-table--small">
                  <thead>
                    <tr>
                      <th scope="col">Hafta (pazartesi)</th>
                      <th scope="col">{bankoColumnTitle}</th>
                      <th scope="col">Oranlı</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_week.map((w) => (
                      <tr key={w.week_start}>
                        <th scope="row" className="numeral">
                          {dayText(w.week_start)}
                        </th>
                        <td>
                          <BreakdownCell summary={bankoColumn(w)} />
                        </td>
                        <td>
                          <BreakdownCell summary={w.oranli} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </details>
          )}
        </>
      )}
    </div>
  );
}
