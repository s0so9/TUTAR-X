/**
 * Small inline glyphs for match events. Monochrome (currentColor) except the
 * cards, whose colour is the information.
 */

interface GlyphProps {
  size?: number;
  className?: string;
}

export function BallGlyph({ size = 14, className }: GlyphProps) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <circle cx="8" cy="8" r="6.6" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <path d="M8 4.9 10.9 7 9.8 10.4H6.2L5.1 7Z" fill="currentColor" />
      <path d="M8 4.9V1.6M10.9 7l3-1M9.8 10.4l1.9 2.8M6.2 10.4l-1.9 2.8M5.1 7l-3-1" stroke="currentColor" strokeWidth="1" />
    </svg>
  );
}

export function MissedPenaltyGlyph({ size = 14, className }: GlyphProps) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <circle cx="8" cy="8" r="6.6" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <path d="M3.4 12.6 12.6 3.4" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

export function CardGlyph({ tone, size = 14, className }: GlyphProps & { tone: 'yellow' | 'red' | 'second' }) {
  const w = size * 0.62;
  const h = size;
  if (tone === 'second') {
    return (
      <svg className={className} width={size} height={h} viewBox="0 0 16 16" aria-hidden="true" focusable="false">
        <rect x="1.5" y="1" width="8" height="12" rx="1.2" className="glyph-card glyph-card--yellow" />
        <rect x="6.5" y="3" width="8" height="12" rx="1.2" className="glyph-card glyph-card--red" />
      </svg>
    );
  }
  return (
    <svg className={className} width={w} height={h} viewBox="0 0 10 16" aria-hidden="true" focusable="false">
      <rect x="0.5" y="0.5" width="9" height="15" rx="1.4" className={`glyph-card glyph-card--${tone}`} />
    </svg>
  );
}

export function SubGlyph({ direction, size = 12, className }: GlyphProps & { direction: 'in' | 'out' }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 12 12" aria-hidden="true" focusable="false">
      {direction === 'in' ? (
        <path d="M6 10.5V2M2.5 5.5 6 2l3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      ) : (
        <path d="M6 1.5V10M2.5 6.5 6 10l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      )}
    </svg>
  );
}

export function VarGlyph({ size = 14, className }: GlyphProps) {
  return (
    <svg className={className} width={size * 1.5} height={size} viewBox="0 0 24 16" aria-hidden="true" focusable="false">
      <rect x="0.75" y="0.75" width="22.5" height="14.5" rx="2" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <text x="12" y="11.4" textAnchor="middle" fontSize="8.5" fontWeight="700" fill="currentColor" fontFamily="inherit">
        VAR
      </text>
    </svg>
  );
}
