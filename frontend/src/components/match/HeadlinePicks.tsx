/**
 * Banko + Oranlı: the two picks the system leads with on the match page.
 * Selection rule: utils/headlinePicks.ts (headline_v2). Every other market stays below.
 *
 * The Banko card names the tier of its pick ("Çok güçlü banko" >= 90 %, "Banko" 85-90 %, "Güçlü — banko
 * değil" 70-85 %, visibly quieter) and, where the research measured it, the past test rate of picks that
 * strong (utils/headlineEvidence.ts). Outside the tested competitions, and for a single 1X2 outcome, it
 * says why no rate is shown. Each card carries the status of the pick it shows, worked out per card
 * (utils/headlineRecord.ts cardPickStatus): "Ön tahmin" before the freeze until the line-ups are confirmed;
 * "Kesin" only for the frozen pick of that kind frozen with confirmed line-ups (or, before any freeze, a
 * pick computed from confirmed line-ups); "Kaydedildi" for a frozen pick without confirmed line-ups;
 * "Kayıtlı değil" for a live pick that is not the frozen one of its kind.
 *
 * Once the backend has frozen the picks (about 20 minutes before kick-off, api/headlineRecord.ts) a
 * one-line note says when and with which line-ups, and after the match each frozen pick carries its
 * result mark. The marks belong to the FROZEN pick; when the live rule gives a different pick now,
 * the frozen one is printed under the card with its own status.
 */

import { Plus, Minus } from 'lucide-react';
import type { HeadlineKind, HeadlinePickItem, MatchHeadlineRecord } from '../../api/headlineRecord';
import type { BankoTier, HeadlinePicks as Picks, PickCandidate } from '../../utils/headlinePicks';
import {
  BANKO_MAX_P,
  BANKO_MIN_P,
  ODDS_MIN_P,
  ODDS_MIN_PRICE,
  TIER_BANKO_MIN_P,
  TIER_COK_GUCLU_MIN_P,
  bankoTier,
} from '../../utils/headlinePicks';
import { bankoEvidenceLines, oranliEvidenceLines } from '../../utils/headlineEvidence';
import {
  cardPickStatus,
  cardStatusLines,
  describeFrozen,
  formatProbability,
  headlinePickStatus,
  pickCardNote,
  pickStatusLabel,
  resultMark,
  type CardStatus,
  type PickStatusInfo,
} from '../../utils/headlineRecord';
import './HeadlinePicks.css';

/** "%55" for a threshold (rounded: 0.55 * 100 is not exactly 55 in floating point). */
function pct(p: number): string {
  return `%${Math.round(p * 100)}`;
}

const TIER_TITLES: Record<BankoTier, string> = {
  cok_guclu: 'Çok güçlü banko',
  banko: 'Banko',
  guclu: 'Güçlü — banko değil',
};

function ResultMark({ pick }: { pick: HeadlinePickItem | null }) {
  const mark = pick ? resultMark(pick.result) : null;
  if (!mark) return null;
  return (
    <span className={`hp-card__mark hp-card__mark--${pick?.result}`} role="img" aria-label={mark.label} title={mark.label}>
      {mark.symbol}
    </span>
  );
}

function StatusLabel({ info }: { info: PickStatusInfo }) {
  return <span className={`hp-card__status hp-card__status--${info.status}`}>{pickStatusLabel(info.status)}</span>;
}

function PickCard({
  kind,
  pick,
  tier,
  frozen,
  empty,
  evidence,
  status,
  inCombine,
  onToggleCombine,
}: {
  kind: HeadlineKind;
  pick: PickCandidate | null;
  /** Banko slot tier (Banko card only) */
  tier: BankoTier | null;
  frozen: HeadlinePickItem | null;
  empty: string;
  /** past test rate, or why there is none */
  evidence: string[];
  /** status of the pick shown and, under a different live pick, of the frozen one */
  status: CardStatus;
  inCombine: boolean;
  onToggleCombine: (pick: PickCandidate) => void;
}) {
  const region = kind === 'banko' ? 'Banko' : 'Oranlı';
  const title = kind === 'banko' && tier ? TIER_TITLES[tier] : region;
  // the frozen pick is what counts; show it separately when today's rule would pick something else
  const differs = frozen !== null && (pick === null || pick.key !== frozen.market_key);
  const tierClass = kind === 'banko' && tier ? ` hp-card--tier-${tier}` : '';
  const note = pick ? pickCardNote(status.shown) : null;
  return (
    <section className={`hp-card hp-card--${kind}${tierClass}`} aria-label={region}>
      <p className="hp-card__kind">
        <span className="hp-card__title">{title}</span>
        {(pick || frozen) && <StatusLabel info={status.shown} />}
        {!differs && <ResultMark pick={frozen} />}
      </p>
      {pick ? (
        <>
          <p className="hp-card__outcome">{pick.outcome}</p>
          <p className="hp-card__market">{pick.marketName}</p>
          <p className="hp-card__numbers numeral">
            <span>
              Model <b>{pct(pick.probability)}</b>
            </span>
            <span>{pick.odds !== null ? `Oran ${pick.odds.toFixed(2)}` : `Adil oran ${pick.fairOdds.toFixed(2)}`}</span>
          </p>
          {evidence.map((line) => (
            <p key={line} className="hp-card__evidence">
              {line}
            </p>
          ))}
          {note && <p className="hp-card__status-note">{note}</p>}
          <button
            type="button"
            className={`hp-card__add${inCombine ? ' hp-card__add--on' : ''}`}
            onClick={() => onToggleCombine(pick)}
            aria-pressed={inCombine}
          >
            {inCombine ? <Minus size={14} strokeWidth={1.5} aria-hidden="true" /> : <Plus size={14} strokeWidth={1.5} aria-hidden="true" />}
            {inCombine ? 'Kombineden çıkar' : 'Kombineye ekle'}
          </button>
        </>
      ) : (
        !frozen && <p className="hp-card__empty">{empty}</p>
      )}
      {differs && frozen && (
        <p className="hp-card__recorded numeral">
          Kayıtlı seçim: {frozen.selection_text ?? frozen.label} · {formatProbability(frozen.probability)}
          {status.recorded && <StatusLabel info={status.recorded} />}
          <ResultMark pick={frozen} />
        </p>
      )}
    </section>
  );
}

export function HeadlinePicks({
  picks,
  isInCombine,
  onToggleCombine,
  record = null,
  competitionId,
  status,
}: {
  picks: Picks;
  isInCombine: (pick: PickCandidate) => boolean;
  onToggleCombine: (pick: PickCandidate) => void;
  /** The picks frozen before kick-off; null / absent when none were frozen (or not loaded) */
  record?: MatchHeadlineRecord | null;
  /**
   * FotMob parent league id of the match (e.g. "42"): past test rates only for the tested competitions.
   * null = not known (said so); undefined = still being looked up (no line yet).
   */
  competitionId?: string | null;
  /**
   * "Ön tahmin" / "Kesin" of the LIVE picks (line-ups of the prediction, headlinePickStatus); without it they
   * are an ön tahmin. Frozen picks are judged per card from `record`.
   */
  status?: PickStatusInfo;
}) {
  const frozenNote = describeFrozen(record);
  const live = status ?? headlinePickStatus({ predictionLineups: null, centreLineups: null });
  const matchFrozen = !!record?.frozen;
  const frozenBanko = record?.picks.banko ?? null;
  const frozenOranli = record?.picks.oranli ?? null;
  const bankoStatus = cardPickStatus({ livePickKey: picks.banko?.key ?? null, frozen: frozenBanko, matchFrozen, live });
  const oranliStatus = cardPickStatus({ livePickKey: picks.oranli?.key ?? null, frozen: frozenOranli, matchFrozen, live });
  // one line per distinct reason, only for the cards that show a pick
  const statusLines = cardStatusLines([
    ...(picks.banko || frozenBanko ? [bankoStatus] : []),
    ...(picks.oranli || frozenOranli ? [oranliStatus] : []),
  ]);
  // the live pick's tier; with no live pick, the tier of the frozen one
  const tier = picks.banko ? picks.bankoTier : frozenBanko ? frozenBanko.tier ?? bankoTier(frozenBanko.probability) : null;
  const lookingUp = competitionId === undefined;
  return (
    <div className="hp" role="group" aria-label="Sistemin iki seçimi">
      <PickCard
        kind="banko"
        pick={picks.banko}
        tier={tier}
        frozen={frozenBanko}
        empty={`Bu maçta ${pct(BANKO_MIN_P)} ve üstü güvenli seçim yok.`}
        evidence={lookingUp ? [] : bankoEvidenceLines(picks.banko, picks.bankoTier, competitionId)}
        status={bankoStatus}
        inCombine={!!picks.banko && isInCombine(picks.banko)}
        onToggleCombine={onToggleCombine}
      />
      <PickCard
        kind="oranli"
        pick={picks.oranli}
        tier={null}
        frozen={frozenOranli}
        empty={`${ODDS_MIN_PRICE.toFixed(2)} ve üstü ödeyen, en az ${pct(ODDS_MIN_P)} ihtimalli güvenilir seçim yok.`}
        evidence={lookingUp ? [] : oranliEvidenceLines(picks.oranli, competitionId)}
        status={oranliStatus}
        inCombine={!!picks.oranli && isInCombine(picks.oranli)}
        onToggleCombine={onToggleCombine}
      />
      {statusLines.map((line) => (
        <p key={line} className="hp__status">
          {line}
        </p>
      ))}
      {frozenNote && <p className="hp__frozen">{frozenNote}</p>}
      <p className="hp__note">
        Banko: modelin {pct(BANKO_MIN_P)}–{pct(BANKO_MAX_P).slice(1)} arasında en emin olduğu seçim.{' '}
        {pct(TIER_COK_GUCLU_MIN_P)} ve üstü “çok güçlü banko”, {pct(TIER_BANKO_MIN_P)}–{pct(TIER_COK_GUCLU_MIN_P).slice(1)}{' '}
        “banko”; {pct(BANKO_MIN_P)}–{pct(TIER_BANKO_MIN_P).slice(1)} arası “güçlü” seçim gösterilir ama banko sayılmaz.
        Oranlı: Banko ile aynı pazar ailesinden olmayan (maç sonucu ya da gol), ihtimali en az {pct(ODDS_MIN_P)} olan ve
        en az {ODDS_MIN_PRICE.toFixed(2)} ödeyen seçimler içinde ihtimali en yüksek olan. Oran yoksa adil oran (1 ÷
        ihtimal) gösterilir. Geçmiş test oranları kazanç anlamına gelmez: bu seçimlerin oranları düşüktür.
      </p>
    </div>
  );
}
