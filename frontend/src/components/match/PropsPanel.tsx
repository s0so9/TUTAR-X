/**
 * Kart · Korner · Şut: expected counts per team and in total, the most useful
 * over/under lines and the teams' real last-5 averages. Numbers come straight
 * from GET /matches/{id}/props; nothing is filled in.
 */

import type { PropLine, PropMarket, PropRecent, PropsResponse } from '../../api/props';
import './PropsPanel.css';

const GROUP_ORDER = ['Kartlar', 'Kornerler', 'Şutlar'];

function pct(p: number): string {
  return `%${Math.round(p * 100)}`;
}

function num(v: number | null | undefined, digits = 1): string {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : 'veri yok';
}

/** The line closest to a coin flip, plus the safest "over" and "under" (>= 70 %) when they exist. */
function pickLines(lines: PropLine[]): { line: PropLine; side: 'over' | 'under' }[] {
  if (!lines.length) return [];
  const out: { line: PropLine; side: 'over' | 'under' }[] = [];
  const mid = [...lines].sort((a, b) => Math.abs(a.over - 0.5) - Math.abs(b.over - 0.5))[0];
  out.push({ line: mid, side: mid.over >= 0.5 ? 'over' : 'under' });
  const safeOver = [...lines].filter((l) => l.over >= 0.7).sort((a, b) => b.line - a.line)[0];
  const safeUnder = [...lines].filter((l) => l.under >= 0.7).sort((a, b) => a.line - b.line)[0];
  if (safeOver && safeOver !== mid) out.push({ line: safeOver, side: 'over' });
  if (safeUnder && safeUnder !== mid) out.push({ line: safeUnder, side: 'under' });
  return out;
}

function LineChips({ market }: { market: PropMarket | undefined }) {
  if (!market) return <span className="props__muted">veri yok</span>;
  const chosen = pickLines(market.lines);
  if (!chosen.length) return <span className="props__muted">veri yok</span>;
  return (
    <span className="props__chips">
      {chosen.map(({ line, side }) => (
        <span
          key={`${line.line}-${side}`}
          className={`props__chip${
            market.banko_eligible !== false && (side === 'over' ? line.over : line.under) >= 0.7 ? ' props__chip--strong' : ''
          }`}
          title={`${line.line} Alt ${pct(line.under)} · Üst ${pct(line.over)}`}
        >
          {line.line} {side === 'over' ? 'Üst' : 'Alt'} <b className="numeral">{pct(side === 'over' ? line.over : line.under)}</b>
        </span>
      ))}
    </span>
  );
}

function recentFor(recent: PropRecent[] | undefined, stat: string): PropRecent | undefined {
  return recent?.find((r) => r.stat === stat);
}

const GROUP_STATS: Record<string, { stat: string; team: string; total: string; name: string }[]> = {
  Kartlar: [{ stat: 'yellow_cards', team: 'team_yellow_cards', total: 'total_yellow_cards', name: 'Sarı kart' }],
  Kornerler: [{ stat: 'corners', team: 'team_corners', total: 'total_corners', name: 'Korner' }],
  Şutlar: [
    { stat: 'total_shots', team: 'team_shots', total: 'total_shots', name: 'Şut' },
    { stat: 'shots_on_target', team: 'team_shots_on_target', total: 'total_shots_on_target', name: 'İsabetli şut' },
  ],
};

export function PropsPanel({ data }: { data: PropsResponse }) {
  const find = (key: string, scope: PropMarket['scope']) => data.markets.find((m) => m.key === key && m.scope === scope);
  const home = data.home_team ?? 'Ev sahibi';
  const away = data.away_team ?? 'Deplasman';
  const groups = GROUP_ORDER.filter((g) => data.markets.some((m) => m.group === g));
  if (!groups.length) return null;

  return (
    <section className="props" aria-labelledby="props-title">
      <header className="props__head">
        <h2 id="props-title" className="props__title">Kart · Korner · Şut</h2>
        <p className="props__sub">
          Beklenen sayılar rakibe göre hesaplanır
          {data.referee ? ` · Hakem: ${data.referee}${data.referee_used ? '' : ' (geçmiş verisi yok)'}` : ''}
        </p>
      </header>

      <div className="props__table" role="table" aria-label="Kart, korner ve şut tahminleri">
        <div className="props__row props__row--head" role="row">
          <span role="columnheader" />
          <span role="columnheader" className="props__team">{home}</span>
          <span role="columnheader">Toplam</span>
          <span role="columnheader" className="props__team">{away}</span>
        </div>
        {groups.flatMap((g) =>
          (GROUP_STATS[g] ?? []).map((s) => {
            const mh = find(s.team, 'home');
            const ma = find(s.team, 'away');
            const mt = find(s.total, 'total');
            if (!mh && !ma && !mt) return null;
            const rh = recentFor(data.recent.home, s.stat);
            const ra = recentFor(data.recent.away, s.stat);
            return (
              <div className="props__block" key={s.stat} role="rowgroup">
                <div className="props__row" role="row">
                  <span role="rowheader" className="props__label">{s.name}</span>
                  <span role="cell" className="numeral props__expected">{num(mh?.expected)}</span>
                  <span role="cell" className="numeral props__expected props__expected--total">{num(mt?.expected)}</span>
                  <span role="cell" className="numeral props__expected">{num(ma?.expected)}</span>
                </div>
                <div className="props__row props__row--recent" role="row">
                  <span role="rowheader" className="props__label props__label--sub">Son 5 maç ort.</span>
                  <span role="cell" className="numeral" title="Attığı / yediği (rakibe yaptırdığı)">
                    {num(rh?.for_last5)} <span className="props__muted">/ {num(rh?.against_last5)}</span>
                  </span>
                  <span role="cell" />
                  <span role="cell" className="numeral" title="Attığı / yediği (rakibe yaptırdığı)">
                    {num(ra?.for_last5)} <span className="props__muted">/ {num(ra?.against_last5)}</span>
                  </span>
                </div>
                <div className="props__row props__row--lines" role="row">
                  <span role="rowheader" className="props__label props__label--sub">Çizgiler</span>
                  <span role="cell"><LineChips market={mh} /></span>
                  <span role="cell"><LineChips market={mt} /></span>
                  <span role="cell"><LineChips market={ma} /></span>
                </div>
              </div>
            );
          }),
        )}
      </div>
      <p className="props__note">
        {data.note} Son 5 maç: kendi sayısı / rakibine verdiği. Koyu çizgiler modelin %70 ve üstü gördükleri (kart ve toplam kornerde güçlü işaret kullanılmaz).
      </p>
    </section>
  );
}
