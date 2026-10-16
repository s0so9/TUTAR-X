/**
 * LiveTimeline Component
 * 
 * Displays match events in chronological order: goals, cards, subs, VAR.
 * Most recent events at top. Handles empty state gracefully.
 */

import type { LiveEvent, LiveEventType } from '../../types/live';
import './LiveTimeline.css';

interface LiveTimelineProps {
  /** Home team name */
  homeTeam: string;
  /** Away team name */
  awayTeam: string;
  /** Array of events */
  events: LiveEvent[];
  /** Loading state */
  isLoading?: boolean;
}

export default function LiveTimeline({
  homeTeam,
  awayTeam,
  events,
  isLoading = false
}: LiveTimelineProps) {
  if (isLoading) {
    return (
      <div className="live-timeline" aria-busy="true">
        <div className="live-timeline__header">
          <div className="skeleton skeleton--title"></div>
        </div>
        <div className="live-timeline__events">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="skeleton skeleton--event"></div>
          ))}
        </div>
      </div>
    );
  }

  // Sort events: most recent first
  const sortedEvents = [...events].sort((a, b) => {
    const aTotal = a.minute + (a.addedTime || 0);
    const bTotal = b.minute + (b.addedTime || 0);
    return bTotal - aTotal;
  });

  return (
    <div className="live-timeline">
      <div className="live-timeline__header">
        <h3 className="live-timeline__title">Maç Olayları</h3>
      </div>

      {sortedEvents.length === 0 ? (
        <div className="live-timeline__empty">
          <p className="empty-text">Henüz önemli olay kaydedilmedi</p>
        </div>
      ) : (
        <div className="live-timeline__events">
          {sortedEvents.map((event) => (
            <TimelineEvent
              key={event.eventId}
              event={event}
              homeTeam={homeTeam}
              awayTeam={awayTeam}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * TimelineEvent - Single event in timeline
 */
function TimelineEvent({
  event,
  homeTeam,
  awayTeam
}: {
  event: LiveEvent;
  homeTeam: string;
  awayTeam: string;
}) {
  const minute = event.addedTime ? `${event.minute}+${event.addedTime}'` : `${event.minute}'`;
  const { icon, label, bgColor } = getEventDisplay(event.type);
  const teamName = event.team === 'home' ? homeTeam : awayTeam;

  return (
    <div
      className={`timeline-event timeline-event--${event.team} ${
        event.isImportant ? 'timeline-event--important' : ''
      }`}
    >
      <div className="timeline-event__time">{minute}</div>

      <div
        className="timeline-event__icon"
        style={{ background: bgColor }}
        aria-label={label}
      >
        {icon}
      </div>

      <div className="timeline-event__content">
        <div className="timeline-event__type">{label}</div>

        {event.player && (
          <div className="timeline-event__player">
            {event.player.name}
            {event.player.shirtNumber && (
              <span className="timeline-event__number">#{event.player.shirtNumber}</span>
            )}
          </div>
        )}

        {event.secondaryPlayer && (
          <div className="timeline-event__secondary">
            {event.type === 'SUBSTITUTION' ? '↔ ' : ''}
            {event.secondaryPlayer.name}
            {event.secondaryPlayer.shirtNumber && (
              <span className="timeline-event__number">#{event.secondaryPlayer.shirtNumber}</span>
            )}
          </div>
        )}

        {event.description && (
          <div className="timeline-event__description">{event.description}</div>
        )}

        <div className="timeline-event__team">{teamName}</div>
      </div>
    </div>
  );
}

/**
 * Get event display properties
 */
function getEventDisplay(type: LiveEventType): {
  icon: string;
  label: string;
  bgColor: string;
} {
  const displays: Record<
    LiveEventType,
    { icon: string; label: string; bgColor: string }
  > = {
    GOAL: { icon: '⚽', label: 'Gol', bgColor: 'rgba(0, 255, 136, 0.2)' },
    GOAL_PENALTY: { icon: '⚽', label: 'Penaltı Golü', bgColor: 'rgba(0, 255, 136, 0.2)' },
    GOAL_OWN: { icon: '⚽', label: 'Kendi Kalesine', bgColor: 'rgba(239, 68, 68, 0.2)' },
    ASSIST: { icon: '👟', label: 'Asist', bgColor: 'rgba(59, 130, 246, 0.2)' },
    YELLOW_CARD: { icon: '🟨', label: 'Sarı Kart', bgColor: 'rgba(245, 158, 11, 0.2)' },
    RED_CARD: { icon: '🟥', label: 'Kırmızı Kart', bgColor: 'rgba(239, 68, 68, 0.2)' },
    SECOND_YELLOW: { icon: '🟨🟥', label: 'İkinci Sarı Kart', bgColor: 'rgba(239, 68, 68, 0.2)' },
    SUBSTITUTION: { icon: '🔄', label: 'Oyuncu Değişikliği', bgColor: 'rgba(113, 113, 122, 0.2)' },
    VAR_OVERTURNED: { icon: '📺', label: 'VAR İptali', bgColor: 'rgba(139, 92, 246, 0.2)' },
    VAR_CONFIRMED: { icon: '📺', label: 'VAR Onayı', bgColor: 'rgba(139, 92, 246, 0.2)' },
    PENALTY_MISSED: { icon: '❌', label: 'Penaltı Kaçtı', bgColor: 'rgba(239, 68, 68, 0.2)' },
    PENALTY_SAVED: { icon: '🧤', label: 'Penaltı Kurtarıldı', bgColor: 'rgba(59, 130, 246, 0.2)' },
    SHOT_ON_TARGET: { icon: '🎯', label: 'İsabetli Şut', bgColor: 'rgba(59, 130, 246, 0.1)' },
    SHOT_OFF_TARGET: { icon: '🔀', label: 'Dışarı Şut', bgColor: 'rgba(113, 113, 122, 0.1)' },
    SHOT_BLOCKED: { icon: '🛑', label: 'Bloke Şut', bgColor: 'rgba(239, 68, 68, 0.1)' },
    BIG_CHANCE_MISSED: { icon: '⚠️', label: 'Kaçan Büyük Fırsat', bgColor: 'rgba(245, 158, 11, 0.2)' }
  };

  return displays[type] || { icon: '•', label: type, bgColor: 'rgba(113, 113, 122, 0.1)' };
}
