/**
 * Skeleton - loading placeholder block.
 */

import type { CSSProperties } from 'react';
import './ui.css';

export interface SkeletonProps {
  /** CSS width (number = px). Defaults to 100%. */
  width?: string | number;
  /** CSS height (number = px). Defaults to 1rem. */
  height?: string | number;
  /** CSS border radius (number = px). */
  radius?: string | number;
  className?: string;
  /** Screen reader text. */
  label?: string;
}

function toCssSize(value: string | number | undefined): string | undefined {
  if (value === undefined) return undefined;
  return typeof value === 'number' ? `${value}px` : value;
}

export function Skeleton({
  width = '100%',
  height = '1rem',
  radius,
  className,
  label = 'Yükleniyor…',
}: SkeletonProps) {
  const style: CSSProperties = {
    width: toCssSize(width),
    height: toCssSize(height),
    borderRadius: toCssSize(radius),
  };

  return (
    <div
      className={`tx-skeleton${className ? ` ${className}` : ''}`}
      style={style}
      role="status"
      aria-live="polite"
    >
      <span className="sr-only">{label}</span>
    </div>
  );
}
