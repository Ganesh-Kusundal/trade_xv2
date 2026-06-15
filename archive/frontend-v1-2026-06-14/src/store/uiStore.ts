import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Workspace =
  | 'workspace'
  | 'dashboard'
  | 'market'
  | 'scanner'
  | 'research'
  | 'analytics'
  | 'strategies'
  | 'backtest'
  | 'replay'
  | 'options'
  | 'portfolio'
  | 'positions'
  | 'orders'
  | 'risk'
  | 'alerts'
  | 'reports'
  | 'settings'
  | 'amt-scalper'

interface UIState {
  workspace: Workspace
  setWorkspace: (w: Workspace) => void
  sidebarCollapsed: boolean
  setSidebarCollapsed: (v: boolean) => void
  statusBarCollapsed: boolean
  setStatusBarCollapsed: (v: boolean) => void
  marketOpen: boolean
  setMarketOpen: (v: boolean) => void
  activeSymbol: string
  setActiveSymbol: (s: string) => void
  chartTimeframe: '1m' | '3m' | '5m' | '15m' | '1h' | '1d'
  setChartTimeframe: (t: '1m' | '3m' | '5m' | '15m' | '1h' | '1d') => void
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      workspace: 'workspace',
      setWorkspace: (workspace) => set({ workspace }),
      sidebarCollapsed: false,
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      statusBarCollapsed: false,
      setStatusBarCollapsed: (statusBarCollapsed) => set({ statusBarCollapsed }),
      marketOpen: true,
      setMarketOpen: (marketOpen) => set({ marketOpen }),
      activeSymbol: 'RELIANCE',
      setActiveSymbol: (activeSymbol) => set({ activeSymbol }),
      chartTimeframe: '5m',
      setChartTimeframe: (chartTimeframe) => set({ chartTimeframe }),
    }),
    {
      name: 'tradex-ui',
      partialize: (s) => ({ sidebarCollapsed: s.sidebarCollapsed, statusBarCollapsed: s.statusBarCollapsed, activeSymbol: s.activeSymbol, chartTimeframe: s.chartTimeframe }),
    },
  ),
)
