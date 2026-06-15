/**
 * WorkspaceCanvas — the main grid that hosts widgets.
 *
 * Professional UX:
 *   - Widgets are ALWAYS draggable and resizable (no "Edit mode" gate)
 *   - Drag handle is always visible in the title bar
 *   - Resize handle is always visible at the bottom-right corner
 *   - Click to select (Properties Panel updates)
 *   - Hide button collapses widget to a chip (lives in Hidden Tray)
 *   - Hidden Tray shows all hidden widgets with one-click restore
 *   - Drop target accepts widgets from the Widget Library
 *
 * Layout engine: react-grid-layout (v2.x)
 */

import * as React from 'react'
import { Responsive, useContainerWidth } from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'
import { useWorkspaceStore } from './store'
import { widgetRegistry } from '@/widgets/registry'
import { cn } from '@/lib/utils'
import { Plus, Edit3, Check, Maximize2, Minimize2, Eye, EyeOff, X, Settings, GripVertical } from 'lucide-react'
import { useState, useRef } from 'react'
import { WidgetGallery } from './WidgetGallery'

interface WorkspaceCanvasProps {
  selectedWidgetId?: string | null
  onSelectWidget?: (id: string | null) => void
}

export function WorkspaceCanvas({ selectedWidgetId, onSelectWidget }: WorkspaceCanvasProps) {
  const currentWorkspace = useWorkspaceStore((s) => s.workspaces.find((w) => w.id === s.currentWorkspaceId))
  const updateWidgetLayout = useWorkspaceStore((s) => s.updateWidgetLayout)
  const removeWidget = useWorkspaceStore((s) => s.removeWidget)
  const toggleWidgetHidden = useWorkspaceStore((s) => s.toggleWidgetHidden)
  const showAllWidgets = useWorkspaceStore((s) => s.showAllWidgets)
  const addWidget = useWorkspaceStore((s) => s.addWidget)
  const [galleryOpen, setGalleryOpen] = useState(false)
  const [fullscreen, setFullscreen] = useState(false)
  const [editingMode, setEditingMode] = useState(false)
  const [configWidget, setConfigWidget] = useState<string | null>(null)
  const [showHiddenTray, setShowHiddenTray] = useState(false)
  const [isDragOver, setIsDragOver] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const { width, mounted } = useContainerWidth()

  if (!currentWorkspace) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-fg-muted">No workspace selected</div>
      </div>
    )
  }

  const visibleWidgets = currentWorkspace.widgets.filter((w) => !w.hidden)
  const hiddenWidgets = currentWorkspace.widgets.filter((w) => w.hidden)

  const layouts: any = {
    lg: visibleWidgets.map((w) => ({
      i: w.id,
      x: w.layout.x,
      y: w.layout.y,
      w: w.layout.w,
      h: w.layout.h,
      minW: w.layout.minW || 2,
      minH: w.layout.minH || 2,
    })),
  }

  const handleLayoutChange = (newLayout: any, _allLayouts: any) => {
    const items = Array.isArray(newLayout) ? newLayout : (newLayout?.lg || [])
    if (items.length === 0) return
    updateWidgetLayout(currentWorkspace.id, items.map((l: any) => ({ i: l.i, x: l.x, y: l.y, w: l.w, h: l.h })))
  }

  // Drop handler — accept widget from library
  const handleDragOver = (e: React.DragEvent) => {
    if (e.dataTransfer.types.includes('widget-type')) {
      e.preventDefault()
      e.dataTransfer.dropEffect = 'copy'
      setIsDragOver(true)
    }
  }

  const handleDragLeave = () => {
    setIsDragOver(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
    const type = e.dataTransfer.getData('widget-type')
    if (type) {
      // Place at end of layout
      const maxY = currentWorkspace.widgets.reduce((m, w) => Math.max(m, w.layout.y + w.layout.h), 0)
      addWidget(currentWorkspace.id, type, { x: 0, y: maxY })
    }
  }

  return (
    <div className={cn('h-full flex flex-col bg-bg-0', fullscreen && 'fixed inset-0 z-50')}>
      {/* Workspace toolbar */}
      <div className="h-10 flex items-center justify-between px-3 border-b border-line bg-bg-1 flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <h2 className="text-sm font-semibold truncate">{currentWorkspace.name}</h2>
          {currentWorkspace.builtIn && (
            <span className="px-1.5 py-0.5 text-2xs rounded bg-bg-2 text-fg-muted uppercase tracking-wider">Built-in</span>
          )}
          <span className="text-2xs text-fg-dim">
            {visibleWidgets.length} visible · {currentWorkspace.widgets.length} total
          </span>
          {hiddenWidgets.length > 0 && (
            <button
              onClick={() => setShowHiddenTray(!showHiddenTray)}
              className={cn(
                'h-6 px-2 text-2xs rounded font-medium flex items-center gap-1.5 ml-1',
                showHiddenTray ? 'bg-bg-3 text-fg' : 'bg-bg-2 text-fg-muted hover:text-fg',
              )}
            >
              <EyeOff className="h-3 w-3" />
              {hiddenWidgets.length} hidden
            </button>
          )}
        </div>
        <div className="flex items-center gap-1">
          {hiddenWidgets.length > 0 && (
            <button
              onClick={() => showAllWidgets(currentWorkspace.id)}
              className="h-7 px-2.5 text-2xs font-medium rounded bg-bg-2 text-fg-muted hover:text-fg border border-line flex items-center gap-1.5"
              title="Show all hidden widgets"
            >
              <Eye className="h-3 w-3" /> Show All
            </button>
          )}
          <button
            onClick={() => setEditingMode(!editingMode)}
            className={cn(
              'h-7 px-2.5 text-xs font-medium rounded flex items-center gap-1.5',
              editingMode ? 'bg-brand/15 text-brand border border-brand/40' : 'bg-bg-2 text-fg-muted hover:bg-bg-3 border border-line',
            )}
            title="Show grid guides during drag"
          >
            {editingMode ? <><Check className="h-3.5 w-3.5" /> Guides</> : <><Edit3 className="h-3.5 w-3.5" /> Guides</>}
          </button>
          <button
            onClick={() => setGalleryOpen(true)}
            className="h-7 px-2.5 text-xs font-medium rounded bg-brand text-white hover:bg-brand-600 flex items-center gap-1.5"
          >
            <Plus className="h-3.5 w-3.5" /> Add Widget
          </button>
          <button
            onClick={() => setFullscreen(!fullscreen)}
            className="h-7 w-7 rounded bg-bg-2 text-fg-muted hover:bg-bg-3 border border-line flex items-center justify-center"
            title={fullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {fullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {/* Grid + drop zone */}
      <div
        ref={containerRef}
        className="flex-1 min-h-0 overflow-auto bg-bg-0 relative"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* Drop indicator overlay */}
        {isDragOver && (
          <div className="absolute inset-2 z-30 border-2 border-dashed border-brand rounded-lg bg-brand/5 flex items-center justify-center pointer-events-none">
            <div className="text-brand text-sm font-semibold bg-bg-1 px-3 py-1.5 rounded-md border border-brand/30">
              Drop widget here to add
            </div>
          </div>
        )}

        {mounted && width > 0 ? (
          visibleWidgets.length > 0 ? (
            <Responsive
              width={width}
              className="layout"
              layouts={layouts}
              breakpoints={{ lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 }}
              cols={{ lg: 12, md: 10, sm: 6, xs: 4, xxs: 2 }}
              rowHeight={36}
              margin={[6, 6]}
              containerPadding={[6, 6]}
              // Always allow drag and resize — no Edit Mode gate
              dragConfig={{
                enabled: true,
                handle: '.widget-drag-handle',
                threshold: 3,
              }}
              resizeConfig={{
                enabled: true,
                handles: ['se'] as any,
              }}
              onLayoutChange={handleLayoutChange}
            >
              {visibleWidgets.map((widget, idx) => {
                const manifest = widgetRegistry.get(widget.type)
                const Widget = manifest?.component as any
                const isSelected = selectedWidgetId === widget.id
                return (
                  <div key={widget.id}>
                    <div
                      onClick={(e) => {
                        e.stopPropagation()
                        onSelectWidget?.(widget.id)
                      }}
                      className={cn(
                        'h-full w-full relative',
                        isSelected && 'ring-2 ring-brand/60 rounded-md',
                      )}
                    >
                      {/* Per-widget chrome: number badge + always-visible drag handle via WidgetFrame */}
                      <div className="h-full w-full flex flex-col">
                        {/* Mini chrome: number, drag handle, hide, settings, remove */}
                        <div className="widget-drag-handle flex items-center justify-between px-1.5 py-1 border-b border-line bg-bg-2/60 select-none h-7" style={{ cursor: 'grab' }}>
                          <div className="flex items-center gap-1.5">
                            <div className="flex items-center justify-center w-4 h-4 text-fg-dim">
                              <svg width="8" height="10" viewBox="0 0 8 10" className="opacity-70">
                                <circle cx="1" cy="1" r="1" fill="currentColor" />
                                <circle cx="1" cy="5" r="1" fill="currentColor" />
                                <circle cx="1" cy="9" r="1" fill="currentColor" />
                                <circle cx="5" cy="1" r="1" fill="currentColor" />
                                <circle cx="5" cy="5" r="1" fill="currentColor" />
                                <circle cx="5" cy="9" r="1" fill="currentColor" />
                              </svg>
                            </div>
                            <span className="text-2xs font-semibold uppercase tracking-wider text-fg-muted">
                              {(widget.config as any)?.title || manifest?.name || widget.type}
                            </span>
                            {widget.hidden && <EyeOff className="h-2.5 w-2.5 text-fg-dim ml-1" />}
                          </div>
                          <div className="flex items-center gap-0.5">
                            <button
                              onClick={(e) => { e.stopPropagation(); toggleWidgetHidden(currentWorkspace.id, widget.id) }}
                              className="h-5 w-5 rounded hover:bg-bg-3 text-fg-dim hover:text-fg flex items-center justify-center"
                              title="Hide widget"
                            >
                              <EyeOff className="h-3 w-3" />
                            </button>
                            <button
                              onClick={(e) => { e.stopPropagation(); setConfigWidget(widget.id) }}
                              className="h-5 w-5 rounded hover:bg-bg-3 text-fg-dim hover:text-fg flex items-center justify-center"
                              title="Configure"
                            >
                              <Settings className="h-3 w-3" />
                            </button>
                            <button
                              onClick={(e) => { e.stopPropagation(); removeWidget(currentWorkspace.id, widget.id) }}
                              className="h-5 w-5 rounded hover:bg-bearish/20 text-fg-dim hover:text-bearish flex items-center justify-center"
                              title="Remove"
                            >
                              <X className="h-3 w-3" />
                            </button>
                          </div>
                        </div>
                        <div className="flex-1 min-h-0 overflow-auto">
                          {manifest ? (
                            <Widget
                              id={widget.id}
                              config={widget.config}
                              refresh={() => {}}
                              loading={false}
                              lastUpdated={Date.now()}
                            />
                          ) : (
                            <UnknownWidgetPlaceholder name={widget.type} />
                          )}
                        </div>
                      </div>

                      {/* Numbered badge */}
                      <div className={cn(
                        'absolute -top-1 -left-1 flex items-center justify-center w-5 h-5 rounded-full text-2xs font-mono num font-semibold z-20 shadow-md',
                        isSelected ? 'bg-brand text-white' : 'bg-bg-2 text-fg-muted border border-line',
                      )}>
                        {idx + 1}
                      </div>
                    </div>
                  </div>
                )
              })}
            </Responsive>
          ) : (
            <EmptyState onAddWidget={() => setGalleryOpen(true)} hasHidden={hiddenWidgets.length > 0} onShowAll={() => showAllWidgets(currentWorkspace.id)} />
          )
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-fg-muted text-sm">Loading workspace...</div>
        )}
      </div>

      {/* Hidden Widgets Tray */}
      {showHiddenTray && hiddenWidgets.length > 0 && (
        <div className="border-t border-line bg-bg-1 max-h-48 overflow-y-auto flex-shrink-0">
          <div className="px-3 py-2 flex items-center justify-between border-b border-line-subtle sticky top-0 bg-bg-1 z-10">
            <div className="flex items-center gap-2">
              <EyeOff className="h-3.5 w-3.5 text-fg-muted" />
              <span className="text-2xs font-semibold uppercase tracking-wider text-fg-muted">Hidden Widgets</span>
              <span className="text-2xs text-fg-dim">{hiddenWidgets.length} hidden</span>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => showAllWidgets(currentWorkspace.id)}
                className="h-6 px-2 text-2xs font-medium rounded bg-bg-2 text-fg-muted hover:text-fg border border-line flex items-center gap-1"
              >
                <Eye className="h-3 w-3" /> Show All
              </button>
              <button
                onClick={() => setShowHiddenTray(false)}
                className="h-6 w-6 rounded text-fg-muted hover:text-fg hover:bg-bg-2 flex items-center justify-center"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          </div>
          <div className="p-2 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-1.5">
            {hiddenWidgets.map((w) => {
              const manifest = widgetRegistry.get(w.type)
              const Icon = manifest?.icon
              return (
                <div
                  key={w.id}
                  className="flex items-center gap-2 px-2 py-1.5 bg-bg-2 hover:bg-bg-3 rounded border border-line-subtle group"
                >
                  {Icon && (
                    <div className="h-6 w-6 rounded bg-brand/15 flex items-center justify-center flex-shrink-0">
                      <Icon className="h-3 w-3 text-brand" />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="text-2xs font-medium truncate">
                      {(w.config as any)?.title || manifest?.name || w.type}
                    </div>
                    <div className="text-2xs text-fg-dim truncate">
                      Hidden {w.hiddenAt ? Math.floor((Date.now() - w.hiddenAt) / 60000) + 'm ago' : ''}
                    </div>
                  </div>
                  <button
                    onClick={() => toggleWidgetHidden(currentWorkspace.id, w.id)}
                    className="h-6 px-2 text-2xs font-medium rounded bg-bg-1 hover:bg-bg-3 border border-line text-bullish hover:text-bullish flex items-center gap-1"
                    title="Restore widget"
                  >
                    <Eye className="h-3 w-3" /> Show
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Edit guides banner */}
      {editingMode && (
        <div className="h-7 px-3 bg-brand/10 border-t border-brand/30 flex items-center gap-2 text-2xs text-brand flex-shrink-0">
          <Edit3 className="h-3 w-3" />
          <span className="font-medium">Grid Guides On</span>
          <span className="text-fg-muted">— Snap-to-grid enabled. Drag any widget by its title bar. Resize from bottom-right corner.</span>
          <button
            onClick={() => setEditingMode(false)}
            className="ml-auto h-5 px-2 rounded bg-bg-2 hover:bg-bg-3 border border-line text-fg flex items-center gap-1"
          >
            <Check className="h-2.5 w-2.5" /> Done
          </button>
        </div>
      )}

      {galleryOpen && (
        <WidgetGallery
          workspaceId={currentWorkspace.id}
          onClose={() => setGalleryOpen(false)}
        />
      )}

      {configWidget && (
        <ConfigModal
          widgetId={configWidget}
          workspaceId={currentWorkspace.id}
          onClose={() => setConfigWidget(null)}
        />
      )}
    </div>
  )
}

function EmptyState({ onAddWidget, hasHidden, onShowAll }: { onAddWidget: () => void; hasHidden: boolean; onShowAll: () => void }) {
  return (
    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
      <div className="text-center max-w-md">
        <div className="inline-flex h-16 w-16 items-center justify-center rounded-full bg-bg-2 border border-line mb-3">
          <Plus className="h-7 w-7 text-fg-dim" />
        </div>
        <div className="text-base text-fg font-medium mb-1">Your workspace is empty</div>
        <div className="text-sm text-fg-muted mb-4">
          Drag widgets from the library on the left, or click below to browse.
        </div>
        <div className="flex items-center justify-center gap-2 pointer-events-auto">
          <button
            onClick={onAddWidget}
            className="h-9 px-4 text-sm font-medium rounded bg-brand text-white hover:bg-brand-600 flex items-center gap-1.5"
          >
            <Plus className="h-3.5 w-3.5" /> Browse Widget Gallery
          </button>
          {hasHidden && (
            <button
              onClick={onShowAll}
              className="h-9 px-4 text-sm font-medium rounded bg-bg-2 hover:bg-bg-3 border border-line text-fg flex items-center gap-1.5"
            >
              <Eye className="h-3.5 w-3.5" /> Show Hidden Widgets
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function UnknownWidgetPlaceholder({ name }: { name: string }) {
  return (
    <div className="h-full w-full flex items-center justify-center bg-bg-1 border border-bearish/40 rounded text-bearish text-xs">
      Unknown widget: {name}
    </div>
  )
}

function ConfigModal({ widgetId, workspaceId, onClose }: { widgetId: string; workspaceId: string; onClose: () => void }) {
  const workspace = useWorkspaceStore((s) => s.workspaces.find((w) => w.id === workspaceId))
  const updateConfig = useWorkspaceStore((s) => s.updateWidgetConfig)
  const widget = workspace?.widgets.find((w) => w.id === widgetId)
  if (!widget) return null
  const manifest = widgetRegistry.get(widget.type)
  if (!manifest) return null

  return (
    <div className="fixed inset-0 z-50 bg-bg-0/80 backdrop-blur-sm flex items-center justify-center" onClick={onClose}>
      <div className="w-96 bg-bg-1 border border-line rounded-md shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="px-4 py-3 border-b border-line flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold">Configure {manifest.name}</div>
            <div className="text-2xs text-fg-dim">{manifest.description}</div>
          </div>
          <button onClick={onClose} className="h-6 w-6 rounded hover:bg-bg-3 text-fg-muted flex items-center justify-center">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="p-4 space-y-3 max-h-[60vh] overflow-y-auto">
          {manifest.configSchema?.map((field) => (
            <div key={field.key}>
              <label className="text-2xs text-fg-dim uppercase tracking-wider">{field.label}</label>
              {field.type === 'text' && (
                <input
                  value={(widget.config as any)[field.key] || ''}
                  onChange={(e) => updateConfig(workspaceId, widgetId, { [field.key]: e.target.value })}
                  className="w-full h-8 bg-bg-0 border border-line rounded px-2 text-sm mt-1"
                />
              )}
              {field.type === 'number' && (
                <input
                  type="number"
                  value={(widget.config as any)[field.key] || ''}
                  onChange={(e) => updateConfig(workspaceId, widgetId, { [field.key]: +e.target.value })}
                  className="w-full h-8 bg-bg-0 border border-line rounded px-2 text-sm num mt-1"
                />
              )}
              {field.type === 'select' && (
                <select
                  value={(widget.config as any)[field.key] || ''}
                  onChange={(e) => updateConfig(workspaceId, widgetId, { [field.key]: e.target.value })}
                  className="w-full h-8 bg-bg-0 border border-line rounded px-2 text-sm mt-1"
                >
                  {field.options?.map((o) => (
                    <option key={String(o.value)} value={o.value}>{o.label}</option>
                  ))}
                </select>
              )}
            </div>
          ))}
          {(manifest.configSchema?.length || 0) === 0 && (
            <div className="text-xs text-fg-muted text-center py-4">No configuration options.</div>
          )}
        </div>
        <div className="px-4 py-2.5 border-t border-line flex justify-end">
          <button onClick={onClose} className="h-7 px-3 text-xs font-medium rounded bg-brand text-white">Done</button>
        </div>
      </div>
    </div>
  )
}
