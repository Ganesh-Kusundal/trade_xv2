/**
 * WidgetFrame — Bloomberg-style chrome around every widget.
 *
 * Always-visible controls (no "Edit mode" required):
 *   - Drag handle (grip icon, left side of title bar) — always draggable
 *   - Title (truncated, editable in Properties Panel)
 *   - Last-updated timestamp
 *   - Hide/Show toggle (eye icon)
 *   - Refresh (with loading spinner)
 *   - Settings (opens config modal)
 *
 * Resize handle: bottom-right corner (always available via react-grid-layout)
 */

import * as React from 'react'
import { RefreshCw, Settings, Eye, EyeOff, MoreVertical } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { WidgetProps } from './Widget'

interface WidgetFrameProps extends Omit<WidgetProps, 'updateConfig'> {
  className?: string
  children: React.ReactNode
  onRemove?: () => void
  onConfigOpen?: () => void
  onToggleHidden?: () => void
  updateConfig?: WidgetProps['updateConfig']
  isSelected?: boolean
  widgetNumber?: number
  hidden?: boolean
  variant?: 'default' | 'compact'
}

export function WidgetFrame({
  config,
  loading,
  lastUpdated,
  refresh,
  onRemove,
  onConfigOpen,
  onToggleHidden,
  hidden,
  isSelected,
  widgetNumber,
  className,
  children,
  variant = 'default',
}: WidgetFrameProps) {
  const [now, setNow] = React.useState(Date.now())
  React.useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  const time = lastUpdated
    ? new Date(lastUpdated).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
    : new Date(now).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })

  if (hidden) {
    // Collapsed state: small chip-like card
    return (
      <div className={cn(
        'h-full w-full flex items-center gap-2 px-2.5 py-1.5 bg-bg-1 border border-line rounded-md',
        isSelected && 'ring-2 ring-brand/60',
        className,
      )}>
        <div className="h-6 w-6 rounded bg-bg-3 flex items-center justify-center text-2xs font-mono num font-semibold text-fg-muted">
          {widgetNumber}
        </div>
        <div className="text-2xs font-semibold uppercase tracking-wider text-fg-muted truncate flex-1">
          {(config as any)?.title || (config as any)?.symbol || 'Widget'}
        </div>
        <button
          onClick={onToggleHidden}
          className="h-6 px-2 text-2xs rounded bg-bg-2 hover:bg-bg-3 border border-line text-fg-muted hover:text-fg flex items-center gap-1"
          title="Show widget"
        >
          <Eye className="h-3 w-3" /> Show
        </button>
      </div>
    )
  }

  return (
    <div className={cn(
      'h-full w-full flex flex-col bg-bg-1 border border-line rounded-md overflow-hidden transition-colors group',
      isSelected && 'border-brand/60',
      className,
    )}>
      {/* Title bar — always shows drag handle, title, timestamp, action buttons */}
      <div
        className={cn(
          'widget-drag-handle flex items-center justify-between px-1.5 py-1 border-b border-line bg-bg-2/40 select-none',
          variant === 'compact' ? 'h-6' : 'h-7',
        )}
        style={{ cursor: 'grab' }}
      >
        <div className="flex items-center gap-1 min-w-0 flex-1">
          {/* Drag handle (always visible) */}
          <div className="flex items-center justify-center w-4 h-4 text-fg-dim hover:text-fg flex-shrink-0" title="Drag to move">
            <svg width="8" height="10" viewBox="0 0 8 10" className="opacity-60 group-hover:opacity-100">
              <circle cx="1" cy="1" r="1" fill="currentColor" />
              <circle cx="1" cy="5" r="1" fill="currentColor" />
              <circle cx="1" cy="9" r="1" fill="currentColor" />
              <circle cx="5" cy="1" r="1" fill="currentColor" />
              <circle cx="5" cy="5" r="1" fill="currentColor" />
              <circle cx="5" cy="9" r="1" fill="currentColor" />
            </svg>
          </div>
          <div className="text-2xs font-semibold uppercase tracking-wider text-fg-muted truncate">
            {(config as any)?.title || (config as any)?.symbol || 'Widget'}
          </div>
          <span className="text-2xs text-fg-dim font-mono num flex-shrink-0 ml-1.5">{time}</span>
        </div>
        <div className="flex items-center gap-0.5 flex-shrink-0">
          {onToggleHidden && (
            <button
              onClick={(e) => { e.stopPropagation(); onToggleHidden() }}
              className="h-5 w-5 rounded hover:bg-bg-3 text-fg-dim hover:text-fg flex items-center justify-center"
              title="Hide widget"
            >
              <EyeOff className="h-3 w-3" />
            </button>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); refresh() }}
            className="h-5 w-5 rounded hover:bg-bg-3 text-fg-dim hover:text-fg flex items-center justify-center"
            title="Refresh"
          >
            <RefreshCw className={cn('h-3 w-3', loading && 'animate-spin')} />
          </button>
          {onConfigOpen && (
            <button
              onClick={(e) => { e.stopPropagation(); onConfigOpen() }}
              className="h-5 w-5 rounded hover:bg-bg-3 text-fg-dim hover:text-fg flex items-center justify-center"
              title="Configure"
            >
              <Settings className="h-3 w-3" />
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 min-h-0 overflow-auto">{children}</div>
    </div>
  )
}
