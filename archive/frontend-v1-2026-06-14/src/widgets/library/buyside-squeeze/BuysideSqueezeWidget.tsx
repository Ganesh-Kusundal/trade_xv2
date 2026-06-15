/**
 * Buyside Squeeze Widget
 *
 * Detects aggressive buy-side volume hitting the ask (lifting the offer).
 * Renders trade "bubbles" sized by aggressive volume and price, similar
 * to the DeepCharts screenshot.
 *
 * Reference: https://www.deepcharts.com/features/buyside-squeeze
 */

import { useEffect, useState } from 'react'
import { WidgetFrame } from '../../WidgetFrame'
import type { WidgetProps } from '../../Widget'
import { cn, formatIN, formatNumber } from '@/lib/utils'
import { generateSqueezeBubbles, type SqueezeBubble } from '@/services/deepchartsData'
import { TrendingUp, TrendingDown, Sparkles, Activity } from 'lucide-react'

interface BuysideSqueezeConfig {
  symbol?: string
  count?: number
  title?: string
}

export default function BuysideSqueezeWidget({
  config,
  refresh,
  loading,
  lastUpdated,
}: WidgetProps<BuysideSqueezeConfig>) {
  const symbol = config.symbol || 'NIFTY'
  const count = config.count || 50
  const [bubbles, setBubbles] = useState<SqueezeBubble[]>([])

  useEffect(() => {
    setBubbles(generateSqueezeBubbles(symbol, count))
    const id = window.setInterval(() => {
      setBubbles(generateSqueezeBubbles(symbol, count))
    }, 3000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, count])

  if (bubbles.length === 0) {
    return (
      <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
        <div className="p-4 text-center text-fg-muted text-xs">Scanning…</div>
      </WidgetFrame>
    )
  }

  const buyBubbles = bubbles.filter((b) => b.side === 'BUY')
  const totalAgg = buyBubbles.reduce((s, b) => s + b.aggregation, 0)
  const totalSize = buyBubbles.reduce((s, b) => s + b.size, 0)
  const maxSize = Math.max(...buyBubbles.map((b) => b.size), 1)
  const maxPrice = Math.max(...buyBubbles.map((b) => b.price), 0)
  const minPrice = Math.min(...buyBubbles.map((b) => b.price), maxPrice)
  const priceRange = maxPrice - minPrice || 1

  return (
    <WidgetFrame
      id=""
      config={{ ...config, title: `BUYSIDE SQUEEZE - ${symbol}` }}
      loading={loading}
      lastUpdated={lastUpdated}
      refresh={() => {
        setBubbles(generateSqueezeBubbles(symbol, count))
        refresh()
      }}
    >
      <div className="flex flex-col h-full">
        {/* Header stats */}
        <div className="px-2 py-1.5 border-b border-line bg-bg-2/40 grid grid-cols-4 gap-2 text-2xs">
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px] flex items-center gap-1">
              <Sparkles className="h-3 w-3 text-accent" /> Bubbles
            </div>
            <div className="font-mono num text-accent font-semibold">{buyBubbles.length}</div>
          </div>
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px] flex items-center gap-1">
              <Activity className="h-3 w-3" /> Total Aggr
            </div>
            <div className="font-mono num text-bullish font-semibold">{formatNumber(totalAgg)}</div>
          </div>
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px]">Total Vol</div>
            <div className="font-mono num text-fg font-semibold">{formatNumber(totalSize)}</div>
          </div>
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px]">Range</div>
            <div className="font-mono num text-fg-muted">
              {formatIN(minPrice)} – {formatIN(maxPrice)}
            </div>
          </div>
        </div>

        {/* Bubble visualization */}
        <div className="flex-1 min-h-0 relative p-2">
          <div className="relative h-full bg-bg-2/20 rounded">
            {/* Price axis labels */}
            <div className="absolute left-0 top-0 bottom-0 w-[60px] flex flex-col justify-between py-2 text-[9px] text-fg-dim font-mono num">
              <span>{formatIN(maxPrice)}</span>
              <span>{formatIN((maxPrice + minPrice) / 2)}</span>
              <span>{formatIN(minPrice)}</span>
            </div>

            {/* Bubbles */}
            <div className="absolute left-[60px] right-0 top-0 bottom-0">
              {buyBubbles.map((b, i) => {
                const xPct = ((i + 0.5) / buyBubbles.length) * 100 + (Math.random() - 0.5) * 3
                const yPct = ((maxPrice - b.price) / priceRange) * 100
                const r = 6 + Math.sqrt(b.size / maxSize) * 28
                const isLarge = b.size > maxSize * 0.6
                return (
                  <div
                    key={b.id}
                    className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full flex items-center justify-center font-mono num transition-all"
                    style={{
                      left: `${Math.max(2, Math.min(98, xPct))}%`,
                      top: `${Math.max(5, Math.min(95, yPct))}%`,
                      width: `${r * 2}px`,
                      height: `${r * 2}px`,
                      background: isLarge
                        ? 'radial-gradient(circle, rgba(34,197,94,0.5) 0%, rgba(34,197,94,0.15) 60%, transparent 100%)'
                        : 'radial-gradient(circle, rgba(168,85,247,0.4) 0%, rgba(168,85,247,0.1) 60%, transparent 100%)',
                      border: isLarge ? '2px solid rgb(34,197,94)' : '1.5px solid rgb(168,85,247)',
                      boxShadow: isLarge
                        ? '0 0 20px rgba(34,197,94,0.4)'
                        : '0 0 12px rgba(168,85,247,0.3)',
                      color: isLarge ? 'rgb(34,197,94)' : 'rgb(168,85,247)',
                      fontSize: `${Math.max(8, r / 2.5)}px`,
                      fontWeight: 600,
                    }}
                    title={`Aggressive: ${formatNumber(b.size)} @ ${formatIN(b.price)} (${b.aggregation} prints)`}
                  >
                    {b.aggregation}({b.size > 1000 ? `${Math.round(b.size / 1000)}k` : b.size})
                  </div>
                )
              })}

              {/* Connecting line — price trend */}
              <svg className="absolute inset-0 w-full h-full pointer-events-none" preserveAspectRatio="none">
                <polyline
                  points={buyBubbles
                    .map((b, i) => {
                      const xPct = ((i + 0.5) / buyBubbles.length) * 100
                      const yPct = ((maxPrice - b.price) / priceRange) * 100
                      return `${xPct},${yPct}`
                    })
                    .join(' ')}
                  fill="none"
                  stroke="rgb(34,197,94)"
                  strokeWidth="1"
                  strokeOpacity="0.4"
                />
              </svg>
            </div>
          </div>
        </div>

        {/* Top bubbles list */}
        <div className="px-2 py-1.5 border-t border-line bg-bg-2/30">
          <div className="text-[10px] text-fg-dim uppercase tracking-wider mb-1">Top Aggregations</div>
          <div className="space-y-0.5">
            {buyBubbles
              .slice()
              .sort((a, b) => b.aggregation - a.aggregation)
              .slice(0, 4)
              .map((b) => (
                <div
                  key={b.id}
                  className="flex items-center gap-2 text-2xs"
                >
                  <div
                    className="h-1.5 w-1.5 rounded-full bg-accent"
                  />
                  <span className="font-mono num text-fg-muted">
                    {formatIN(b.price)}
                  </span>
                  <span className="font-mono num text-accent font-semibold">
                    ×{b.aggregation}
                  </span>
                  <span className="font-mono num text-bullish">
                    {formatNumber(b.size)}
                  </span>
                  <span className="ml-auto font-mono num text-fg-dim">
                    {b.trigger.toFixed(2)}x threshold
                  </span>
                </div>
              ))}
          </div>
        </div>
      </div>
    </WidgetFrame>
  )
}
