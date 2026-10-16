/**
 * LiveStats Component
 * 
 * Displays side-by-side live statistics comparison for home/away teams.
 * Shows possession, shots, xG, passes, corners, etc.
 * Handles missing data gracefully with "—" indicators.
 */

import type { LiveStats as LiveStatsType } from '../../types/live';
import './LiveStats.css';

interface LiveStatsProps {
  /** Home team name */
  homeTeam: string;
  /** Away team name */
  awayTeam: string;
  /** Home team stats */
  homeStats?: LiveStatsType;
  /** Away team stats */
  awayStats?: LiveStatsType;
  /** Loading state */
  isLoading?: boolean;
}

interface StatRowProps {
  label: string;
  homeValue?: number | null;
  awayValue?: number | null;
  formatValue?: (value: number) => string;
  invertComparison?: boolean;
}

export default function LiveStats({
  homeStats,
  awayStats,
  isLoading = false
}: LiveStatsProps) {
  if (isLoading) {
    return (
      <div className="live-stats-container" aria-busy="true">
        <div className="live-stats-header">
          <div className="skeleton skeleton--header"></div>
        </div>
        <div className="live-stats-grid">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="skeleton skeleton--row"></div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="live-stats-container">
      <div className="live-stats-header">
        <h3 className="live-stats-title">Canlı İstatistikler</h3>
      </div>

      <div className="live-stats-grid">
        {/* Possession */}
        <StatRow
          label="Top Hakimiyeti"
          homeValue={homeStats?.possession}
          awayValue={awayStats?.possession}
          formatValue={(v) => `${v}%`}
        />

        {/* Expected Goals (xG) */}
        <StatRow
          label="Beklenen Gol (xG)"
          homeValue={homeStats?.xG}
          awayValue={awayStats?.xG}
          formatValue={(v) => v.toFixed(2)}
        />

        {/* Shots */}
        <StatRow
          label="Şutlar"
          homeValue={homeStats?.shots}
          awayValue={awayStats?.shots}
        />

        {/* Shots on Target */}
        <StatRow
          label="İsabetli Şutlar"
          homeValue={homeStats?.shotsOnTarget}
          awayValue={awayStats?.shotsOnTarget}
        />

        {/* Shots Inside Box */}
        {(homeStats?.shotsInsideBox !== undefined || awayStats?.shotsInsideBox !== undefined) && (
          <StatRow
            label="Ceza Sahası İçi Şut"
            homeValue={homeStats?.shotsInsideBox}
            awayValue={awayStats?.shotsInsideBox}
          />
        )}

        {/* Big Chances */}
        {(homeStats?.bigChances !== undefined || awayStats?.bigChances !== undefined) && (
          <StatRow
            label="Büyük Fırsatlar"
            homeValue={homeStats?.bigChances}
            awayValue={awayStats?.bigChances}
          />
        )}

        {/* Pass Accuracy */}
        {(homeStats?.passAccuracy !== undefined || awayStats?.passAccuracy !== undefined) && (
          <StatRow
            label="Pas İsabeti"
            homeValue={homeStats?.passAccuracy}
            awayValue={awayStats?.passAccuracy}
            formatValue={(v) => `${v}%`}
          />
        )}

        {/* Corners */}
        <StatRow
          label="Kornerler"
          homeValue={homeStats?.corners}
          awayValue={awayStats?.corners}
        />

        {/* Fouls */}
        <StatRow
          label="Fauller"
          homeValue={homeStats?.fouls}
          awayValue={awayStats?.fouls}
          invertComparison={true}
        />

        {/* Yellow Cards */}
        <StatRow
          label="Sarı Kartlar"
          homeValue={homeStats?.yellowCards}
          awayValue={awayStats?.yellowCards}
          invertComparison={true}
        />

        {/* Red Cards */}
        {(homeStats?.redCards !== undefined && homeStats.redCards > 0) || 
         (awayStats?.redCards !== undefined && awayStats.redCards > 0) ? (
          <StatRow
            label="Kırmızı Kartlar"
            homeValue={homeStats?.redCards}
            awayValue={awayStats?.redCards}
            invertComparison={true}
          />
        ) : null}

        {/* Offsides */}
        {(homeStats?.offsides !== undefined || awayStats?.offsides !== undefined) && (
          <StatRow
            label="Ofsaytlar"
            homeValue={homeStats?.offsides}
            awayValue={awayStats?.offsides}
          />
        )}
      </div>

      {/* No Stats Message */}
      {!homeStats && !awayStats && (
        <div className="live-stats-empty">
          <p className="live-stats-empty__text">
            Canlı istatistikler henüz mevcut değil
          </p>
        </div>
      )}
    </div>
  );
}

/**
 * StatRow Component - Single statistic comparison row
 */
function StatRow({
  label,
  homeValue,
  awayValue,
  formatValue = (v) => v.toString(),
  invertComparison = false
}: StatRowProps) {
  const homeDisplay = homeValue !== undefined && homeValue !== null ? formatValue(homeValue) : '—';
  const awayDisplay = awayValue !== undefined && awayValue !== null ? formatValue(awayValue) : '—';

  // Determine which side is leading
  let homeLead = false;
  let awayLead = false;

  if (
    homeValue !== undefined &&
    homeValue !== null &&
    awayValue !== undefined &&
    awayValue !== null
  ) {
    if (invertComparison) {
      homeLead = homeValue < awayValue;
      awayLead = awayValue < homeValue;
    } else {
      homeLead = homeValue > awayValue;
      awayLead = awayValue > homeValue;
    }
  }

  return (
    <div className="stat-row">
      <div className={`stat-row__value stat-row__value--home ${homeLead ? 'stat-row__value--lead' : ''}`}>
        {homeDisplay}
      </div>
      <div className="stat-row__label">{label}</div>
      <div className={`stat-row__value stat-row__value--away ${awayLead ? 'stat-row__value--lead' : ''}`}>
        {awayDisplay}
      </div>
    </div>
  );
}
