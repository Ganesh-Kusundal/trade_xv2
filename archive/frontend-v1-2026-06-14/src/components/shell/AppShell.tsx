/**
 * AppShell — root layout with the 3-column widget builder interface.
 *
 * Default layout (library hidden):
 *   ┌────────────────────────────────────────────────────┐
 *   │                  Header (Title + Actions)            │
 *   ├───────────────────────────────┬──────────────────┤
 *   │     Workspace Canvas (Center)   │  Properties Panel │
 *   │                                 │      (Right)      │
 *   ├─────────────────────────────────┴──────────────────┤
 *   │                  Status Bar                          │
 *   └────────────────────────────────────────────────────┘
 *
 * With library open:
 *   ┌────────────────────────────────────────────────────┐
 *   │                  Header                                │
 *   ├──────────┬─────────────────────────┬──────────────┤
 *   │ Widget   │    Workspace Canvas      │ Properties   │
 *   │ Library  │    (Center)              │   Panel      │
 *   ├──────────┴─────────────────────────┴──────────────┤
 *   │                  Status Bar                            │
 *   └────────────────────────────────────────────────────┘
 *
 * Library is hidden by default for a focused, clean workspace.
 * Toggle via the button in the header or the floating left-edge tab.
 */

import { Header } from './Header'
import { WidgetLibrary } from './WidgetLibrary'
import { PropertiesPanel } from './PropertiesPanel'
import { StatusBar } from './StatusBar'
import { useUIStore } from '@/store/uiStore'
import { useState } from 'react'
import { Workspace } from '@/features/workspace/Workspace'
import { Dashboard } from '@/features/dashboard/Dashboard'
import { Market } from '@/features/market/Market'
import { Scanner } from '@/features/scanner/Scanner'
import { Research } from '@/features/research/Research'
import { Analytics } from '@/features/analytics/Analytics'
import { Strategies } from '@/features/strategies/Strategies'
import { Backtest } from '@/features/backtest/Backtest'
import { Replay } from '@/features/replay/Replay'
import { Options } from '@/features/options/Options'
import { Portfolio } from '@/features/portfolio/Portfolio'
import { Positions } from '@/features/positions/Positions'
import { Orders } from '@/features/orders/Orders'
import { Risk } from '@/features/risk/Risk'
import { Alerts } from '@/features/alerts/Alerts'
import { Reports } from '@/features/reports/Reports'
import { Settings } from '@/features/settings/Settings'
import { AMTScalper } from '@/features/amt-scalper/AMTScalper'
import { LayoutGrid } from 'lucide-react'
import { cn } from '@/lib/utils'

const LEGACY_WORKSPACE_MAP = {
  dashboard: Dashboard,
  market: Market,
  scanner: Scanner,
  research: Research,
  analytics: Analytics,
  strategies: Strategies,
  backtest: Backtest,
  replay: Replay,
  options: Options,
  portfolio: Portfolio,
  positions: Positions,
  orders: Orders,
  risk: Risk,
  alerts: Alerts,
  reports: Reports,
  settings: Settings,
  'amt-scalper': AMTScalper,
} as const

const WORKSPACE_VIEW = 'workspace' as const

export function AppShell() {
  const { workspace } = useUIStore()
  const [selectedWidgetId, setSelectedWidgetId] = useState<string | null>(null)
  // Library hidden by default for a clean, focused workspace
  const [libraryOpen, setLibraryOpen] = useState(false)

  const Component = workspace === WORKSPACE_VIEW ? Workspace : LEGACY_WORKSPACE_MAP[workspace as keyof typeof LEGACY_WORKSPACE_MAP]
  const isWorkspaceMode = workspace === WORKSPACE_VIEW
  const isAMTMode = workspace === 'amt-scalper'

  return (
    <div className="flex h-screen w-screen bg-bg-0 text-fg overflow-hidden flex-col">
      {!isAMTMode && (
        <Header
          libraryOpen={libraryOpen}
          onToggleLibrary={() => setLibraryOpen((v) => !v)}
        />
      )}
      <div className="flex-1 flex min-h-0">
        {/* Widget Library — hidden by default */}
        {isWorkspaceMode && (
          <div
            className={cn(
              'flex-shrink-0 overflow-hidden transition-all duration-200 ease-out',
              libraryOpen ? 'w-60' : 'w-0',
            )}
          >
            <div className="w-60 h-full">
              <WidgetLibrary />
            </div>
          </div>
        )}

        {/* Floating left-edge tab to show library when hidden */}
        {isWorkspaceMode && !libraryOpen && (
          <button
            onClick={() => setLibraryOpen(true)}
            className="absolute left-0 top-1/2 -translate-y-1/2 z-30 h-20 w-5 bg-bg-1 border border-line border-l-0 rounded-r-md flex flex-col items-center justify-center gap-1 hover:bg-bg-2 hover:w-6 transition-all group"
            title="Show Widget Library (⌘L)"
          >
            <LayoutGrid className="h-3 w-3 text-fg-dim group-hover:text-fg" />
            <span className="text-2xs font-semibold text-fg-dim group-hover:text-fg" style={{ writingMode: 'vertical-rl', textOrientation: 'mixed' }}>
              LIBRARY
            </span>
          </button>
        )}

        {/* Main workspace canvas (center) */}
        <div className="flex-1 min-w-0 overflow-hidden relative">
          <Component />
        </div>

        {/* Properties Panel — always on the right (skipped in AMT mode) */}
        {isWorkspaceMode && <PropertiesPanel selectedWidgetId={selectedWidgetId} onSelectWidget={setSelectedWidgetId} />}
      </div>
      {!isAMTMode && <StatusBar />}
    </div>
  )
}
