/**
 * ValueClassificationBadge
 *
 * Renders a backend value classification code as a Turkish badge.
 * MODEL_MARKET_CONFLICT is always a warning ("Model–piyasa çelişkisi") with an
 * explanatory tooltip; it is never styled as value.
 */

import { Badge } from '../ui';
import type { BadgeVariant } from '../ui';
import {
  MODEL_MARKET_CONFLICT_TOOLTIP,
  describeValueClassification,
  valueClassificationTone,
} from '../../utils/pickMarket';
import type { ValueClassificationTone } from '../../utils/pickMarket';

interface ValueClassificationBadgeProps {
  code: string;
  className?: string;
}

const TONE_TO_VARIANT: Record<ValueClassificationTone, BadgeVariant> = {
  value: 'success',
  warning: 'warning',
  negative: 'danger',
  neutral: 'neutral',
};

export default function ValueClassificationBadge({ code, className }: ValueClassificationBadgeProps) {
  const tone = valueClassificationTone(code);
  const label = describeValueClassification(code);
  const isConflict = tone === 'warning';

  return (
    <Badge
      variant={TONE_TO_VARIANT[tone]}
      className={`value-classification-badge value-classification-badge--${tone}${className ? ` ${className}` : ''}`}
      title={isConflict ? MODEL_MARKET_CONFLICT_TOOLTIP : undefined}
      ariaLabel={isConflict ? `${label}: ${MODEL_MARKET_CONFLICT_TOOLTIP}` : undefined}
    >
      {isConflict && <span aria-hidden="true">⚠</span>}
      {label}
    </Badge>
  );
}
