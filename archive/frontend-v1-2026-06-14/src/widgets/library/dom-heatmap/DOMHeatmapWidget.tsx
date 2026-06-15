/**
 * DOM Heatmap Widget — Orderbook Density Heatmap
 *
 * Renders the DOM as a 2D heatmap with:
 *   - Bid / ask intensity per price level (size + persistence)
 *   - "Stable & Persistent Passive Clusters" — high stability zones
 *   - "Low-Slippage Execution Zones" — deep liquidity
 *   - "Reliable Test of Levels" — historically tested & held
 *   - "Natural Price Magnets" — strong, persistent levels
 *
 * Reference: https://www.deepcharts.com/features/deepdom
 */

import { useEffect, useState } from 'react'
import { WidgetFrame } from '../../WidgetFrame'
import type { WidgetProps } from '../../Widget'
import { cn, formatIN, formatNumber } from '@/lib/utils'
import { generateDOMHeatmap, type DOMHeatmapData } from '@/services/deepchartsData'
import { Magnet, Layers, Target, ShieldCheck, Zap } from 'lucide-react'

interface DOMHeatmapConfig {
  symbol?: string
  levels?: number
  title?: string
}

export default function DOMHeatmapWidget({
  config,
  refresh,
  loading,
  lastUpdated,
}: WidgetProps<DOMHeatmapConfig>) {
  const symbol = config.symbol || 'NIFTY'
  const levels = config.levels || 20
  const [data, setData] = useState<DOMHeatmapData | null>(null)

  useEffect(() => {
    setData(generateDOMHeatmap(symbol, levels))
    const id = window.setInterval(() => {
      setData(generateDOMHeatmap(symbol, levels))
    }, 2000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, levels])

  if (!data) {
    return (
      <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
        <div className="p-4 text-center text-fg-muted text-xs">Loading heatmap…</div>
      </WidgetFrame>
    )
  }

  // Sort by price descending
  const sorted = data.cells.slice().sort((a, b) => b.price - a.price)
  const totalBid = data.cells.reduce((s, c) => s + c.bidSize, 0)
  const totalAsk = data.cells.reduce((s, c) => s + c.askSize, 0)
  const magnetCount = data.magnets.length
  const reliableTestCount = data.cells.filter((c) => c.reliableTest).length
  const lowSlippageCount = data.cells.filter((c) => c.lowSlippage).length

  return (
    <WidgetFrame
      id=""
      config={{ ...config, title: `DOM HEATMAP - ${symbol}` }}
      loading={loading}
      lastUpdated={lastUpdated}
      refresh={() => {
        setData(generateDOMHeatmap(symbol, levels))
        refresh()
      }}
    >
      <div className="flex flex-col h-full">
        {/* Header stats */}
        <div className="px-2 py-1.5 border-b border-line bg-bg-2/40 grid grid-cols-4 gap-2 text-2xs">
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px] flex items-center gap-1">
              <Magnet className="h-3 w-3 text-accent" /> Magnets
            </div>
            <div className="font-mono num text-accent font-semibold">{magnetCount}</div>
          </div>
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px] flex items-center gap-1">
              <ShieldCheck className="h-3 w-3 text-bullish" /> Reliable Tests
            </div>
            <div className="font-mono num text-bullish font-semibold">{reliableTestCount}</div>
          </div>
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px] flex items-center gap-1">
              <Zap className="h-3 w-3 text-info" /> Low-Slippage
            </div>
            <div className="font-mono num text-info font-semibold">{lowSlippageCount}</div>
          </div>
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px]">Mid</div>
            <div className="font-mono num text-fg font-semibold">{formatIN(data.midPrice)}</div>
          </div>
        </div>

        {/* Heatmap column labels */}
        <div className="grid grid-cols-[1fr_60px_1fr] text-[9px] text-fg-dim uppercase tracking-wider px-1 py-1 border-b border-line-subtle">
          <div className="text-right">Bid Heat</div>
          <div className="text-center">Price</div>
          <div className="text-left">Ask Heat</div>
        </div>

        {/* Heatmap rows */}
        <div className="flex-1 min-h-0 overflow-auto">
          {sorted.map((cell) => {
            const isAboveMid = cell.price > data.midPrice
            return (
              <div
                key={cell.price}
                className={cn(
                  'grid grid-cols-[1fr_60px_1fr] items-center text-[10px] font-mono num h-[20px] border-b border-line-subtle/20 relative',
                  cell.isMagnet && 'bg-accent/8 ring-1 ring-accent/30',
                )}
              >
                {/* Bid cell */}
                <div className="text-right relative h-full flex items-center justify-end">
                  <div
                    className="absolute inset-y-0 right-0"
                    style={{
                      width: `${cell.bidHeat * 100}%`,
                      background: `linear-gradient(90deg, transparent 0%, rgba(34,197,94,${cell.bidHeat * 0.6}) 100%)`,
                    }}
                  />
                  {cell.bidStability > 0.7 && (
                    <span
                      className="absolute top-1/2 right-1 -translate-y-1/2 h-1.5 w-1.5 rounded-full bg-bullish"
                      title="Stable passive cluster"
                    />
                  )}
                  <span className="relative text-bullish pr-1">
                    {cell.bidSize > 0 ? formatNumber(cell.bidSize) : ''}
                  </span>
                </div>

                {/* Price */}
                <div
                  className={cn(
                    'text-center relative z-10 px-1 font-semibold',
                    isAboveMid ? 'text-bearish' : 'text-bullish',
                    cell.isMagnet && 'text-accent',
                  )}
                >
                  {cell.isMagnet && (
                    <Magnet className="inline h-2.5 w-2.5 mr-0.5 -mt-0.5" />
                  )}
                  {formatIN(cell.price)}
                </div>

                {/* Ask cell */}
                <div className="text-left relative h-full flex items-center justify-start">
                  <div
                    className="absolute inset-y-0 left-0"
                    style={{
                      width: `${cell.askHeat * 100}%`,
                      background: `linear-gradient(270deg, transparent 0%, rgba(239,68,68,${cell.askHeat * 0.6}) 100%)`,
                    }}
                  />
                  {cell.askStability > 0.7 && (
                    <span
                      className="absolute top-1/2 left-1 -translate-y-1/2 h-1.5 w-1.5 rounded-full bg-bearish"
                      title="Stable passive cluster"
                    />
                  )}
                  <span className="relative text-bearish pl-1">
                    {cell.askSize > 0 ? formatNumber(cell.askSize) : ''}
                  </span>
                </div>

                {/* Markers overlay */}
                {(cell.reliableTest || cell.lowSlippage || cell.isMagnet) && (
                  <div className="absolute right-1 top-0.5 flex items-center gap-0.5 z-20">
                    {cell.reliableTest && (
                      <span
                        className="h-1.5 w-1.5 rounded-full bg-bullish"
                        title="Reliable test of level"
                      />
                    )}
                    {cell.lowSlippage && (
                      <span
                        className="h-1.5 w-1.5 rounded-full bg-info"
                        title="Low-slippage zone"
                      />
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Footer */}
        <div className="px-2 py-1.5 border-t border-line bg-bg-2/30 flex items-center justify-between text-[10px] text-fg-dim">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <Magnet className="h-3 w-3 text-accent" /> Magnet
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-bullish" /> Stable
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-bullish" /> Reliable Test
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-info" /> Low-Slippage
            </span>
          </div>
          <div className="flex items-center gap-1 font-mono num">
            <Layers className="h-3 w-3" /> B/A: {formatNumber(totalBid)} / {formatNumber(totalAsk)}
          </div>
        </div>
      </div>
    </WidgetFrame>
  )
}
