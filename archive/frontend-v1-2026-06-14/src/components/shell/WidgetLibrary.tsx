/**
 * WidgetLibrary — left sidebar that displays all available widgets grouped by category.
 * Acts as a widget palette for drag-and-drop into the workspace.
 *
 * Click a widget card to add it to the current workspace (alternative to drag).
 */

import * as React from 'react'
import { useState, useMemo } from 'react'
import { Search, Plus, GripVertical, ChevronRight } from 'lucide-react'
import { widgetRegistry } from '@/widgets/registry'
import { useWorkspaceStore } from '@/workspaces/store'
import { cn } from '@/lib/utils'
import type { WidgetCategory } from '@/widgets/Widget'

const CATEGORY_TABS: { id: WidgetCategory | 'all'; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'market', label: 'Market' },
  { id: 'scanner', label: 'Scanner' },
  { id: 'analytics', label: 'Analytics' },
  { id: 'chart', label: 'Chart' },
  { id: 'strategy', label: 'Strategy' },
  { id: 'portfolio', label: 'Portfolio' },
  { id: 'risk', label: 'Risk' },
  { id: 'options', label: 'Options' },
  { id: 'replay', label: 'Replay' },
  { id: 'alerts', label: 'Alerts' },
]

const CATEGORY_SECTIONS: { id: WidgetCategory; label: string }[] = [
  { id: 'market', label: 'Market Widgets' },
  { id: 'scanner', label: 'Scanner Widgets' },
  { id: 'analytics', label: 'Analytics Widgets' },
  { id: 'chart', label: 'Chart Widgets' },
  { id: 'portfolio', label: 'Trading Widgets' },
  { id: 'strategy', label: 'Strategy Widgets' },
  { id: 'replay', label: 'Replay Widgets' },
  { id: 'risk', label: 'Risk Widgets' },
  { id: 'options', label: 'Options Widgets' },
  { id: 'alerts', label: 'Alert Widgets' },
]

export function WidgetLibrary() {
  const addWidget = useWorkspaceStore((s) => s.addWidget)
  const workspaces = useWorkspaceStore((s) => s.workspaces)
  const currentWorkspaceId = useWorkspaceStore((s) => s.currentWorkspaceId)
  const [search, setSearch] = useState('')
  const [activeTab, setActiveTab] = useState<WidgetCategory | 'all'>('all')
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})

  const allWidgets = widgetRegistry.list()

  // Filter
  const filtered = useMemo(() => {
    return allWidgets.filter((m) => {
      if (activeTab !== 'all' && m.category !== activeTab) return false
      if (search && !m.name.toLowerCase().includes(search.toLowerCase()) && !m.description.toLowerCase().includes(search.toLowerCase())) return false
      return true
    })
  }, [allWidgets, search, activeTab])

  // Group by category for the "All" view
  const grouped = useMemo(() => {
    const out: Record<string, typeof allWidgets> = {}
    for (const m of filtered) {
      if (!out[m.category]) out[m.category] = []
      out[m.category].push(m)
    }
    return out
  }, [filtered])

  const handleAdd = (type: string) => {
    const ws = workspaces.find((w) => w.id === currentWorkspaceId)
    if (!ws) return
    const maxY = ws.widgets.reduce((m, w) => Math.max(m, w.layout.y + w.layout.h), 0)
    addWidget(currentWorkspaceId!, type, { x: 0, y: maxY })
  }

  const toggleSection = (id: string) => {
    setCollapsed((c) => ({ ...c, [id]: !c[id] }))
  }

  return (
    <aside className="w-60 flex flex-col bg-bg-1 border-r border-line flex-shrink-0 overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2.5 border-b border-line flex-shrink-0">
        <div className="flex items-center justify-between mb-1.5">
          <div className="text-2xs font-semibold uppercase tracking-wider text-fg-dim">Widget Library</div>
          <span className="text-2xs text-fg-dim">{allWidgets.length} widgets</span>
        </div>
        <div className="flex items-center gap-1.5 px-2 h-7 bg-bg-0 border border-line rounded">
          <Search className="h-3 w-3 text-fg-dim" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search widgets..."
            className="flex-1 bg-transparent border-0 outline-none text-xs placeholder:text-fg-dim"
          />
        </div>
      </div>

      {/* Category tabs */}
      <div className="px-2 py-1.5 border-b border-line flex-shrink-0 overflow-x-auto scrollbar-thin">
        <div className="flex items-center gap-0.5">
          {CATEGORY_TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={cn(
                'h-6 px-2 text-2xs font-medium rounded uppercase tracking-wider whitespace-nowrap',
                activeTab === t.id ? 'bg-bg-3 text-fg' : 'text-fg-muted hover:bg-bg-2',
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Widget list */}
      <div className="flex-1 overflow-y-auto py-2 scrollbar-thin">
        {activeTab === 'all' ? (
          <div className="space-y-2">
            {CATEGORY_SECTIONS.map((section) => {
              const widgets = grouped[section.id] || []
              if (widgets.length === 0) return null
              const isCollapsed = collapsed[section.id]
              return (
                <div key={section.id}>
                  <button
                    onClick={() => toggleSection(section.id)}
                    className="w-full flex items-center justify-between px-3 py-1 text-2xs font-semibold uppercase tracking-wider text-fg-dim hover:text-fg"
                  >
                    <span className="flex items-center gap-1">
                      <ChevronRight className={cn('h-2.5 w-2.5 transition-transform', !isCollapsed && 'rotate-90')} />
                      {section.label}
                    </span>
                    <span className="text-fg-dim">{widgets.length}</span>
                  </button>
                  {!isCollapsed && (
                    <div className="space-y-1 px-1.5">
                      {widgets.map((m) => {
                        const Icon = m.icon
                        return (
                          <button
                            key={m.type}
                            onClick={() => handleAdd(m.type)}
                            draggable
                            onDragStart={(e) => {
                              e.dataTransfer.setData('widget-type', m.type)
                              e.dataTransfer.effectAllowed = 'copy'
                            }}
                            className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-left hover:bg-bg-2 group transition-colors"
                            title={`Drag or click to add ${m.name}`}
                          >
                            <GripVertical className="h-3 w-3 text-fg-dim opacity-0 group-hover:opacity-100 cursor-grab" />
                            <div className="h-6 w-6 rounded bg-brand/15 flex items-center justify-center flex-shrink-0">
                              <Icon className="h-3 w-3 text-brand" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="text-xs font-medium truncate">{m.name}</div>
                            </div>
                            <Plus className="h-3 w-3 text-fg-dim opacity-0 group-hover:opacity-100" />
                          </button>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        ) : (
          <div className="space-y-1 px-1.5">
            {filtered.map((m) => {
              const Icon = m.icon
              return (
                <button
                  key={m.type}
                  onClick={() => handleAdd(m.type)}
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData('widget-type', m.type)
                    e.dataTransfer.effectAllowed = 'copy'
                  }}
                  className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-left hover:bg-bg-2 group transition-colors"
                  title={`Drag or click to add ${m.name}`}
                >
                  <GripVertical className="h-3 w-3 text-fg-dim opacity-0 group-hover:opacity-100 cursor-grab" />
                  <div className="h-6 w-6 rounded bg-brand/15 flex items-center justify-center flex-shrink-0">
                    <Icon className="h-3 w-3 text-brand" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium truncate">{m.name}</div>
                    <div className="text-2xs text-fg-dim truncate">{m.description}</div>
                  </div>
                </button>
              )
            })}
            {filtered.length === 0 && (
              <div className="text-center text-fg-dim text-xs py-6">No widgets found</div>
            )}
          </div>
        )}
      </div>

      {/* Footer: Create custom widget */}
      <div className="px-3 py-2 border-t border-line flex-shrink-0">
        <button className="w-full h-8 text-xs font-medium rounded bg-bg-2 hover:bg-bg-3 border border-dashed border-line text-fg-muted hover:text-fg flex items-center justify-center gap-1.5">
          <Plus className="h-3 w-3" /> Create Custom Widget
        </button>
      </div>
    </aside>
  )
}
