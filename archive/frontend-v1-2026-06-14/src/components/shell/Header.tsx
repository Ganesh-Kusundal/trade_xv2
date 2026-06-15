/**
 * Header — top bar with title, subtitle, workspace switcher, and action buttons.
 * Includes a Widget Library toggle button (hidden by default).
 */

import { cn } from '@/lib/utils'
import { Save, Share2, Plus, LayoutGrid, ChevronDown, User, PanelLeft, X, Cpu } from 'lucide-react'
import { useWorkspaceStore } from '@/workspaces/store'
import { useUIStore } from '@/store/uiStore'
import { useState } from 'react'

interface HeaderProps {
  className?: string
  libraryOpen?: boolean
  onToggleLibrary?: () => void
}

export function Header({ className, libraryOpen, onToggleLibrary }: HeaderProps) {
  const workspaces = useWorkspaceStore((s) => s.workspaces)
  const currentWorkspaceId = useWorkspaceStore((s) => s.currentWorkspaceId)
  const setCurrentWorkspace = useWorkspaceStore((s) => s.setCurrent)
  const createWorkspace = useWorkspaceStore((s) => s.createWorkspace)
  const currentWorkspace = workspaces.find((w) => w.id === currentWorkspaceId)
  const { setWorkspace } = useUIStore()
  const [showSwitcher, setShowSwitcher] = useState(false)

  return (
    <header className={cn('h-16 flex items-center justify-between px-4 bg-bg-1 border-b border-line flex-shrink-0', className)}>
      {/* Brand + Title + Subtitle */}
      <div className="flex items-center gap-4 min-w-0 flex-1">
        <div className="flex items-center gap-2.5">
          <div className="h-9 w-9 rounded-md bg-gradient-to-br from-brand via-accent to-brand flex items-center justify-center shadow-lg">
            <svg viewBox="0 0 24 24" className="h-5 w-5 text-white" fill="none">
              <path d="M3 18 L8 11 L12 14 L17 7 L21 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <div className="text-base font-semibold leading-tight">TradeXV2</div>
            <div className="text-2xs text-fg-dim leading-tight">Quant Platform</div>
          </div>
        </div>
        <div className="h-8 w-px bg-line" />
        <div className="min-w-0">
          <div className="text-sm font-semibold leading-tight">Widget Based Quant Workspace</div>
          <div className="text-2xs text-fg-dim leading-tight">Build your Workspace. Plug Widgets. Analyze Markets. Execute Trades.</div>
        </div>
      </div>

      {/* Right: Workspace switcher + Library toggle + actions + user */}
      <div className="flex items-center gap-1.5 flex-shrink-0">
        {/* AMT Scalper launcher */}
        <button
          onClick={() => setWorkspace('amt-scalper')}
          className="h-9 px-3 text-sm font-bold rounded flex items-center gap-2 bg-black border border-cyan-500/40 text-cyan-300 hover:bg-cyan-500/10 transition-colors"
          title="Launch AMT Scalper System"
        >
          <Cpu className="h-3.5 w-3.5" />
          <span className="hidden lg:inline tracking-wider">AMT SCALPER</span>
        </button>

        {/* Library toggle */}
        {onToggleLibrary && (
          <button
            onClick={onToggleLibrary}
            className={cn(
              'h-9 px-3 text-sm font-medium rounded flex items-center gap-2 transition-colors',
              libraryOpen
                ? 'bg-brand/15 text-brand border border-brand/40'
                : 'bg-bg-2 text-fg-muted hover:text-fg border border-line',
            )}
            title={libraryOpen ? 'Hide Widget Library' : 'Show Widget Library'}
          >
            {libraryOpen ? <X className="h-3.5 w-3.5" /> : <PanelLeft className="h-3.5 w-3.5" />}
            <span className="hidden lg:inline">Library</span>
          </button>
        )}

        {/* Workspace switcher */}
        <div className="relative">
          <button
            onClick={() => setShowSwitcher(!showSwitcher)}
            className="h-9 px-3 text-sm font-medium rounded bg-bg-2 hover:bg-bg-3 border border-line text-fg flex items-center gap-2"
          >
            <LayoutGrid className="h-4 w-4 text-fg-muted" />
            <span className="max-w-[180px] truncate">{currentWorkspace?.name || 'Select workspace'}</span>
            <ChevronDown className="h-3.5 w-3.5 text-fg-dim" />
          </button>
          {showSwitcher && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setShowSwitcher(false)} />
              <div className="absolute right-0 top-full mt-1 w-64 bg-bg-1 border border-line rounded-md shadow-2xl z-50 py-1 max-h-80 overflow-y-auto">
                {workspaces.map((w) => (
                  <button
                    key={w.id}
                    onClick={() => { setCurrentWorkspace(w.id); setShowSwitcher(false) }}
                    className={cn(
                      'w-full flex items-center justify-between px-3 py-2 text-sm hover:bg-bg-2 text-left',
                      w.id === currentWorkspaceId && 'bg-brand/10 text-brand',
                    )}
                  >
                    <span className="truncate flex items-center gap-2">
                      <LayoutGrid className="h-3.5 w-3.5" />
                      {w.name}
                    </span>
                    {w.builtIn && <span className="text-2xs text-fg-dim uppercase tracking-wider flex-shrink-0">Built-in</span>}
                  </button>
                ))}
                <div className="border-t border-line mt-1 pt-1">
                  <button
                    onClick={() => { createWorkspace('New Workspace'); setShowSwitcher(false) }}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-brand hover:bg-bg-2"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    New Workspace
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        <button className="h-9 px-3 text-sm font-medium rounded bg-bg-2 hover:bg-bg-3 border border-line text-fg-muted hover:text-fg flex items-center gap-2">
          <Save className="h-3.5 w-3.5" />
          Save Workspace
        </button>
        <button className="h-9 px-3 text-sm font-medium rounded bg-bg-2 hover:bg-bg-3 border border-line text-fg-muted hover:text-fg flex items-center gap-2">
          <Share2 className="h-3.5 w-3.5" />
          Share
        </button>
        <button
          onClick={() => createWorkspace('New Workspace')}
          className="h-9 px-3 text-sm font-medium rounded bg-brand text-white hover:bg-brand-600 flex items-center gap-2"
        >
          <Plus className="h-3.5 w-3.5" />
          New Workspace
        </button>

        <div className="h-8 w-px bg-line mx-1" />

        <button className="h-9 px-2 text-sm font-medium rounded text-fg-muted hover:text-fg hover:bg-bg-2 flex items-center gap-2">
          <div className="h-7 w-7 rounded-full bg-accent/30 border border-accent/40 flex items-center justify-center text-xs font-semibold text-accent">A</div>
          <div className="text-left">
            <div className="text-xs leading-tight">Arjun</div>
            <div className="text-2xs text-fg-dim leading-tight">Pro Plan</div>
          </div>
        </button>
      </div>
    </header>
  )
}
