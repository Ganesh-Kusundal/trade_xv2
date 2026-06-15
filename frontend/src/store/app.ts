/**
 * App store — global UI state.
 *
 * Persisted to localStorage so user choices (last symbol, last
 * timeframe, watchlist) survive page reloads.
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Timeframe } from '@/types'
import { DEFAULT_WATCHLIST } from '@/data/symbols'

interface AppState {
  activeSymbol: string
  activeTimeframe: Timeframe
  watchlist: string[]
  replayOpen: boolean
  setActiveSymbol: (s: string) => void
  setActiveTimeframe: (tf: Timeframe) => void
  addToWatchlist: (s: string) => void
  removeFromWatchlist: (s: string) => void
  setReplayOpen: (v: boolean) => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      activeSymbol: 'RELIANCE',
      activeTimeframe: '5m',
      watchlist: DEFAULT_WATCHLIST,
      replayOpen: false,
      setActiveSymbol: (s) => set({ activeSymbol: s.toUpperCase() }),
      setActiveTimeframe: (tf) => set({ activeTimeframe: tf }),
      addToWatchlist: (s) =>
        set((state) =>
          state.watchlist.includes(s)
            ? state
            : { watchlist: [s, ...state.watchlist] },
        ),
      removeFromWatchlist: (s) =>
        set((state) => ({ watchlist: state.watchlist.filter((x) => x !== s) })),
      setReplayOpen: (v) => set({ replayOpen: v }),
    }),
    { name: 'tradexv2-ui' },
  ),
)
