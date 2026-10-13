/**
 * BookmakerValueList
 *
 * Renders the outcomes of a bookmaker comparison that the backend flagged as
 * value, using ValueIndicator with the model edge (model - implied, positive =
 * value). Outcomes classified as MODEL_MARKET_CONFLICT are shown as a warning
 * badge instead and are never presented as value.
 */

import type { BookmakerComparisonResponse } from '../../api/types'
import ValueIndicator from '../common/ValueIndicator'
import ValueClassificationBadge from '../common/ValueClassificationBadge'
import {
  describeOutcomeLabel,
  isModelMarketConflict,
  modelEdgeFromImpliedEdge,
} from '../../utils/pickMarket'

interface BookmakerValueListProps {
  comparisons: BookmakerComparisonResponse[]
}

export default function BookmakerValueList({ comparisons }: BookmakerValueListProps) {
  const items = comparisons.filter(
    (c) => c.has_value_flag || isModelMarketConflict(c.value_classification)
  )

  if (items.length === 0) {
    return <span className="value-item value-item--none">Değer yok</span>
  }

  return (
    <>
      {items.map((comparison) => (
        <div key={comparison.label} className="value-item">
          <span className="value-item__label">{describeOutcomeLabel(comparison.label)}</span>
          {isModelMarketConflict(comparison.value_classification) ? (
            <ValueClassificationBadge code={comparison.value_classification as string} />
          ) : (
            <ValueIndicator value={modelEdgeFromImpliedEdge(comparison.edge_value)} />
          )}
        </div>
      ))}
    </>
  )
}
