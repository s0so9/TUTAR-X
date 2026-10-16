/**
 * Maç analizi: the pre-match read of both teams from real results and FotMob fields.
 * Highlights first (fixed sentences with their numbers), then a compact home | away
 * table: last 5, home/away last 5, xG, rest, absentees, line-up and rotation.
 * Nothing is estimated here; missing values say "veri yok" and, where the backend
 * knows why, the reason is shown or available as a tooltip.
 */

import type {
  Absentee,
  FormWindow,
  MatchPreviewResponse,
  MatchPreviewState,
  PreviewMatch,
  PreviewSide,
} from '../../api/matchPreview';
import { UNAVAILABLE_LABEL } from '../../utils/displayValue';
import { describeAbsenceReason, describeExpectedReturn } from '../../utils/squadInfo';
import './MatchPreview.css';

const MAX_ABSENTEES_SHOWN = 4;

const LINEUP_TYPE_LABEL: Record<string, string> = {
  confirmed: 'Açıklandı',
  predicted: 'Tahmini kadro',
  last_starting11: 'Kadro açıklanmadı',
};

const RESULT_CLASS: Record<string, string> = { G: 'win', B: 'draw', M: 'loss' };

/** Turkish decimal comma, one digit: 7.64 -> "7,6". */
function oneDecimal(value: number): string {
  return value.toFixed(1).replace('.', ',');
}

function goalsText(w: FormWindow): string {
  return w.goals_for === null || w.goals_against === null ? UNAVAILABLE_LABEL : `${w.goals_for}–${w.goals_against}`;
}

function shortDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return UNAVAILABLE_LABEL;
  return d.toLocaleDateString('tr-TR', { day: 'numeric', month: 'short', timeZone: 'UTC' });
}

function matchTitle(m: PreviewMatch): string {
  const where = m.venue === 'home' ? 'ev' : 'dep.';
  const score = m.goals_for === null || m.goals_against === null ? UNAVAILABLE_LABEL : `${m.goals_for}–${m.goals_against}`;
  const xg = m.xg_for !== null && m.xg_against !== null ? ` · xG ${oneDecimal(m.xg_for)}–${oneDecimal(m.xg_against)}` : '';
  return `${shortDate(m.date)} · ${m.opponent ?? UNAVAILABLE_LABEL} (${where}) · ${score}${m.competition ? ` · ${m.competition}` : ''}${xg}`;
}

function FormChips({ window }: { window: FormWindow }) {
  if (window.played === 0 || !window.results) {
    return <span className="preview__muted" title={window.missing_reason ?? undefined}>{UNAVAILABLE_LABEL}</span>;
  }
  return (
    <span className="preview__form" aria-label={`Sonuçlar, en yeniden eskiye: ${window.results.split('').join(' ')}`}>
      {window.matches.map((m, i) => (
        <span key={`${m.match_id ?? 'm'}-${i}`} className={`preview__result preview__result--${RESULT_CLASS[m.result ?? ''] ?? 'draw'}`} title={matchTitle(m)}>
          {m.result ?? '?'}
        </span>
      ))}
    </span>
  );
}

function FormCell({ window }: { window: FormWindow }) {
  return (
    <>
      <FormChips window={window} />
      {window.played > 0 && (
        <span className="preview__goals numeral" title="Attığı – yediği gol">
          {goalsText(window)}
        </span>
      )}
      {window.played > 0 && window.played < 5 && (
        <span className="preview__muted preview__reason">{window.missing_reason ?? `Son 5 yerine ${window.played} maç`}</span>
      )}
      {window.played === 0 && window.missing_reason && <span className="preview__muted preview__reason">{window.missing_reason}</span>}
    </>
  );
}

function XgCell({ window }: { window: FormWindow }) {
  if (window.xg_for === null || window.xg_against === null || window.xg_matches === 0) {
    return <span className="preview__muted" title={window.xg_missing_reason ?? undefined}>{UNAVAILABLE_LABEL}</span>;
  }
  return (
    <>
      <span className="numeral" title="Toplam xG: attığı – yediği">{oneDecimal(window.xg_for)} – {oneDecimal(window.xg_against)}</span>
      {window.xg_matches < window.played && (
        <span className="preview__muted preview__reason">{window.xg_matches}/{window.played} maçta xG var</span>
      )}
    </>
  );
}

function RestCell({ side }: { side: PreviewSide }) {
  const { rest } = side;
  if (rest.rest_days === null) {
    return (
      <>
        <span className="preview__muted">{UNAVAILABLE_LABEL}</span>
        {rest.missing_reason && <span className="preview__muted preview__reason">{rest.missing_reason}</span>}
      </>
    );
  }
  return (
    <>
      <span className="numeral">{rest.rest_days} gün</span>
      {rest.matches_last_14_days !== null && (
        <span className="preview__muted preview__reason">son 14 günde {rest.matches_last_14_days} maç</span>
      )}
    </>
  );
}

function absenteeMeta(p: Absentee): string {
  const parts = [p.reason ?? (p.reason_code ? describeAbsenceReason(p.reason_code) : UNAVAILABLE_LABEL)];
  if (p.expected_return) parts.push(describeExpectedReturn(p.expected_return));
  return parts.join(' · ');
}

function AbsenteesCell({ side }: { side: PreviewSide }) {
  const { absentees } = side;
  if (!absentees.available) {
    return <span className="preview__muted" title={absentees.missing_reason ?? undefined}>{UNAVAILABLE_LABEL}</span>;
  }
  if (absentees.players.length === 0) return <span className="preview__muted">Bildirilen eksik yok</span>;
  const shown = absentees.players.slice(0, MAX_ABSENTEES_SHOWN);
  const rest = absentees.players.length - shown.length;
  return (
    <ul className="preview__absent">
      {shown.map((p, i) => (
        <li key={`${p.id ?? p.name ?? 'p'}-${i}`}>
          <span className="preview__absent-name">
            {p.name ?? UNAVAILABLE_LABEL}
            {p.started_previous_match === true && (
              <span className="preview__tag" title="Önceki maçta ilk 11'deydi">ilk 11</span>
            )}
          </span>
          <span className="preview__muted preview__absent-meta">{absenteeMeta(p)}</span>
        </li>
      ))}
      {rest > 0 && (
        <li className="preview__muted" title={absentees.players.slice(MAX_ABSENTEES_SHOWN).map((p) => p.name).filter(Boolean).join(', ')}>
          +{rest} oyuncu daha
        </li>
      )}
    </ul>
  );
}

function rotationTitle(side: PreviewSide): string | undefined {
  const r = side.lineup.rotation;
  const names = (list: { name: string | null }[]) => list.map((p) => p.name).filter(Boolean).join(', ');
  if (r.changes === null) return r.missing_reason ?? undefined;
  const inn = names(r.came_in);
  const out = names(r.dropped_out);
  return [inn && `Giren: ${inn}`, out && `Çıkan: ${out}`].filter(Boolean).join(' · ') || undefined;
}

function LineupCell({ side }: { side: PreviewSide }) {
  const { lineup } = side;
  if (!lineup.lineup_type) {
    return <span className="preview__muted" title={lineup.missing_reason ?? undefined}>{lineup.missing_reason ?? UNAVAILABLE_LABEL}</span>;
  }
  const rotation = lineup.rotation;
  return (
    <>
      <span>
        {LINEUP_TYPE_LABEL[lineup.lineup_type] ?? UNAVAILABLE_LABEL}
        {lineup.formation && lineup.lineup_type !== 'last_starting11' ? <span className="preview__muted"> · {lineup.formation}</span> : null}
      </span>
      {rotation.changes !== null ? (
        <span className="preview__rotation" title={rotationTitle(side)}>
          <span className="numeral">{rotation.changes}</span> değişiklik <span className="preview__muted">(geçen maça göre)</span>
        </span>
      ) : (
        <span className="preview__muted preview__reason" title={rotation.missing_reason ?? undefined}>
          {lineup.lineup_type === 'last_starting11'
            ? 'değişiklik sayısı kadro açıklanınca'
            : `değişiklik: ${UNAVAILABLE_LABEL}`}
        </span>
      )}
    </>
  );
}

function MatchLines({ title, window }: { title: string; window: FormWindow }) {
  if (window.matches.length === 0) return null;
  return (
    <div className="preview__lines">
      <p className="preview__lines-title">{title}</p>
      <ul>
        {window.matches.map((m, i) => (
          <li key={`${m.match_id ?? 'm'}-${i}`}>
            <span className="preview__muted">{shortDate(m.date)}</span>{' '}
            <span className={`preview__result preview__result--${RESULT_CLASS[m.result ?? ''] ?? 'draw'}`}>{m.result ?? '?'}</span>{' '}
            <span>
              {m.venue === 'home' ? '' : '@ '}
              {m.opponent ?? UNAVAILABLE_LABEL}
            </span>{' '}
            <span className="numeral">
              {m.goals_for ?? '?'}–{m.goals_against ?? '?'}
            </span>
            {m.xg_for !== null && m.xg_against !== null && (
              <span className="preview__muted"> · xG {oneDecimal(m.xg_for)}–{oneDecimal(m.xg_against)}</span>
            )}
            {m.source === 'fotmob_team_fixtures' && <span className="preview__muted"> · FotMob takım sayfası, xG yok</span>}
            {m.competition && <span className="preview__muted"> · {m.competition}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function SideDetails({ side, label }: { side: PreviewSide; label: string }) {
  const rotation = side.lineup.rotation;
  const names = (list: { name: string | null }[]) => list.map((p) => p.name).filter(Boolean).join(', ');
  return (
    <div className="preview__details-side">
      <h3 className="preview__details-title">{label}</h3>
      <MatchLines title="Son 5 maç" window={side.last5} />
      <MatchLines title={side.venue_last5.venue === 'home' ? 'Evde son 5' : 'Deplasmanda son 5'} window={side.venue_last5} />
      {rotation.changes !== null && (
        <p className="preview__lines-note">
          Geçen maça göre: giren {names(rotation.came_in) || UNAVAILABLE_LABEL}; çıkan {names(rotation.dropped_out) || UNAVAILABLE_LABEL}.
        </p>
      )}
      {side.data_notes.map((n) => (
        <p key={n} className="preview__lines-note preview__lines-note--warn">{n}</p>
      ))}
    </div>
  );
}

export function MatchPreview({ data, state }: { data: MatchPreviewResponse | null; state: MatchPreviewState }) {
  if (state === 'idle') return null;
  if (state === 'loading') {
    return (
      <section className="preview preview--state" aria-busy="true" aria-label="Maç analizi">
        <p className="preview__muted">Maç analizi hazırlanıyor</p>
      </section>
    );
  }
  if (state === 'unavailable' || !data) {
    return (
      <section className="preview preview--state" aria-label="Maç analizi">
        <p className="preview__muted">Maç analizi şu an alınamadı.</p>
      </section>
    );
  }

  const home = data.home;
  const away = data.away;
  const homeName = home.team_name ?? 'Ev sahibi';
  const awayName = away.team_name ?? 'Deplasman';
  const rows: { key: string; label: string; cell: (s: PreviewSide) => React.ReactNode }[] = [
    { key: 'last5', label: 'Son 5 maç', cell: (s) => <FormCell window={s.last5} /> },
    { key: 'venue', label: 'Evde / dep.', cell: (s) => <FormCell window={s.venue_last5} /> },
    { key: 'xg', label: 'xG (son 5)', cell: (s) => <XgCell window={s.last5} /> },
    { key: 'rest', label: 'Dinlenme', cell: (s) => <RestCell side={s} /> },
    { key: 'absent', label: 'Eksikler', cell: (s) => <AbsenteesCell side={s} /> },
    { key: 'lineup', label: 'Kadro', cell: (s) => <LineupCell side={s} /> },
  ];
  const notes = [...data.notes, ...home.data_notes.map((n) => `${homeName}: ${n}`), ...away.data_notes.map((n) => `${awayName}: ${n}`)];

  return (
    <section className="preview" aria-labelledby="preview-title">
      <header className="preview__head">
        <h2 id="preview-title" className="preview__title">Maç analizi</h2>
        <p className="preview__sub">Gerçek sonuçlardan ve FotMob verisinden · hazırlık maçları son 5'e dahil değil</p>
      </header>

      {data.highlights.length > 0 ? (
        <ul className="preview__highlights">
          {data.highlights.map((h) => (
            <li key={h.id} className="preview__highlight">{h.text}</li>
          ))}
        </ul>
      ) : (
        <p className="preview__muted preview__quiet">Öne çıkan bir bulgu yok; ayrıntılar aşağıda.</p>
      )}

      <div className="preview__table" role="table" aria-label="Takımların maç öncesi karşılaştırması">
        <div className="preview__row preview__row--head" role="row">
          <span role="columnheader" />
          <span role="columnheader" className="preview__team">{homeName}</span>
          <span role="columnheader" className="preview__team">{awayName}</span>
        </div>
        {rows.map((r) => (
          <div className="preview__row" role="row" key={r.key}>
            <span role="rowheader" className="preview__label" title={r.key === 'venue' ? 'Ev sahibinin evinde, deplasman takımının deplasmanda oynadığı son 5 maç' : undefined}>{r.label}</span>
            <span role="cell" className="preview__cell">{r.cell(home)}</span>
            <span role="cell" className="preview__cell">{r.cell(away)}</span>
          </div>
        ))}
      </div>

      <details className="preview__details">
        <summary>Maç ayrıntıları</summary>
        <div className="preview__details-grid">
          <SideDetails side={home} label={homeName} />
          <SideDetails side={away} label={awayName} />
        </div>
      </details>

      {notes.length > 0 && (
        <ul className="preview__notes">
          {notes.map((n) => (
            <li key={n} className="preview__muted">{n}</li>
          ))}
        </ul>
      )}
      <p className="preview__source preview__muted">
        {data.sources.length ? data.sources.join(' ') : 'Kaynak: yerel veritabanı ve FotMob.'}
      </p>
    </section>
  );
}
