/**
 * Deep Print Widget — Time & Sales / Tape Reading
 *
 * Live print tape showing individual trades with:
 *   - Buy / Sell side colouring (aggressor)
 *   - Trade size with heatmap intensity
 *   - Trade conditions (BLOCK / SWEEP / LARGE)
 *   - Cumulative buy/sell volume delta
 *   - Filter by size threshold
 *
 * Reference: https://www.deepcharts.com/features/deepprint
 */

import { useEffect, useMemo, useState } from 'react'
import { WidgetFrame } from '../../WidgetFrame'
import type { WidgetProps } from '../../Widget'
import { cn, formatIN, formatNumber, formatTime } from '@/lib/utils'
import { generateTrades, type Trade } from '@/services/deepchartsData'
import { TrendingUp, TrendingDown, Zap, Filter, AlertCircle } from 'lucide-react'

interface DeepPrintConfig {
  symbol?: string
  count?: number
  title?: string
  minSize?: number
  showCumulative?: boolean
}

export default function DeepPrintWidget({
  config,
  refresh,
  loading,
  lastUpdated,
}: WidgetProps<DeepPrintConfig>) {
  const symbol = config.symbol || 'NIFTY'
  const count = config.count || 80
  const [minSize, setMinSize] = useState(config.minSize || 0)
  const [trades, setTrades] = useState<Trade[]>([])

  useEffect(() => {
    setTrades(generateTrades(symbol, count))
    const id = window.setInterval(() => {
      setTrades((prev) => {
        const fresh = generateTrades(symbol, 20)
        return [...fresh, ...prev].slice(0, count)
      })
    }, 1000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, count])

  const visible = useMemo(() => trades.filter((t) => t.size >= minSize), [trades, minSize])
  const maxSize = useMemo(() => Math.max(...trades.map((t) => t.size), 1), [trades])

  const buyVol = visible.filter((t) => t.side === 'BUY').reduce((s, t) => s + t.size, 0)
  const sellVol = visible.filter((t) => t.side === 'SELL').reduce((s, t) => s + t.size, 0)
  const totalVol = buyVol + sellVol
  const buyPct = totalVol ? (buyVol / totalVol) * 100 : 50
  const cumDelta = buyVol - sellVol
  const sweepCount = visible.filter((t) => t.condition === 'SWEEP').length
  const blockCount = visible.filter((t) => t.condition === 'BLOCK').length

  return (
    <WidgetFrame
      id=""
      config={{ ...config, title: `DEEP PRINT - ${symbol}` }}
      loading={loading}
      lastUpdated={lastUpdated}
      refresh={() => {
        setTrades(generateTrades(symbol, count))
        refresh()
      }}
    >
      <div className="flex flex-col h-full">
        {/* Summary header */}
        <div className="px-2 py-1.5 border-b border-line bg-bg-2/40 grid grid-cols-5 gap-2 text-2xs">
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px]">Buy</div>
            <div className="font-mono num text-bullish font-semibold">{formatNumber(buyVol)}</div>
          </div>
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px]">Sell</div>
            <div className="font-mono num text-bearish font-semibold">{formatNumber(sellVol)}</div>
          </div>
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px]">Delta</div>
            <div
              className={cn(
                'font-mono num font-semibold',
                cumDelta > 0 ? 'text-bullish' : cumDelta < 0 ? 'text-bearish' : 'text-fg-muted',
              )}
            >
              {cumDelta > 0 ? '+' : ''}
              {formatNumber(cumDelta)}
            </div>
          </div>
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px]">Sweeps</div>
            <div className="font-mono num text-accent font-semibold">{sweepCount}</div>
          </div>
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px]">Blocks</div>
            <div className="font-mono num text-warning font-semibold">{blockCount}</div>
          </div>
        </div>

        {/* Buy/sell cumulative bar */}
        <div className="h-1 w-full flex">
          <div
            className="h-full bg-bullish transition-all"
            style={{ width: `${buyPct}%` }}
          />
          <div
            className="h-full bg-bearish transition-all"
            style={{ width: `${100 - buyPct}%` }}
          />
        </div>

        {/* Filter */}
        <div className="px-2 py-1 border-b border-line-subtle flex items-center gap-2 text-2xs text-fg-dim">
          <Filter className="h-3 w-3" />
          <span>Min Size</span>
          <input
            type="range"
            min={0}
            max={Math.max(5000, maxSize / 2)}
            step={500}
            value={minSize}
            onChange={(e) => setMinSize(Number(e.target.value))}
            className="flex-1 max-w-[120px] accent-brand"
          />
          <span className="font-mono num text-fg">{formatNumber(minSize)}</span>
          <span className="ml-auto">
            {visible.length}/{trades.length} prints
          </span>
        </div>

        {/* Table */}
        <div className="flex-1 min-h-0 overflow-auto">
          <table className="w-full text-2xs">
            <thead className="sticky top-0 bg-bg-2 z-10">
              <tr className="text-fg-dim uppercase tracking-wider text-[10px]">
                <th className="px-2 py-1 text-left">Time</th>
                <th className="px-2 py-1 text-left">Side</th>
                <th className="px-2 py-1 text-right">Price</th>
                <th className="px-2 py-1 text-right">Size</th>
                <th className="px-2 py-1 text-left">Cond</th>
                <th className="px-2 py-1 text-left">Exch</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((t) => {
                const intensity = Math.min(1, t.size / maxSize)
                const bg = t.side === 'BUY' ? 'rgba(34,197,94,0.06)' : 'rgba(239,68,68,0.06)'
                return (
                  <tr
                    key={t.id}
                    className="border-b border-line-subtle/30"
                    style={{ background: `${bg}${Math.round(intensity * 60).toString(16).padStart(2, '0')}` }}
                  >
                    <td className="px-2 py-1 font-mono num text-fg-muted">
                      {formatTime(t.timestamp, true)}
                    </td>
                    <td className="px-2 py-1">
                      <span
                        className={cn(
                          'inline-flex items-center gap-0.5 px-1 py-0.5 rounded text-[10px] font-semibold',
                          t.side === 'BUY'
                            ? 'bg-bullish/20 text-bullish'
                            : 'bg-bearish/20 text-bearish',
                        )}
                      >
                        {t.side === 'BUY' ? (
                          <TrendingUp className="h-2.5 w-2.5" />
                        ) : (
                          <TrendingDown className="h-2.5 w-2.5" />
                        )}
                      </span>
                    </td>
                    <td
                      className={cn(
                        'px-2 py-1 text-right font-mono num font-semibold',
                        t.side === 'BUY' ? 'text-bullish' : 'text-bearish',
                      )}
                    >
                      {formatIN(t.price)}
                    </td>
                    <td className="px-2 py-1 text-right font-mono num">
                      <div className="flex items-center justify-end gap-1.5">
                        <div className="flex-1 h-1.5 max-w-[60px] bg-bg-3 rounded overflow-hidden">
                          <div
                            className={cn(
                              'h-full',
                              t.side === 'BUY' ? 'bg-bullish' : 'bg-bearish',
                            )}
                            style={{ width: `${intensity * 100}%` }}
                          />
                        </div>
                        <span className="min-w-[50px] text-right">
                          {formatNumber(t.size)}
                        </span>
                      </div>
                    </td>
                    <td className="px-2 py-1">
                      {t.condition === 'SWEEP' && (
                        <span className="inline-flex items-center gap-0.5 px-1 py-0.5 rounded bg-accent/20 text-accent text-[10px] font-semibold">
                          <Zap className="h-2.5 w-2.5" /> SWEEP
                        </span>
                      )}
                      {t.condition === 'BLOCK' && (
                        <span className="inline-flex items-center gap-0.5 px-1 py-0.5 rounded bg-warning/20 text-warning text-[10px] font-semibold">
                          <AlertCircle className="h-2.5 w-2.5" /> BLOCK
                        </span>
                      )}
                      {t.condition === 'LARGE' && (
                        <span className="inline-flex items-center gap-0.5 px-1 py-0.5 rounded bg-info/20 text-info text-[10px] font-semibold">
                          LARGE
                        </span>
                      )}
                    </td>
                    <td className="px-2 py-1 text-fg-muted text-[10px]">{t.exchange}</td>
                  </tr>
                )
              })}
              {visible.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-2 py-6 text-center text-fg-dim text-xs">
                    No trades match current size filter
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </WidgetFrame>
  )
}
