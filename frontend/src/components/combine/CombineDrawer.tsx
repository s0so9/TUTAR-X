/**
 * CombineDrawer Component
 *
 * Kombine toggle + drawer on the match page. The body (CombineSlip) is shared
 * with the dashboard panel, so both show the same figures in the same format.
 * AI confidence NEVER enters odds calculations.
 * Side panel on desktop, bottom sheet on phones.
 */

import { useState } from 'react'
import { Layers, X } from 'lucide-react'
import type { CombineItem } from '../../hooks/useCombine'
import { CombineSlip } from './CombineSlip'
import './CombineDrawer.css'

interface CombineDrawerProps {
  /** Combine items */
  items: CombineItem[]
  /** Callback to remove item */
  onRemove: (matchId: string) => void
  /** Callback to clear all items */
  onClear: () => void
}

export default function CombineDrawer({
  items,
  onRemove,
  onClear
}: CombineDrawerProps) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <>
      <button
        type="button"
        className="combine-drawer-toggle"
        onClick={() => setIsOpen(!isOpen)}
        aria-label={isOpen ? 'Kombineyi kapat' : 'Kombineyi aç'}
        aria-expanded={isOpen}
      >
        <span className="combine-drawer-toggle__icon" aria-hidden="true">
          <Layers size={16} strokeWidth={1.75} />
        </span>
        <span className="combine-drawer-toggle__text">Kombine</span>
        {items.length > 0 && (
          <span className="combine-drawer-toggle__badge">{items.length}</span>
        )}
      </button>

      <aside
        className={`combine-drawer ${isOpen ? 'combine-drawer--open' : ''}`}
        aria-hidden={!isOpen}
        aria-label="Kombine"
      >
        <div className="combine-drawer__header">
          <h3 className="combine-drawer__title">
            Kombine<span className="combine-drawer__count">{items.length} seçim</span>
          </h3>
          <button
            type="button"
            className="combine-drawer__close-button"
            onClick={() => setIsOpen(false)}
            aria-label="Kapat"
          >
            <X size={18} strokeWidth={1.75} aria-hidden="true" />
          </button>
        </div>

        <div className="combine-drawer__content">
          {items.length === 0 ? (
            <p className="combine-drawer__empty-state">Henüz seçim eklenmedi.</p>
          ) : (
            <CombineSlip items={items} onRemove={onRemove} onClear={onClear} idPrefix="combine-drawer" />
          )}
        </div>
      </aside>

      {isOpen && (
        <div
          className="combine-drawer-backdrop"
          onClick={() => setIsOpen(false)}
          aria-hidden="true"
        />
      )}
    </>
  )
}
