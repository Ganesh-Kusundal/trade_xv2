/**
 * Initial Balance Widget — IB / VAH / VAL
 *
 * Shows the Initial Balance (first 30 minutes) range with the classic
 * "opening drive" projection lines:
 *   - IB High / IB Low
 *   - IB Mid
 *   - IB Range
 *   - 1x / 2x / 3x extensions of the IB range
 *   - Value Area (VAH / VAL)
 *   - Session progress bar
 *
 * Reference: https://www.deepcharts.com/features/ivb-by-volume
 */

import { useEffect, useState } from 'react'
import { WidgetFrame } from '../../WidgetFrame'
import type { WidgetProps } from '../../Widget'
import { cn, formatIN } from '@/lib/utils'
import { generateInitialBalance, type InitialBalance } from '@/services/deepchartsData'
import { TrendingUp, TrendingDown, BarChart3, Activity } from 'lucide-react'

interface InitialBalanceConfig {
  symbol?: string
  ibMinutes?: number
  title?: string
}

export default function InitialBalanceWidget({
  config,
  refresh,
  loading,
  lastUpdated,
}: WidgetProps<InitialBalanceConfig>) {
  const symbol = config.symbol || 'NIFTY'
  const ibMinutes = config.ibMinutes || 30
  const [data, setData] = useState<InitialBalance | null>(null)
  const [progress, setProgress] = useState(0.45)

  useEffect(() => {
    setData(generateInitialBalance(symbol, ibMinutes))
    const id = window.setInterval(() => {
      setData(generateInitialBalance(symbol, ibMinutes))
      setProgress((p) => Math.min(1, p + 0.005))
    }, 2000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, ibMinutes])

  if (!data) {
    return (
      <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
        <div className="p-4 text-center text-fg-muted text-xs">Loading…</div>
      </WidgetFrame>
    )
  }

  const range = data.ibRange
  const minPrice = data.val - range * 0.5
  const maxPrice = data.vah + range * 0.5
  const total = maxPrice - minPrice
  const priceToY = (p: number) => ((maxPrice - p) / total) * 100

  // All price lines to render
  const lines = [
    { price: data.vah, label: 'VAH', color: 'bg-bearish', textColor: 'text-bearish', dashed: true },
    { price: data.extensions.x3, label: '3x', color: 'bg-accent', textColor: 'text-accent', dashed: true },
    { price: data.extensions.x2, label: '2x', color: 'bg-accent', textColor: 'text-accent', dashed: true },
    { price: data.extensions.x1, label: '1x', color: 'bg-accent', textColor: 'text-accent', dashed: true },
    { price: data.ibHigh, label: 'IBH', color: 'bg-bearish', textColor: 'text-bearish', dashed: false },
    { price: data.ibMid, label: 'IBM', color: 'bg-info', textColor: 'text-info', dashed: true },
    { price: data.ibLow, label: 'IBL', color: 'bg-bullish', textColor: 'text-bullish', dashed: false },
    { price: data.val, label: 'VAL', color: 'bg-bullish', textColor: 'text-bullish', dashed: true },
  ]

  return (
    <WidgetFrame
      id=""
      config={{ ...config, title: `INITIAL BALANCE - ${symbol}` }}
      loading={loading}
      lastUpdated={lastUpdated}
      refresh={() => {
        setData(generateInitialBalance(symbol, ibMinutes))
        refresh()
      }}
    >
      <div className="flex flex-col h-full">
        {/* Header stats */}
        <div className="px-2 py-1.5 border-b border-line bg-bg-2/40 grid grid-cols-4 gap-2 text-2xs">
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px] flex items-center gap-1">
              <BarChart3 className="h-3 w-3" /> IB Range
            </div>
            <div className="font-mono num text-fg font-semibold">{formatIN(range)}</div>
          </div>
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px] flex items-center gap-1">
              <Activity className="h-3 w-3" /> IB Mid
            </div>
            <div className="font-mono num text-info font-semibold">{formatIN(data.ibMid)}</div>
          </div>
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px] flex items-center gap-1">
              <TrendingUp className="h-3 w-3 text-bearish" /> IBH / VAH
            </div>
            <div className="font-mono num text-bearish font-semibold">
              {formatIN(data.ibHigh)} / {formatIN(data.vah)}
            </div>
          </div>
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px] flex items-center gap-1">
              <TrendingDown className="h-3 w-3 text-bullish" /> IBL / VAL
            </div>
            <div className="font-mono num text-bullish font-semibold">
              {formatIN(data.ibLow)} / {formatIN(data.val)}
            </div>
          </div>
        </div>

        {/* Visualization band */}
        <div className="flex-1 min-h-0 relative p-3">
          <div className="relative h-full bg-bg-2/20 rounded">
            {lines.map((line) => (
              <div
                key={line.label}
                className="absolute left-0 right-0 flex items-center pointer-events-none"
                style={{ top: `${priceToY(line.price)}%` }}
              >
                <div
                  className={cn(
                    'h-px flex-1',
                    line.color,
                    line.dashed && 'border-t border-dashed',
                    !line.dashed && 'opacity-80',
                  )}
                  style={line.dashed ? { background: 'transparent', borderTopWidth: '1px', borderTopStyle: 'dashed' } : {}}
                />
                <div
                  className={cn(
                    'px-1.5 py-0.5 rounded text-[10px] font-mono num font-semibold ml-1',
                    line.textColor,
                    'bg-bg-0/80',
                  )}
                >
                  {line.label} {formatIN(line.price)}
                </div>
              </div>
            ))}

            {/* IB fill zone */}
            <div
              className="absolute left-2 right-2 bg-info/5 border-x-2 border-info/30"
              style={{
                top: `${priceToY(data.ibHigh)}%`,
                bottom: `${100 - priceToY(data.ibLow)}%`,
              }}
            >
              <div className="absolute inset-0 flex items-center justify-center text-[10px] text-info font-mono num font-semibold tracking-wider">
                INITIAL BALANCE
              </div>
            </div>
          </div>
        </div>

        {/* Session progress */}
        <div className="px-2 py-1.5 border-t border-line bg-bg-2/30">
          <div className="flex items-center justify-between text-2xs text-fg-dim mb-1">
            <span>Session Progress</span>
            <span className="font-mono num text-fg">{(progress * 100).toFixed(0)}%</span>
          </div>
          <div className="h-1.5 bg-bg-3 rounded overflow-hidden">
            <div
              className="h-full bg-brand transition-all"
              style={{ width: `${progress * 100}%` }}
            />
          </div>
          <div className="grid grid-cols-2 gap-2 mt-2 text-[10px]">
            <div className="flex items-center justify-between bg-bg-2/40 px-2 py-1 rounded">
              <span className="text-fg-dim">IB Period</span>
              <span className="font-mono num text-fg font-semibold">{ibMinutes}m</span>
            </div>
            <div className="flex items-center justify-between bg-bg-2/40 px-2 py-1 rounded">
              <span className="text-fg-dim">Extensions</span>
              <span className="font-mono num text-accent font-semibold">3x active</span>
            </div>
          </div>
        </div>
      </div>
    </WidgetFrame>
  )
}
