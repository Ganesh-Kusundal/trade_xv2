/**
 * TopBar — Bloomberg-style header.
 *
 *   [Symbol Search]  [Timeframe tabs]      [Status / Quote]   [Replay] [Settings]
 *
 * Keyboard:
 *   ⌘K / Ctrl+K   → focus symbol search
 */

import { useEffect } from 'react'
import { History, Wifi, WifiOff } from 'lucide-react'
import { SymbolSearch } from './SymbolSearch'
import { useAppStore } from '@/store/app'
import type { Timeframe } from '@/types'
import { cn, formatIN, formatPercent, pnlColor } from '@/lib/utils'
import { useQuote } from '@/hooks/useQuote'

const TIMEFRAMES: { id: Timeframe; label: string }[] = [
  { id: '1m',  label: '1m' },
  { id: '3m',  label: '3m' },
  { id: '5m',  label: '5m' },
  { id: '15m', label: '15m' },
  { id: '30m', label: '30m' },
  { id: '1h',  label: '1h' },
  { id: '4h',  label: '4h' },
  { id: '1d',  label: '1D' },
  { id: '1w',  label: '1W' },
]

export function TopBar() {
  const symbol = useAppStore((s) => s.activeSymbol)
  const tf = useAppStore((s) => s.activeTimeframe)
  const setTimeframe = useAppStore((s) => s.setActiveTimeframe)
  const replayOpen = useAppStore((s) => s.replayOpen)
  const setReplayOpen = useAppStore((s) => s.setReplayOpen)

  const { quote, isLive, latencyMs, dataSource } = useQuote(symbol, { intervalMs: 1500 })

  // ⌘K / Ctrl+K to focus search
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        // The search input is auto-focusable when the dropdown opens; we
        // simulate a click on the search wrap.
        const el = document.querySelector<HTMLElement>('[data-symbol-search]')
        el?.click()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div className="flex items-center gap-3 h-9 px-2 border-b border-bline bg-bbg1">
      {/* Brand */}
      <div className="flex items-center gap-1.5 pr-2 mr-1 border-r border-bline">
        <div className="h-5 w-5 rounded-sm bg-bamb/20 border border-bamb/40 flex items-center justify-center font-mono text-[11px] font-bold text-bamb">
          TX
        </div>
        <span className="text-sm font-semibold tracking-wide text-bfg">TradeXV2</span>
      </div>

      <div data-symbol-search>
        <SymbolSearch />
      </div>

      {/* Timeframes */}
      <div className="flex items-center h-7 border border-bline rounded-sm overflow-hidden">
        {TIMEFRAMES.map((t) => (
          <button
            key={t.id}
            onClick={() => setTimeframe(t.id)}
            className={cn(
              'h-full px-2 text-2xs font-mono num border-r border-bline last:border-r-0 transition-colors',
              tf === t.id
                ? 'bg-bbg3 text-bfg'
                : 'bg-bbg2 text-bfgm hover:text-bfg hover:bg-bbg3',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Quote HUD */}
      <div className="flex-1 flex items-center gap-3 px-3 ml-2 h-7 border-l border-r border-bline">
        {quote ? (
          <>
            <span className="text-2xs text-bfgd uppercase tracking-wider">{quote.exchange}</span>
            <span className="text-2xs text-bfgd">·</span>
            <span className="font-mono num text-sm font-semibold text-bfg">
              {formatIN(quote.ltp)}
            </span>
            <span className={cn('font-mono num text-2xs font-semibold', pnlColor(quote.change))}>
              {quote.change >= 0 ? '+' : ''}{formatIN(quote.change)}
            </span>
            <span className={cn('font-mono num text-2xs', pnlColor(quote.changePct))}>
              {formatPercent(quote.changePct)}
            </span>
            <span className="text-2xs text-bfgd font-mono num">
              H {formatIN(quote.high)}  L {formatIN(quote.low)}
            </span>
            <span className="text-2xs text-bfgd font-mono num">
              Vol {quote.volume.toLocaleString('en-IN')}
            </span>
          </>
        ) : (
          <span className="text-2xs text-bfgd">—</span>
        )}
      </div>

      {/* Connection indicator */}
      <div
        className={cn(
          'flex items-center gap-1.5 h-6 px-2 rounded-sm border text-2xs font-mono num',
          dataSource === 'ws'
            ? 'bg-bull/10 border-bull/30 text-bull'
            : dataSource === 'http'
            ? 'bg-bblue/10 border-bblue/30 text-bblue'
            : dataSource === 'mock'
            ? 'bg-byellow/10 border-byellow/30 text-byellow'
            : 'bg-bbg2 border-bline text-bfgd',
        )}
        title={
          dataSource === 'ws'
            ? 'Live via WebSocket'
            : dataSource === 'http'
            ? 'Live via HTTP polling'
            : dataSource === 'mock'
            ? 'Mock data (backend offline)'
            : 'Stale / no data'
        }
      >
        {isLive ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
        {dataSource === 'ws'
          ? `LIVE · ${latencyMs}ms`
          : dataSource === 'http'
          ? `HTTP · ${latencyMs}ms`
          : dataSource === 'mock'
          ? 'MOCK'
          : 'STALE'}
      </div>

      {/* Replay button */}
      <button
        onClick={() => setReplayOpen(!replayOpen)}
        className={cn(
          'h-7 px-2.5 inline-flex items-center gap-1.5 rounded-sm border text-2xs font-semibold transition-colors',
          replayOpen
            ? 'bg-bamb/15 border-bamb/40 text-bamb'
            : 'bg-bbg2 border-bline text-bfgm hover:text-bfg hover:border-bline2',
        )}
      >
        <History className="h-3.5 w-3.5" />
        REPLAY
      </button>
    </div>
  )
}
