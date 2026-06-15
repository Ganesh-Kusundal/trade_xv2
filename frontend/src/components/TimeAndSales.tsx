/**
 * TimeAndSales — live trade tape (a.k.a. "the tape" / "Time & Sales").
 *
 * Streams individual trades colour-coded by aggressor side, with
 * condition flags (BLOCK / SWEEP / LARGE) and a cumulative delta
 * summary at the bottom.
 */

import { useEffect, useMemo, useState } from 'react'
import { Activity, ArrowDown, ArrowUp, Filter, Zap, AlertCircle, Box } from 'lucide-react'
import { generateTrades, type Trade } from '@/data/orderflow'
import { cn, formatIN, formatNumber, formatTime, pnlColor } from '@/lib/utils'

interface TimeAndSalesProps {
  symbol: string
  height?: number
}

export function TimeAndSales({ symbol, height = 360 }: TimeAndSalesProps) {
  const [trades, setTrades] = useState<Trade[]>([])
  const [minSize, setMinSize] = useState(0)
  const [highlightBlocks, setHighlightBlocks] = useState(true)

  useEffect(() => {
    setTrades(generateTrades(symbol, 60))
    const id = window.setInterval(() => {
      setTrades((prev) => {
        const fresh = generateTrades(symbol, 5)
        return [...fresh, ...prev].slice(0, 80)
      })
    }, 800)
    return () => clearInterval(id)
  }, [symbol])

  const visible = useMemo(() => trades.filter((t) => t.size >= minSize), [trades, minSize])
  const stats = useMemo(() => {
    const buy = visible.filter((t) => t.side === 'BUY').reduce((s, t) => s + t.size, 0)
    const sell = visible.filter((t) => t.side === 'SELL').reduce((s, t) => s + t.size, 0)
    const total = buy + sell
    return {
      buy, sell, total,
      delta: buy - sell,
      buyPct: total ? (buy / total) * 100 : 50,
      blocks: visible.filter((t) => t.condition === 'BLOCK').length,
      sweeps: visible.filter((t) => t.condition === 'SWEEP').length,
      largest: visible.reduce((m, t) => Math.max(m, t.size), 0),
    }
  }, [visible])

  return (
    <div className="flex flex-col b-panel rounded-sm overflow-hidden" style={{ height }}>
      {/* Header */}
      <div className="flex items-center justify-between px-2 py-1 border-b border-bline bg-bbg2">
        <div className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wider">
          <Activity className="h-3 w-3 text-bcy" />
          <span>Time &amp; Sales</span>
        </div>
        <span className="text-[10px] text-bfgd font-mono num">{visible.length}/{trades.length}</span>
      </div>

      {/* Stats strip */}
      <div className="grid grid-cols-3 border-b border-bline text-2xs">
        <div className="px-2 py-1 border-r border-bline">
          <div className="text-fg-dim text-[10px] uppercase tracking-wider">Buy</div>
          <div className="font-mono num text-bull font-semibold">{formatNumber(stats.buy)}</div>
        </div>
        <div className="px-2 py-1 border-r border-bline">
          <div className="text-fg-dim text-[10px] uppercase tracking-wider">Sell</div>
          <div className="font-mono num text-bear font-semibold">{formatNumber(stats.sell)}</div>
        </div>
        <div className="px-2 py-1">
          <div className="text-fg-dim text-[10px] uppercase tracking-wider">Δ Delta</div>
          <div className={cn('font-mono num font-semibold', pnlColor(stats.delta))}>
            {stats.delta >= 0 ? '+' : ''}{formatNumber(stats.delta)}
          </div>
        </div>
      </div>

      {/* Buy/sell bar */}
      <div className="h-1 flex">
        <div className="bg-bull transition-all" style={{ width: `${stats.buyPct}%` }} />
        <div className="bg-bear transition-all" style={{ width: `${100 - stats.buyPct}%` }} />
      </div>

      {/* Filter */}
      <div className="flex items-center gap-1.5 px-2 py-1 border-b border-bline text-2xs text-bfgd">
        <Filter className="h-3 w-3" />
        <span className="font-mono">min</span>
        <input
          type="range"
          min={0}
          max={Math.max(1000, stats.largest / 2)}
          step={100}
          value={minSize}
          onChange={(e) => setMinSize(Number(e.target.value))}
          className="flex-1 max-w-[100px] accent-bcy"
        />
        <span className="font-mono num text-fg">{formatNumber(minSize)}</span>
        <button
          onClick={() => setHighlightBlocks((v) => !v)}
          className={cn(
            'h-5 px-1.5 text-[10px] rounded-sm border',
            highlightBlocks
              ? 'bg-warning/15 border-warning/30 text-warning'
              : 'bg-bbg2 border-bline text-bfgm',
          )}
          title="Highlight BLOCK / SWEEP prints"
        >
          <Zap className="h-2.5 w-2.5" />
        </button>
      </div>

      {/* Table */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        <table className="w-full text-2xs font-mono num">
          <thead className="sticky top-0 bg-bbg2 text-fg-dim text-[10px] uppercase tracking-wider">
            <tr>
              <th className="px-2 py-0.5 text-left">Time</th>
              <th className="px-1 py-0.5 text-left w-4"></th>
              <th className="px-1 py-0.5 text-right">Price</th>
              <th className="px-1 py-0.5 text-right">Size</th>
              <th className="px-2 py-0.5 text-left">Cond</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((t) => (
              <tr
                key={t.id}
                className={cn(
                  'border-b border-bline-subtle/40 hover:bg-bbg2',
                  t.side === 'BUY' ? 'text-bull' : 'text-bear',
                )}
                style={{ background: t.side === 'BUY' ? 'rgba(34,197,94,0.04)' : 'rgba(239,68,68,0.04)' }}
              >
                <td className="px-2 py-0.5 text-fg-muted">{formatTime(t.t, true)}</td>
                <td className="px-1 py-0.5">
                  {t.side === 'BUY' ? <ArrowUp className="h-2.5 w-2.5" /> : <ArrowDown className="h-2.5 w-2.5" />}
                </td>
                <td className="px-1 py-0.5 text-right font-semibold">{formatIN(t.price)}</td>
                <td className="px-1 py-0.5 text-right">{formatNumber(t.size)}</td>
                <td className="px-2 py-0.5">
                  {t.condition === 'BLOCK' && highlightBlocks && (
                    <span className="inline-flex items-center gap-0.5 px-1 rounded bg-warning/20 text-warning text-[10px]">
                      <Box className="h-2.5 w-2.5" />BLK
                    </span>
                  )}
                  {t.condition === 'SWEEP' && highlightBlocks && (
                    <span className="inline-flex items-center gap-0.5 px-1 rounded bg-accent/20 text-accent text-[10px]">
                      <Zap className="h-2.5 w-2.5" />SWP
                    </span>
                  )}
                  {t.condition === 'LARGE' && highlightBlocks && (
                    <span className="inline-flex items-center gap-0.5 px-1 rounded bg-info/20 text-info text-[10px]">
                      <AlertCircle className="h-2.5 w-2.5" />LRG
                    </span>
                  )}
                </td>
              </tr>
            ))}
            {visible.length === 0 && (
              <tr>
                <td colSpan={5} className="px-2 py-4 text-center text-fg-dim">
                  No trades match filter
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Footer with sweep/block counts */}
      <div className="px-2 py-1 border-t border-bline bg-bbg2 flex items-center justify-between text-[10px] text-fg-dim font-mono num">
        <span className="flex items-center gap-2">
          <span className="flex items-center gap-0.5"><Zap className="h-2.5 w-2.5 text-accent" />{stats.sweeps} sweep</span>
          <span className="flex items-center gap-0.5"><Box className="h-2.5 w-2.5 text-warning" />{stats.blocks} block</span>
        </span>
        <span>max {formatNumber(stats.largest)}</span>
      </div>
    </div>
  )
}
