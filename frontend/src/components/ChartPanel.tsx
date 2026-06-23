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

import { useEffect, useState } from 'react'
import { CandlestickChart } from './CandlestickChart'
import { ReplayPanel } from './ReplayPanel'
import { ChartToolbar, type ChartSettings } from './ChartToolbar'
import { useAppStore } from '@/store/app'
import { useCandles } from '@/hooks/useCandles'
import { useQuote } from '@/hooks/useQuote'
import { useMarketStream } from '@/hooks/useMarketStream'
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
  const [replayActive, setReplayActive] = useState(false)
  const [replayState, setReplayState] = useState<ReplayState>('IDLE')

  const { candles, loading, error, push, visibleCount } = useCandles(symbol, timeframe, bars)
  const { quote, wsConnected } = useQuote(symbol, { intervalMs: 1500 })
  const { lastMessage } = useMarketStream({ symbols: [symbol], enabled: !replayActive })

  // Live tick from WebSocket — skip HTTP poll when WS active
  useEffect(() => {
    if (replayActive || !wsConnected) return
    if (!lastMessage || (lastMessage.type !== 'quote' && lastMessage.type !== 'tick')) return
    if (lastMessage.symbol?.toUpperCase() !== symbol.toUpperCase()) return
    const ltp = lastMessage.ltp
    if (ltp == null) return
    const ts = lastMessage.ts ?? Date.now()
    const tBucket = bucketFor(timeframe, ts)
    push({
      t: tBucket,
      o: candles.at(-1)?.o ?? ltp,
      h: Math.max(candles.at(-1)?.h ?? ltp, ltp),
      l: Math.min(candles.at(-1)?.l ?? ltp, ltp),
      c: ltp,
      v: (candles.at(-1)?.v ?? 0) + Math.floor((lastMessage.volume ?? 0) * 0.0001),
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastMessage, symbol, timeframe, replayActive, wsConnected])

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
