/**
 * PropertiesPanel — right sidebar that shows properties of the currently
 * selected widget and the workspace itself.
 *
 * Tabs:
 *   - Style: visual options, hide/show, remove
 *   - Data: data source / refresh
 *   - Events: triggers & actions
 *   - Workspace: workspace-level properties + layout preview
 */

import * as React from 'react'
import { useState } from 'react'
import { useWorkspaceStore } from '@/workspaces/store'
import { widgetRegistry } from '@/widgets/registry'
import { cn } from '@/lib/utils'
import { Trash2, RefreshCw, X, LayoutGrid, Settings, Database, Zap, Save, RotateCcw, Eye, EyeOff, Copy } from 'lucide-react'
import { Distribution } from '@/components/ui/Progress'

interface PropertiesPanelProps {
  selectedWidgetId?: string | null
  onSelectWidget?: (id: string | null) => void
}

export function PropertiesPanel({ selectedWidgetId, onSelectWidget }: PropertiesPanelProps) {
  const workspace = useWorkspaceStore((s) => s.workspaces.find((w) => w.id === s.currentWorkspaceId))
  const updateWidgetConfig = useWorkspaceStore((s) => s.updateWidgetConfig)
  const removeWidget = useWorkspaceStore((s) => s.removeWidget)
  const toggleWidgetHidden = useWorkspaceStore((s) => s.toggleWidgetHidden)
  const renameWorkspace = useWorkspaceStore((s) => s.renameWorkspace)
  const [tab, setTab] = useState<'style' | 'data' | 'events' | 'workspace'>('style')

  const selectedWidget = selectedWidgetId ? workspace?.widgets.find((w) => w.id === selectedWidgetId) : null
  const selectedManifest = selectedWidget ? widgetRegistry.get(selectedWidget.type) : null

  const TABS = [
    { id: 'style' as const, label: 'Style', icon: Settings },
    { id: 'data' as const, label: 'Data', icon: Database },
    { id: 'events' as const, label: 'Events', icon: Zap },
    { id: 'workspace' as const, label: 'Workspace', icon: LayoutGrid },
  ]

  return (
    <aside className="w-72 flex flex-col bg-bg-1 border-l border-line flex-shrink-0 overflow-hidden">
      {/* Tabs */}
      <div className="flex items-center border-b border-line flex-shrink-0">
        {TABS.map((t) => {
          const Icon = t.icon
          const active = tab === t.id
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                'flex-1 h-9 text-2xs font-medium uppercase tracking-wider flex items-center justify-center gap-1.5 transition-colors',
                active ? 'text-fg border-b-2 border-brand bg-bg-2/40' : 'text-fg-muted hover:text-fg',
              )}
            >
              <Icon className="h-3 w-3" />
              {t.label}
            </button>
          )
        })}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {tab !== 'workspace' && !selectedWidget && (
          <div className="p-6 text-center">
            <div className="h-12 w-12 mx-auto rounded-full bg-bg-2 border border-line flex items-center justify-center mb-3">
              <Settings className="h-5 w-5 text-fg-dim" />
            </div>
            <div className="text-2xs text-fg-dim uppercase tracking-wider mb-1.5">No Widget Selected</div>
            <div className="text-xs text-fg-muted leading-relaxed">
              Click on a widget in the workspace to edit its properties. Drag any widget by its title bar to move it, or resize from the bottom-right corner.
            </div>
          </div>
        )}

        {tab !== 'workspace' && selectedWidget && selectedManifest && (
          <div className="p-3 space-y-3">
            {/* Widget header */}
            <div className="flex items-start gap-2 pb-2 border-b border-line">
              <div className="h-9 w-9 rounded bg-brand/15 flex items-center justify-center flex-shrink-0">
                <selectedManifest.icon className="h-4 w-4 text-brand" />
              </div>
              <div className="flex-1 min-w-0">
                <input
                  defaultValue={(selectedWidget.config as any).title || selectedManifest.name}
                  onBlur={(e) => updateWidgetConfig(workspace!.id, selectedWidget.id, { title: e.target.value })}
                  className="w-full bg-transparent border-0 outline-none text-sm font-semibold text-fg p-0 focus:ring-0"
                />
                <div className="text-2xs text-fg-dim truncate font-mono">{selectedManifest.type}</div>
              </div>
              {onSelectWidget && (
                <button
                  onClick={() => onSelectWidget(null)}
                  className="h-6 w-6 rounded text-fg-dim hover:text-fg hover:bg-bg-2 flex items-center justify-center flex-shrink-0"
                  title="Deselect"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            {tab === 'style' && (
              <div className="space-y-3">
                <div>
                  <label className="text-2xs text-fg-dim uppercase tracking-wider">Title</label>
                  <input
                    defaultValue={(selectedWidget.config as any).title || ''}
                    onBlur={(e) => updateWidgetConfig(workspace!.id, selectedWidget.id, { title: e.target.value })}
                    placeholder={selectedManifest.name}
                    className="w-full h-7 bg-bg-0 border border-line rounded px-2 text-sm mt-1"
                  />
                </div>
                <div className="grid grid-cols-2 gap-1.5">
                  <div>
                    <label className="text-2xs text-fg-dim uppercase tracking-wider">Width (cols)</label>
                    <div className="h-7 mt-1 px-2 bg-bg-0 border border-line rounded flex items-center gap-1">
                      <input
                        type="number"
                        min={1}
                        max={12}
                        defaultValue={selectedWidget.layout.w}
                        onBlur={(e) => {
                          const w = Math.max(1, Math.min(12, +e.target.value))
                          useWorkspaceStore.getState().updateWidgetLayout(workspace!.id, [
                            { i: selectedWidget.id, x: selectedWidget.layout.x, y: selectedWidget.layout.y, w, h: selectedWidget.layout.h },
                          ])
                        }}
                        className="flex-1 bg-transparent border-0 outline-none text-sm num"
                      />
                      <span className="text-2xs text-fg-dim">/12</span>
                    </div>
                  </div>
                  <div>
                    <label className="text-2xs text-fg-dim uppercase tracking-wider">Height (rows)</label>
                    <div className="h-7 mt-1 px-2 bg-bg-0 border border-line rounded flex items-center gap-1">
                      <input
                        type="number"
                        min={2}
                        max={20}
                        defaultValue={selectedWidget.layout.h}
                        onBlur={(e) => {
                          const h = Math.max(2, Math.min(20, +e.target.value))
                          useWorkspaceStore.getState().updateWidgetLayout(workspace!.id, [
                            { i: selectedWidget.id, x: selectedWidget.layout.x, y: selectedWidget.layout.y, w: selectedWidget.layout.w, h },
                          ])
                        }}
                        className="flex-1 bg-transparent border-0 outline-none text-sm num"
                      />
                    </div>
                  </div>
                </div>
                <div>
                  <label className="text-2xs text-fg-dim uppercase tracking-wider">Show Header</label>
                  <div className="h-7 mt-1 bg-bg-0 border border-line rounded flex items-center px-2">
                    <span className="text-xs">Visible</span>
                    <span className="ml-auto h-4 w-7 rounded-full bg-brand relative cursor-pointer">
                      <span className="absolute right-0.5 top-0.5 h-3 w-3 rounded-full bg-white" />
                    </span>
                  </div>
                </div>
                <div>
                  <label className="text-2xs text-fg-dim uppercase tracking-wider">Show Controls</label>
                  <div className="h-7 mt-1 bg-bg-0 border border-line rounded flex items-center px-2">
                    <span className="text-xs">Visible</span>
                    <span className="ml-auto h-4 w-7 rounded-full bg-brand relative cursor-pointer">
                      <span className="absolute right-0.5 top-0.5 h-3 w-3 rounded-full bg-white" />
                    </span>
                  </div>
                </div>
                <div>
                  <label className="text-2xs text-fg-dim uppercase tracking-wider">Theme</label>
                  <div className="grid grid-cols-3 gap-1.5 mt-1">
                    {['Default', 'Compact', 'Detailed'].map((t, i) => (
                      <button
                        key={t}
                        className={cn(
                          'h-7 rounded text-2xs font-medium',
                          i === 0 ? 'bg-brand text-white' : 'bg-bg-2 text-fg-muted hover:bg-bg-3',
                        )}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="pt-2 border-t border-line space-y-1.5">
                  <button
                    onClick={() => toggleWidgetHidden(workspace!.id, selectedWidget.id)}
                    className="w-full h-8 text-xs font-medium rounded bg-bg-2 hover:bg-bg-3 border border-line text-fg flex items-center justify-center gap-1.5"
                  >
                    <EyeOff className="h-3.5 w-3.5" /> Hide Widget
                  </button>
                  <button
                    onClick={() => {
                      const manifest = selectedManifest
                      const newInstance = useWorkspaceStore.getState().addWidget(workspace!.id, manifest.type, { x: 0, y: 999 })
                      if (newInstance) onSelectWidget?.(newInstance)
                    }}
                    className="w-full h-8 text-xs font-medium rounded bg-bg-2 hover:bg-bg-3 border border-line text-fg flex items-center justify-center gap-1.5"
                  >
                    <Copy className="h-3.5 w-3.5" /> Duplicate Widget
                  </button>
                  <button
                    onClick={() => {
                      if (workspace && selectedWidget) {
                        removeWidget(workspace.id, selectedWidget.id)
                        onSelectWidget?.(null)
                      }
                    }}
                    className="w-full h-8 text-xs font-medium rounded bg-bearish/15 text-bearish border border-bearish/30 hover:bg-bearish/25 flex items-center justify-center gap-1.5"
                  >
                    <Trash2 className="h-3.5 w-3.5" /> Remove Widget
                  </button>
                </div>
              </div>
            )}

            {tab === 'data' && (
              <div className="space-y-3">
                <div>
                  <label className="text-2xs text-fg-dim uppercase tracking-wider">Data Source</label>
                  <div className="mt-1 px-2.5 h-8 bg-bg-0 border border-line rounded flex items-center">
                    <Database className="h-3.5 w-3.5 text-fg-dim" />
                    <span className="ml-2 text-xs flex-1">Market Data API</span>
                    <span className="text-2xs text-fg-dim">›</span>
                  </div>
                </div>
                <div>
                  <label className="text-2xs text-fg-dim uppercase tracking-wider">Refresh Interval</label>
                  <select className="w-full h-7 bg-bg-0 border border-line rounded px-2 text-sm mt-1">
                    <option>Real-time (1s)</option>
                    <option>Fast (5s)</option>
                    <option>Normal (30s)</option>
                    <option>Slow (5m)</option>
                    <option>Manual only</option>
                  </select>
                </div>
                <div>
                  <label className="text-2xs text-fg-dim uppercase tracking-wider">Auto Refresh</label>
                  <div className="h-7 mt-1 bg-bg-0 border border-line rounded flex items-center px-2">
                    <span className="text-xs">Enabled</span>
                    <span className="ml-auto h-4 w-7 rounded-full bg-brand relative cursor-pointer">
                      <span className="absolute right-0.5 top-0.5 h-3 w-3 rounded-full bg-white" />
                    </span>
                  </div>
                </div>
                {(selectedWidget.config as any).symbol !== undefined && (
                  <div>
                    <label className="text-2xs text-fg-dim uppercase tracking-wider">Symbol</label>
                    <input
                      defaultValue={(selectedWidget.config as any).symbol || ''}
                      onBlur={(e) => updateWidgetConfig(workspace!.id, selectedWidget.id, { symbol: e.target.value.toUpperCase() })}
                      className="w-full h-7 bg-bg-0 border border-line rounded px-2 text-sm font-mono mt-1"
                    />
                  </div>
                )}
                <div className="flex gap-2 pt-2">
                  <button className="flex-1 h-8 text-xs font-medium rounded bg-bg-2 hover:bg-bg-3 border border-line flex items-center justify-center gap-1.5">
                    <RefreshCw className="h-3 w-3" /> Refresh Now
                  </button>
                </div>
              </div>
            )}

            {tab === 'events' && (
              <div className="space-y-3">
                <div>
                  <label className="text-2xs text-fg-dim uppercase tracking-wider">On Click</label>
                  <select className="w-full h-7 bg-bg-0 border border-line rounded px-2 text-sm mt-1">
                    <option>Select widget</option>
                    <option>Open chart</option>
                    <option>Open order ticket</option>
                    <option>Run scan</option>
                    <option>Custom action...</option>
                  </select>
                </div>
                <div>
                  <label className="text-2xs text-fg-dim uppercase tracking-wider">On Signal</label>
                  <select className="w-full h-7 bg-bg-0 border border-line rounded px-2 text-sm mt-1">
                    <option>Highlight</option>
                    <option>Show alert</option>
                    <option>Send notification</option>
                    <option>Custom action...</option>
                  </select>
                </div>
                <div>
                  <label className="text-2xs text-fg-dim uppercase tracking-wider">Webhook URL</label>
                  <input
                    placeholder="https://..."
                    className="w-full h-7 bg-bg-0 border border-line rounded px-2 text-xs font-mono mt-1"
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {tab === 'workspace' && workspace && (
          <div className="p-3 space-y-3">
            <div>
              <div className="text-2xs text-fg-dim uppercase tracking-wider mb-2">Widget Distribution</div>
              <div className="flex items-center gap-3">
                <Distribution
                  data={[
                    { label: 'Market', value: workspace.widgets.filter((w) => !w.hidden && widgetRegistry.get(w.type)?.category === 'market').length, color: '#3b82f6' },
                    { label: 'Chart', value: workspace.widgets.filter((w) => !w.hidden && widgetRegistry.get(w.type)?.category === 'chart').length, color: '#10b981' },
                    { label: 'Scanner', value: workspace.widgets.filter((w) => !w.hidden && widgetRegistry.get(w.type)?.category === 'scanner').length, color: '#f59e0b' },
                    { label: 'Analytics', value: workspace.widgets.filter((w) => !w.hidden && widgetRegistry.get(w.type)?.category === 'analytics').length, color: '#a855f7' },
                    { label: 'Other', value: workspace.widgets.filter((w) => !w.hidden && !['market', 'chart', 'scanner', 'analytics'].includes(widgetRegistry.get(w.type)?.category || '')).length, color: '#6b7280' },
                  ].filter((d) => d.value > 0)}
                  size={90}
                  thickness={14}
                  centerValue={String(workspace.widgets.filter((w) => !w.hidden).length)}
                  centerLabel="VISIBLE"
                />
                <div className="flex-1 space-y-1 text-2xs">
                  {[
                    { label: 'Market', value: workspace.widgets.filter((w) => !w.hidden && widgetRegistry.get(w.type)?.category === 'market').length, color: '#3b82f6' },
                    { label: 'Chart', value: workspace.widgets.filter((w) => !w.hidden && widgetRegistry.get(w.type)?.category === 'chart').length, color: '#10b981' },
                    { label: 'Scanner', value: workspace.widgets.filter((w) => !w.hidden && widgetRegistry.get(w.type)?.category === 'scanner').length, color: '#f59e0b' },
                    { label: 'Other', value: workspace.widgets.filter((w) => !w.hidden && !['market', 'chart', 'scanner'].includes(widgetRegistry.get(w.type)?.category || '')).length, color: '#a855f7' },
                  ].map((r) => (
                    <div key={r.label} className="flex items-center gap-1.5">
                      <div className="h-2 w-2 rounded" style={{ background: r.color }} />
                      <span className="flex-1 text-fg-muted">{r.label}</span>
                      <span className="font-mono num">{r.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div>
              <div className="text-2xs text-fg-dim uppercase tracking-wider mb-1.5">Layout Preview</div>
              <div className="aspect-[4/3] bg-bg-0 border border-line rounded p-1 relative">
                <svg viewBox="0 0 100 75" className="w-full h-full">
                  {workspace.widgets.filter((w) => !w.hidden).map((w, i) => {
                    const colors = ['#3b82f6', '#10b981', '#f59e0b', '#a855f7', '#ec4899', '#06b6d4']
                    const x = (w.layout.x / 12) * 100
                    const y = (w.layout.y / 20) * 75
                    const widthPct = (w.layout.w / 12) * 100
                    const heightPct = (w.layout.h / 20) * 75
                    return (
                      <rect
                        key={w.id}
                        x={x}
                        y={y}
                        width={widthPct}
                        height={heightPct}
                        fill={colors[i % colors.length]}
                        fillOpacity={0.25}
                        stroke={colors[i % colors.length]}
                        strokeOpacity={0.6}
                        strokeWidth={0.4}
                        rx={0.5}
                      />
                    )
                  })}
                </svg>
              </div>
            </div>

            <div>
              <div className="text-2xs text-fg-dim uppercase tracking-wider mb-1.5">Workspace Properties</div>
              <div className="space-y-2">
                <div>
                  <label className="text-2xs text-fg-dim uppercase tracking-wider">Workspace Name</label>
                  <input
                    defaultValue={workspace.name}
                    onBlur={(e) => e.target.value.trim() && renameWorkspace(workspace.id, e.target.value.trim())}
                    className="w-full h-7 bg-bg-0 border border-line rounded px-2 text-sm font-medium mt-1"
                  />
                </div>
                <div>
                  <label className="text-2xs text-fg-dim uppercase tracking-wider">Columns</label>
                  <div className="flex items-center gap-2 mt-1">
                    <input type="range" min={6} max={24} defaultValue={12} className="flex-1 accent-brand" />
                    <span className="text-2xs font-mono num w-6 text-right">12</span>
                  </div>
                </div>
                <div>
                  <label className="text-2xs text-fg-dim uppercase tracking-wider">Allow Drag & Resize</label>
                  <div className="h-7 mt-1 bg-bg-0 border border-line rounded flex items-center px-2">
                    <span className="text-xs">Always on</span>
                    <span className="ml-auto h-4 w-7 rounded-full bg-brand relative cursor-pointer">
                      <span className="absolute right-0.5 top-0.5 h-3 w-3 rounded-full bg-white" />
                    </span>
                  </div>
                </div>
                <div>
                  <label className="text-2xs text-fg-dim uppercase tracking-wider">Snap to Grid</label>
                  <div className="h-7 mt-1 bg-bg-0 border border-line rounded flex items-center px-2">
                    <span className="text-xs">Enabled</span>
                    <span className="ml-auto h-4 w-7 rounded-full bg-brand relative cursor-pointer">
                      <span className="absolute right-0.5 top-0.5 h-3 w-3 rounded-full bg-white" />
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex gap-2 pt-2">
              <button className="flex-1 h-8 text-xs font-medium rounded bg-brand text-white hover:bg-brand-600 flex items-center justify-center gap-1.5">
                <Save className="h-3.5 w-3.5" /> Save Workspace
              </button>
              <button className="flex-1 h-8 text-xs font-medium rounded bg-bg-2 hover:bg-bg-3 border border-line flex items-center justify-center gap-1.5">
                <RotateCcw className="h-3.5 w-3.5" /> Reset Layout
              </button>
            </div>
          </div>
        )}
      </div>
    </aside>
  )
}
