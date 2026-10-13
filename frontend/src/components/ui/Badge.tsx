/**
 * Badge - small status / label pill.
 */

import type { ReactNode } from 'react';
import './ui.css';

export type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'live' | 'neutral';

export interface BadgeProps {
  variant?: BadgeVariant;
  children: ReactNode;
  className?: string;
  /** Optional accessible label when the visible text is abbreviated (e.g. "MS"). */
  ariaLabel?: string;
  /** Optional tooltip text (native title attribute). */
  title?: string;
}

export function Badge({ variant = 'neutral', children, className, ariaLabel, title }: BadgeProps) {
  return (
    <span
      className={`tx-badge tx-badge--${variant}${className ? ` ${className}` : ''}`}
      aria-label={ariaLabel}
      title={title}
    >
      {variant === 'live' && <span className="tx-badge__pulse" aria-hidden="true" />}
      {children}
    </span>
  );
}
