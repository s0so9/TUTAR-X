/**
 * EmptyState - explicit "no data" message with optional action.
 */

import type { ReactNode } from 'react';
import './ui.css';

export interface EmptyStateAction {
  label: string;
  onClick: () => void;
}

export interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: EmptyStateAction;
  className?: string;
}

export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={`tx-empty-state${className ? ` ${className}` : ''}`}>
      {icon !== undefined && (
        <div className="tx-empty-state__icon" aria-hidden="true">
          {icon}
        </div>
      )}
      <p className="tx-empty-state__title">{title}</p>
      {description && <p className="tx-empty-state__description">{description}</p>}
      {action && (
        <button type="button" className="tx-empty-state__action" onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </div>
  );
}
