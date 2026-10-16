/**
 * Live match centre on the match page: momentum strip, then Özet / Kadrolar /
 * İstatistikler / Şut haritası. Before kick-off it shows the line-ups only.
 * Every section the source did not send says "veri yok" with the reason the
 * endpoint gave; the freshness line says when the data was fetched and how
 * often it refreshes.
 */

import { useState, type KeyboardEvent } from 'react';
import { RefreshCw } from 'lucide-react';
import type { LiveCenterResponse } from '../../../types/liveCenter';
import type { LiveCenterLoadState } from '../../../hooks/useLiveCenter';
import { EventTimeline } from './EventTimeline';
import { LineupsPanel } from './LineupsPanel';
import { StatsPanel } from './StatsPanel';
import { ShotMap } from './ShotMap';
import { MomentumStrip } from './MomentumStrip';
import { hasKickedOff, missingReason } from './liveCenterModel';
import './LiveCenter.css';

export type LiveCenterTab = 'summary' | 'lineups' | 'stats' | 'shots';

const TAB_LABELS: Record<LiveCenterTab, string> = {
  summary: 'Özet',
  lineups: 'Kadrolar',
  stats: 'İstatistikler',
  shots: 'Şut haritası',
};

interface LiveCenterProps {
  data: LiveCenterResponse | null;
  state: LiveCenterLoadState;
  error: string | null;
  lastUpdated: Date | null;
  pollIntervalMs: number | null;
  paused: boolean;
  onRefresh: () => void;
  /** Display names used on the page header. */
  teams: { home: string; away: string };
}

function clock(d: Date): string {
  return d.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function cadenceText(ms: number | null, paused: boolean, data: LiveCenterResponse): string {
  if (paused && ms !== null) return 'sekme gizliyken duraklatıldı';
  if (ms === null) {
    if (data.status === 'FINISHED') return 'maç bitti, yenilenmiyor';
    return 'yenilenmiyor';
  }
  const s = Math.round(ms / 1000);
  return s >= 60 ? `${Math.round(s / 60)} dk'da bir yenilenir` : `${s} sn'de bir yenilenir`;
}

function MatchInfo({ data }: { data: LiveCenterResponse }) {
  const parts: string[] = [];
  if (data.venue) parts.push(`Stat: ${data.venue}`);
  if (data.referee) parts.push(`Hakem: ${data.referee}`);
  if (typeof data.attendance === 'number') parts.push(`Seyirci: ${data.attendance.toLocaleString('tr-TR')}`);
  if (parts.length === 0) return null;
  return <p className="lc-info">{parts.join(' · ')}</p>;
}

export function LiveCenter({ data, state, error, lastUpdated, pollIntervalMs, paused, onRefresh, teams }: LiveCenterProps) {
  const [chosen, setChosen] = useState<LiveCenterTab | null>(null);

  if (!data) {
    if (state === 'loading' || state === 'idle') {
      return (
        <section className="lc lc--state" aria-busy="true" aria-label="Canlı maç merkezi">
          <p className="lc-caption">Maç merkezi verileri yükleniyor</p>
        </section>
      );
    }
    if (state === 'error') {
      return (
        <section className="lc lc--state" aria-label="Canlı maç merkezi">
          <p className="lc-empty">Maç merkezi verileri alınamadı.</p>
          <button type="button" className="lc-refresh" onClick={onRefresh}>
            <RefreshCw size={13} strokeWidth={1.75} aria-hidden="true" /> Tekrar dene
          </button>
        </section>
      );
    }
    return null;
  }

  const started = hasKickedOff(data.status);
  const shots = Array.isArray(data.shotmap) && data.shotmap.length > 0 ? data.shotmap : null;
  const tabs: LiveCenterTab[] = started
    ? ['summary', 'lineups', 'stats', ...(shots ? (['shots'] as const) : [])]
    : ['lineups'];
  const tab: LiveCenterTab = chosen && tabs.includes(chosen) ? chosen : tabs[0];
  const homeLabel = data.teams?.home?.short_name || teams.home;
  const awayLabel = data.teams?.away?.short_name || teams.away;
  const shortTeams = { home: homeLabel, away: awayLabel };

  const fetchedAt = data.fetched_at ? new Date(data.fetched_at) : null;
  const stamp = fetchedAt && !Number.isNaN(fetchedAt.getTime()) ? fetchedAt : lastUpdated;

  const onTabKey = (ev: KeyboardEvent<HTMLButtonElement>) => {
    if (ev.key !== 'ArrowRight' && ev.key !== 'ArrowLeft') return;
    ev.preventDefault();
    const i = tabs.indexOf(tab);
    const next = tabs[(i + (ev.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    setChosen(next);
    document.getElementById(`lc-tab-${next}`)?.focus();
  };

  const momentum = started && Array.isArray(data.momentum) && data.momentum.length > 0 ? data.momentum : null;

  return (
    <section className="lc" aria-label={started ? 'Canlı maç merkezi' : 'Kadrolar'}>
      {momentum && <MomentumStrip points={momentum} events={data.events} teams={shortTeams} />}

      <div className="lc-bar">
        {tabs.length > 1 ? (
          <div className="lc-tabs" role="tablist" aria-label="Maç merkezi bölümleri">
            {tabs.map((t) => (
              <button
                key={t}
                id={`lc-tab-${t}`}
                type="button"
                role="tab"
                aria-selected={tab === t}
                aria-controls={`lc-panel-${t}`}
                tabIndex={tab === t ? 0 : -1}
                className={`lc-tab${tab === t ? ' lc-tab--on' : ''}`}
                onClick={() => setChosen(t)}
                onKeyDown={onTabKey}
              >
                {TAB_LABELS[t]}
              </button>
            ))}
          </div>
        ) : (
          <h2 className="lc-title">Kadrolar</h2>
        )}
        <p className="lc-fresh">
          {stamp && (
            <>
              Son güncelleme <time className="numeral" dateTime={stamp.toISOString()}>{clock(stamp)}</time>
              <span className="lc-fresh__sep">·</span>
            </>
          )}
          <span>{cadenceText(pollIntervalMs, paused, data)}</span>
          {error && (
            <>
              <span className="lc-fresh__sep">·</span>
              <span className="lc-fresh__error">{error}</span>
            </>
          )}
          <span className="lc-fresh__sep">·</span>
          <span>Kaynak: {data.provider === 'fotmob' ? 'FotMob' : data.provider}</span>
          <button type="button" className="lc-refresh" onClick={onRefresh} aria-label="Şimdi yenile" title="Şimdi yenile">
            <RefreshCw size={13} strokeWidth={1.75} aria-hidden="true" />
          </button>
        </p>
      </div>

      <div
        key={tab}
        className="lc-panel"
        id={`lc-panel-${tab}`}
        role={tabs.length > 1 ? 'tabpanel' : undefined}
        aria-labelledby={tabs.length > 1 ? `lc-tab-${tab}` : undefined}
      >
        {tab === 'summary' && (
          <>
            <EventTimeline
              events={data.events}
              status={data.status}
              teams={teams}
              missingReason={missingReason(data, 'events')}
            />
            <MatchInfo data={data} />
          </>
        )}
        {tab === 'lineups' && (
          <LineupsPanel
            lineups={data.lineups}
            teams={teams}
            missingReason={missingReason(data, 'lineups')}
            unavailableMissingReason={missingReason(data, 'unavailable')}
          />
        )}
        {tab === 'stats' && (
          <StatsPanel
            stats={data.stats}
            teams={shortTeams}
            missingReason={missingReason(data, 'stats')}
            halfMissingReason={{
              first_half: missingReason(data, 'first_half'),
              second_half: missingReason(data, 'second_half'),
            }}
          />
        )}
        {tab === 'shots' && shots && <ShotMap shots={shots} teams={shortTeams} />}
      </div>
    </section>
  );
}
