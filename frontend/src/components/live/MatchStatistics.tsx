
import type { MatchStatisticsResponse } from '../../api/types';
import './MatchStatistics.css';

interface MatchStatisticsProps {
  homeStats: MatchStatisticsResponse | null;
  awayStats: MatchStatisticsResponse | null;
  homeTeam: string;
  awayTeam: string;
}

interface StatItem {
  label: string;
  homeValue: number | null | undefined;
  awayValue: number | null | undefined;
  formatAsPercentage?: boolean;
  precision?: number;
}

export function MatchStatistics({ homeStats, awayStats, homeTeam, awayTeam }: MatchStatisticsProps) {
  if (!homeStats && !awayStats) {
    return (
      <div className="match-statistics">
        <div className="match-statistics__header">
          <h3>Maç İstatistikleri</h3>
        </div>
        <div className="match-statistics__empty">
          İstatistik verisi mevcut değil
        </div>
      </div>
    );
  }

  // Helper function to format percentage
  const formatValue = (value: number | null, asPercentage: boolean = false, precision: number = 1): string => {
    if (value === null) return '-';
    if (asPercentage) return `${value.toFixed(precision)}%`;
    return value.toFixed(precision);
  };

  // Helper function to create percentage bar
  const getPercentageWidth = (homeValue: number | null, awayValue: number | null, isHome: boolean): number => {
    if (homeValue === null && awayValue === null) return 0;
    if (homeValue === null) return isHome ? 0 : 100;
    if (awayValue === null) return isHome ? 100 : 0;
    
    const total = homeValue + awayValue;
    if (total === 0) return 50; // Equal when both are 0
    
    return isHome ? (homeValue / total) * 100 : (awayValue / total) * 100;
  };

  // Define statistics to display
  const stats: StatItem[] = [
    {
      label: 'Top Kontrolü',
      homeValue: homeStats?.possession_percentage,
      awayValue: awayStats?.possession_percentage,
      formatAsPercentage: true,
      precision: 1
    },
    {
      label: 'Toplam Şut',
      homeValue: homeStats?.shots_total,
      awayValue: awayStats?.shots_total,
      precision: 0
    },
    {
      label: 'İsabetli Şut',
      homeValue: homeStats?.shots_on_target,
      awayValue: awayStats?.shots_on_target,
      precision: 0
    },
    {
      label: 'xG (Beklenen Gol)',
      homeValue: homeStats?.xg,
      awayValue: awayStats?.xg,
      precision: 2
    },
    {
      label: 'Pas İsabet Oranı',
      homeValue: homeStats?.pass_accuracy,
      awayValue: awayStats?.pass_accuracy,
      formatAsPercentage: true,
      precision: 1
    },
    {
      label: 'Toplam Pas',
      homeValue: homeStats?.passes_attempted,
      awayValue: awayStats?.passes_attempted,
      precision: 0
    },
    {
      label: 'Korner',
      homeValue: homeStats?.corners,
      awayValue: awayStats?.corners,
      precision: 0
    },
    {
      label: 'Ofsayt',
      homeValue: homeStats?.offsides,
      awayValue: awayStats?.offsides,
      precision: 0
    },
    {
      label: 'Sarı Kart',
      homeValue: homeStats?.yellow_cards,
      awayValue: awayStats?.yellow_cards,
      precision: 0
    },
    {
      label: 'Kırmızı Kart',
      homeValue: homeStats?.red_cards,
      awayValue: awayStats?.red_cards,
      precision: 0
    },
    {
      label: 'Faul',
      homeValue: homeStats?.fouls_committed,
      awayValue: awayStats?.fouls_committed,
      precision: 0
    },
    {
      label: 'Müdahale',
      homeValue: homeStats?.tackles,
      awayValue: awayStats?.tackles,
      precision: 0
    }
  ];

  return (
    <div className="match-statistics">
      <div className="match-statistics__header">
        <h3>Maç İstatistikleri</h3>
        <div className="match-statistics__teams">
          <span className="match-statistics__team match-statistics__team--home">
            {homeTeam}
          </span>
          <span className="match-statistics__team match-statistics__team--away">
            {awayTeam}
          </span>
        </div>
      </div>

      <div className="match-statistics__content">
        {stats.map((stat, index) => {
          // Skip stats where both values are null
          if (stat.homeValue === null && stat.awayValue === null) {
            return null;
          }

          const homeWidth = getPercentageWidth(
            stat.homeValue as number, 
            stat.awayValue as number, 
            true
          );
          const awayWidth = getPercentageWidth(
            stat.homeValue as number, 
            stat.awayValue as number, 
            false
          );

          return (
            <div key={index} className="match-statistics__row">
              <div className="match-statistics__values">
                <span className="match-statistics__value match-statistics__value--home">
                  {formatValue(
                    stat.homeValue as number, 
                    stat.formatAsPercentage, 
                    stat.precision
                  )}
                </span>
                <span className="match-statistics__label">
                  {stat.label}
                </span>
                <span className="match-statistics__value match-statistics__value--away">
                  {formatValue(
                    stat.awayValue as number, 
                    stat.formatAsPercentage, 
                    stat.precision
                  )}
                </span>
              </div>
              
              {/* Visual bar for comparison */}
              {!stat.formatAsPercentage && stat.homeValue !== null && stat.awayValue !== null && (
                <div className="match-statistics__bar">
                  <div 
                    className="match-statistics__bar-home"
                    style={{ width: `${homeWidth}%` }}
                  />
                  <div 
                    className="match-statistics__bar-away"
                    style={{ width: `${awayWidth}%` }}
                  />
                </div>
              )}
              
              {/* For percentage stats, show the actual percentage bar */}
              {stat.formatAsPercentage && (
                <div className="match-statistics__bar">
                  <div 
                    className="match-statistics__bar-home"
                    style={{ width: `${stat.homeValue || 0}%` }}
                  />
                  <div 
                    className="match-statistics__bar-away"
                    style={{ width: `${stat.awayValue || 0}%` }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default MatchStatistics;