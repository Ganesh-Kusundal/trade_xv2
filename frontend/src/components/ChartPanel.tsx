/**
 * ChartPanel — the main chart container.
 *
 * Owns the candles state, live tick, optional replay state and renders
 * the chart toolbar + candlestick chart + replay panel.
 *
 * Replay, when active, takes over the chart: the chart shows the
 * progressively-revealed candles up to the cursor, and the playhead
 * tracks the latest replay tick.
 */

import { useEffect, useRef, useState } from 'react'
import { CandlestickChart } from './CandlestickChart'
import { ReplayPanel } from './ReplayPanel'
import { ChartToolbar, type ChartSettings } from './ChartToolbar'
import { useAppStore } from '@/store/app'
import { useCandles } from '@/hooks/useCandles'
import { useQuote } from '@/hooks/useQuote'
import { getQuote } from '@/api/client'
import { cn, formatIN, formatPercent, pnlColor } from '@/lib/utils'
import type { Candle, ReplayState } from '@/types'

const DEFAULT_SETTINGS: ChartSettings = {
  showMA: true,
  showVolume: true,
  crosshair: true,
  indicators: { ema9: true, ema20: true, ema50: true, vwap: false, bb: false },
  theme: 'dark',
}

export function ChartPanel() {
  const symbol = useAppStore((s) => s.activeSymbol)
  const timeframe = useAppStore((s) => s.activeTimeframe)
  const replayOpen = useAppStore((s) => s.replayOpen)
  const setReplayOpen = useAppStore((s) => s.setReplayOpen)

  const [bars, setBars] = useState(200)
  const [settings, setSettings] = useState<ChartSettings>(DEFAULT_SETTINGS)
  const { candles, loading, error, push, visibleCount } = useCandles(symbol, timeframe, bars)
  const { quote } = useQuote(symbol, { intervalMs: 1500 })

  const [replayActive, setReplayActive] = useState(false)
  const [replayState, setReplayState] = useState<ReplayState>('IDLE')

  // Live tick — only when not in replay
  const lastTickRef = useRef<number>(0)
  useEffect(() => {
    if (replayActive) return
    const id = window.setInterval(async () => {
      if (Date.now() - lastTickRef.current < 1000) return
      lastTickRef.current = Date.now()
      try {
        const q = await getQuote(symbol)
        const tBucket = bucketFor(timeframe, q.ts)
        push({
          t: tBucket,
          o: candles.at(-1)?.o ?? q.ltp,
          h: Math.max(candles.at(-1)?.h ?? q.ltp, q.ltp),
          l: Math.min(candles.at(-1)?.l ?? q.ltp, q.ltp),
          c: q.ltp,
          v: (candles.at(-1)?.v ?? 0) + Math.floor(q.volume * 0.0001),
        })
      } catch { /* ignore */ }
    }, 1500)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, timeframe, replayActive, candles.length])

  return (
    <div className="flex-1 min-w-0 min-h-0 flex flex-col">
      {/* Chart header strip */}
      <div className="flex items-center justify-between h-7 px-2 border-b border-bline bg-bbg1">
        <div className="flex items-center gap-3">
          {replayActive && (
            <span className={cn(
              'text-[10px] px-1.5 py-0.5 rounded font-mono num uppercase',
              replayState === 'PLAYING' ? 'bg-bull/20 text-bull' :
              replayState === 'PAUSED'  ? 'bg-warning/20 text-warning' :
              'bg-bear/20 text-bear',
            )}>
              REPLAY · {replayState}
            </span>
          )}
          {!replayActive && quote && (
            <div className="flex items-center gap-2 text-2xs font-mono num">
              <span className="text-fgd">LTP</span>
              <span className="text-fg font-semibold">{formatIN(quote.ltp)}</span>
              <span className={cn('font-semibold', pnlColor(quote.change))}>
                {formatIN(quote.change)} ({formatPercent(quote.changePct)})
              </span>
              <span className="text-fgd">
                O {formatIN(quote.open)} H {formatIN(quote.high)} L {formatIN(quote.low)} Prev {formatIN(quote.prevClose)}
              </span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-3 text-[10px] text-fgd font-mono num">
          <span>{candles.length} bars loaded</span>
          {visibleCount < candles.length && (
            <span className="text-bcy">showing {visibleCount}</span>
          )}
        </div>
      </div>

      {/* Chart toolbar */}
      <div className="relative">
        <ChartToolbar
          settings={settings}
          onChange={setSettings}
          bars={bars}
          onBarsChange={setBars}
        />
      </div>

      {/* Replay panel (collapsible) */}
      {replayOpen && (
        <div className="px-2 pt-2">
          <ReplayPanel
            symbol={symbol}
            onCandle={(c: Candle) => push(c)}
            onState={(s) => {
              setReplayActive(s.state !== 'IDLE' && s.state !== 'ENDED')
              setReplayState(s.state)
            }}
            onClose={() => { setReplayOpen(false); setReplayActive(false); setReplayState('IDLE') }}
          />
        </div>
      )}

      {/* Chart body */}
      <div className="flex-1 min-h-0 px-2 pb-2">
        <div className="h-full b-panel rounded-sm bg-bbg1 overflow-hidden relative">
          {error ? (
            <div className="h-full flex items-center justify-center text-bear text-2xs">{error}</div>
          ) : loading && candles.length === 0 ? (
            <div className="h-full flex items-center justify-center text-fgd text-2xs">
              Loading {symbol} {timeframe}…
            </div>
          ) : (
            <CandlestickChart
              candles={candles}
              symbol={symbol}
              timeframe={timeframe}
              visibleCount={replayActive ? visibleCount : undefined}
              liveLtp={!replayActive ? quote?.ltp : undefined}
              showVolume={settings.showVolume}
              showMA={settings.showMA}
            />
          )}
        </div>
      </div>
    </div>
  )
}

/** Bucket a timestamp into the start of its `tf` interval. */
function bucketFor(tf: import('@/types').Timeframe, ts: number): number {
  const ms: Record<import('@/types').Timeframe, number> = {
    '1m': 60_000, '3m': 180_000, '5m': 300_000, '15m': 900_000, '30m': 1_800_000,
    '1h': 3_600_000, '4h': 14_400_000, '1d': 86_400_000, '1w': 604_800_000,
  }
  return Math.floor(ts / ms[tf]) * ms[tf]
}
