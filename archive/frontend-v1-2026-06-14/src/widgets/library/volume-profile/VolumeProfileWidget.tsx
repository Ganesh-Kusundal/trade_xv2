/**
 * Volume Profile Widget — POC / HVN / LVN
 *
 * Horizontal volume profile rendered as a side histogram:
 *   - POC (Point of Control) — row with highest volume
 *   - HVN (High Volume Nodes) — strong support/resistance magnets
 *   - LVN (Low Volume Nodes) — price moves fast through these
 *   - Value Area (70% of volume)
 *   - Per-level buy/sell split shown in stacked bars
 *
 * Reference: https://www.deepcharts.com/features/volume-profile
 */

import { useEffect, useState } from 'react'
import { WidgetFrame } from '../../WidgetFrame'
import type { WidgetProps } from '../../Widget'
import { cn, formatIN, formatNumber } from '@/lib/utils'
import { generateVolumeProfile, type VolumeProfileData } from '@/services/deepchartsData'
import { Target, TrendingUp, TrendingDown, Layers } from 'lucide-react'

interface VolumeProfileConfig {
  symbol?: string
  levels?: number
  title?: string
  side?: 'left' | 'right' | 'center'
}

export default function VolumeProfileWidget({
  config,
  refresh,
  loading,
  lastUpdated,
}: WidgetProps<VolumeProfileConfig>) {
  const symbol = config.symbol || 'NIFTY'
  const levels = config.levels || 30
  const side = config.side || 'right'
  const [data, setData] = useState<VolumeProfileData | null>(null)

  useEffect(() => {
    setData(generateVolumeProfile(symbol, levels))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, levels])

  if (!data) {
    return (
      <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
        <div className="p-4 text-center text-fg-muted text-xs">Building profile…</div>
      </WidgetFrame>
    )
  }

  const maxVol = Math.max(...data.levels.map((l) => l.volume))

  return (
    <WidgetFrame
      id=""
      config={{ ...config, title: `VOL PROFILE - ${symbol}` }}
      loading={loading}
      lastUpdated={lastUpdated}
      refresh={() => {
        setData(generateVolumeProfile(symbol, levels))
        refresh()
      }}
    >
      <div className="flex flex-col h-full">
        {/* Header — POC / VAH / VAL */}
        <div className="px-2 py-1.5 border-b border-line bg-bg-2/40 grid grid-cols-3 gap-2 text-2xs">
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px] flex items-center gap-1">
              <Target className="h-3 w-3 text-warning" /> POC
            </div>
            <div className="font-mono num text-warning font-semibold">{formatIN(data.poc)}</div>
          </div>
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px] flex items-center gap-1">
              <TrendingUp className="h-3 w-3 text-bearish" /> VAH
            </div>
            <div className="font-mono num text-bearish font-semibold">{formatIN(data.vah)}</div>
          </div>
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px] flex items-center gap-1">
              <TrendingDown className="h-3 w-3 text-bullish" /> VAL
            </div>
            <div className="font-mono num text-bullish font-semibold">{formatIN(data.val)}</div>
          </div>
        </div>

        {/* Profile rows */}
        <div className="flex-1 min-h-0 overflow-auto">
          {data.levels
            .slice()
            .reverse()
            .map((lvl) => {
              const barW = (lvl.volume / maxVol) * 100
              const buyPct = (lvl.buyVolume / lvl.volume) * 100
              return (
                <div
                  key={lvl.price}
                  className={cn(
                    'grid grid-cols-[1fr_70px_1fr] items-center text-[10px] font-mono num h-[18px] border-b border-line-subtle/30 relative',
                    lvl.type === 'POC' && 'bg-warning/8',
                    lvl.type === 'HVN' && 'bg-info/5',
                    lvl.type === 'LVN' && 'bg-bg-2/30',
                  )}
                >
                  {/* Left rail (or just label, depending on side) */}
                  {side === 'left' || side === 'center' ? (
                    <div className="relative h-full flex items-center justify-end">
                      {side === 'left' && (
                        <div
                          className="h-full bg-info/25"
                          style={{ width: `${barW}%` }}
                        />
                      )}
                      {side === 'center' && (
                        <div
                          className="h-full bg-info/20"
                          style={{ width: `${barW / 2}%` }}
                        />
                      )}
                    </div>
                  ) : (
                    <div />
                  )}

                  {/* Price label */}
                  <div
                    className={cn(
                      'text-center relative z-10 px-1',
                      lvl.type === 'POC' && 'text-warning font-semibold',
                      lvl.type === 'HVN' && 'text-info',
                      lvl.type === 'LVN' && 'text-fg-dim',
                      lvl.type === 'NORMAL' && 'text-fg-muted',
                    )}
                  >
                    {lvl.type === 'POC' && (
                      <span className="inline-block w-1.5 h-1.5 rounded-full bg-warning mr-1 align-middle" />
                    )}
                    {lvl.type === 'HVN' && (
                      <span className="inline-block w-1.5 h-1.5 rounded-full bg-info mr-1 align-middle" />
                    )}
                    {lvl.type === 'LVN' && (
                      <span className="inline-block w-1.5 h-1.5 rounded-full bg-fg-dim mr-1 align-middle" />
                    )}
                    {formatIN(lvl.price)}
                  </div>

                  {/* Right rail */}
                  {side === 'right' || side === 'center' ? (
                    <div className="relative h-full flex items-center">
                      {side === 'right' && (
                        <div
                          className="h-full bg-accent/30 relative"
                          style={{ width: `${barW}%` }}
                        >
                          {/* Buy/sell split inside the bar */}
                          <div
                            className="absolute inset-y-0 left-0 bg-bullish/60"
                            style={{ width: `${buyPct}%` }}
                          />
                          <span className="absolute inset-0 flex items-center pl-1 text-[9px] text-fg">
                            {formatNumber(lvl.volume)}
                          </span>
                        </div>
                      )}
                      {side === 'center' && (
                        <div
                          className="h-full bg-accent/30 relative"
                          style={{ width: `${barW / 2}%` }}
                        >
                          <div
                            className="absolute inset-y-0 left-0 bg-bullish/60"
                            style={{ width: `${buyPct}%` }}
                          />
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-fg-dim text-[9px] pl-1">{formatNumber(lvl.volume)}</div>
                  )}
                </div>
              )
            })}
        </div>

        {/* Legend */}
        <div className="px-2 py-1.5 border-t border-line bg-bg-2/30 flex items-center justify-between text-[10px] text-fg-dim">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-warning" /> POC
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-info" /> HVN
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-fg-dim" /> LVN
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-bullish" /> Buy
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-accent" /> Sell
            </span>
          </div>
          <div className="flex items-center gap-1">
            <Layers className="h-3 w-3" /> Total: {formatNumber(data.totalVolume)}
          </div>
        </div>
      </div>
    </WidgetFrame>
  )
}
