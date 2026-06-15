/**
 * WidgetGallery — modal for adding a new widget to the current workspace.
 *
 * Lists all available widget types grouped by category. Click a widget to
 * add it to the workspace (auto-placed in the first available spot).
 */

import * as React from 'react'
import { useState } from 'react'
import { X, Search, Plus } from 'lucide-react'
import { widgetRegistry } from '@/widgets/registry'
import { useWorkspaceStore } from './store'
import { cn } from '@/lib/utils'
import type { WidgetCategory } from '@/widgets/Widget'

interface WidgetGalleryProps {
  workspaceId: string
  onClose: () => void
}

const CATEGORIES: { id: WidgetCategory; label: string }[] = [
  { id: 'market', label: 'Market' },
  { id: 'chart', label: 'Charts' },
  { id: 'scanner', label: 'Scanner' },
  { id: 'analytics', label: 'Analytics' },
  { id: 'options', label: 'Options' },
  { id: 'strategy', label: 'Strategy' },
  { id: 'replay', label: 'Replay' },
  { id: 'portfolio', label: 'Portfolio' },
  { id: 'risk', label: 'Risk' },
  { id: 'alerts', label: 'Alerts' },
]

export function WidgetGallery({ workspaceId, onClose }: WidgetGalleryProps) {
  const addWidget = useWorkspaceStore((s) => s.addWidget)
  const [search, setSearch] = useState('')
  const [activeCategory, setActiveCategory] = useState<WidgetCategory | 'all'>('all')

  const handleAdd = (type: string) => {
    // Find a free spot in the grid (simple: place at y=Infinity so RGL puts it at the bottom)
    const ws = useWorkspaceStore.getState().workspaces.find((w) => w.id === workspaceId)
    if (!ws) return
    const maxY = ws.widgets.reduce((m, w) => Math.max(m, w.layout.y + w.layout.h), 0)
    addWidget(workspaceId, type, { x: 0, y: maxY })
    onClose()
  }

  const list = widgetRegistry.list().filter((m) => {
    if (activeCategory !== 'all' && m.category !== activeCategory) return false
    if (search && !m.name.toLowerCase().includes(search.toLowerCase()) && !m.description.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  return (
    <div className="fixed inset-0 z-50 bg-bg-0/80 backdrop-blur-sm flex items-center justify-center" onClick={onClose}>
      <div
        className="w-[760px] max-w-[95vw] max-h-[85vh] bg-bg-1 border border-line rounded-md shadow-2xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-4 py-3 border-b border-line flex items-center justify-between flex-shrink-0">
          <div>
            <div className="text-base font-semibold">Widget Gallery</div>
            <div className="text-2xs text-fg-dim">Click a widget to add it to your workspace</div>
          </div>
          <button onClick={onClose} className="h-7 w-7 rounded hover:bg-bg-3 text-fg-muted flex items-center justify-center">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Search */}
        <div className="px-4 py-2 border-b border-line flex-shrink-0">
          <div className="flex items-center gap-2 px-2.5 h-8 bg-bg-0 border border-line rounded">
            <Search className="h-3.5 w-3.5 text-fg-dim" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search widgets..."
              autoFocus
              className="flex-1 bg-transparent border-0 outline-none text-sm placeholder:text-fg-dim"
            />
          </div>
        </div>

        {/* Categories */}
        <div className="px-4 py-2 border-b border-line flex items-center gap-1 overflow-x-auto flex-shrink-0 scrollbar-thin">
          <button
            onClick={() => setActiveCategory('all')}
            className={cn(
              'h-7 px-2.5 text-2xs font-medium rounded uppercase tracking-wider whitespace-nowrap',
              activeCategory === 'all' ? 'bg-bg-3 text-fg' : 'text-fg-muted hover:bg-bg-2',
            )}
          >
            All
          </button>
          {CATEGORIES.map((c) => (
            <button
              key={c.id}
              onClick={() => setActiveCategory(c.id)}
              className={cn(
                'h-7 px-2.5 text-2xs font-medium rounded uppercase tracking-wider whitespace-nowrap',
                activeCategory === c.id ? 'bg-bg-3 text-fg' : 'text-fg-muted hover:bg-bg-2',
              )}
            >
              {c.label}
            </button>
          ))}
        </div>

        {/* Grid */}
        <div className="flex-1 overflow-y-auto p-4">
          {list.length === 0 ? (
            <div className="text-center text-fg-muted text-sm py-12">No widgets match your search.</div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {list.map((m) => {
                const Icon = m.icon
                return (
                  <button
                    key={m.type}
                    onClick={() => handleAdd(m.type)}
                    className="text-left p-3 bg-bg-2 hover:bg-bg-3 rounded border border-line hover:border-brand transition-colors"
                  >
                    <div className="flex items-center gap-2 mb-1.5">
                      <div className="h-7 w-7 rounded bg-brand/15 flex items-center justify-center flex-shrink-0">
                        <Icon className="h-3.5 w-3.5 text-brand" />
                      </div>
                      <div className="font-semibold text-sm truncate">{m.name}</div>
                    </div>
                    <div className="text-2xs text-fg-muted line-clamp-2 leading-relaxed">{m.description}</div>
                    <div className="mt-2 flex items-center gap-1 text-2xs text-fg-dim">
                      <span className="px-1.5 py-0.5 bg-bg-1 rounded">{m.defaultSize.w}×{m.defaultSize.h}</span>
                      <span className="uppercase tracking-wider">{m.category}</span>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-2.5 border-t border-line flex items-center justify-between flex-shrink-0">
          <div className="text-2xs text-fg-dim">
            {widgetRegistry.list().length} widgets available · {list.length} shown
          </div>
          <button onClick={onClose} className="h-7 px-3 text-xs font-medium rounded bg-bg-2 hover:bg-bg-3 text-fg-muted">
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
