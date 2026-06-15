/**
 * TPO Profile Widget — Time-Price-Opportunity / Market Profile
 *
 * Each 30-minute period is assigned a letter (A, B, C, ...). At each
 * price level, the letters that "printed" at that price are stacked.
 * The result is a market profile showing:
 *   - POC (price with the most letters)
 *   - Value Area (70% of letters)
 *   - Single prints (zones with only 1-2 letters — price moved fast)
 *   - Poor high / poor low (single-letter extremes)
 *
 * Reference: https://www.deepcharts.com/features/improved-tpo
 */

import { useEffect, useState } from 'react'
import { WidgetFrame } from '../../WidgetFrame'
import type { WidgetProps } from '../../Widget'
import { cn, formatIN } from '@/lib/utils'
import { generateTPOProfile, type TPOProfileData } from '@/services/deepchartsData'
import { Target, TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react'

interface TPOProfileConfig {
  symbol?: string
  levels?: number
  periods?: number
  title?: string
}

export default function TPOProfileWidget({
  config,
  refresh,
  loading,
  lastUpdated,
}: WidgetProps<TPOProfileConfig>) {
  const symbol = config.symbol || 'NIFTY'
  const levels = config.levels || 24
  const periods = config.periods || 13
  const [data, setData] = useState<TPOProfileData | null>(null)

  useEffect(() => {
    setData(generateTPOProfile(symbol, levels, periods))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, levels, periods])

  if (!data) {
    return (
      <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
        <div className="p-4 text-center text-fg-muted text-xs">Building TPO…</div>
      </WidgetFrame>
    )
  }

  return (
    <WidgetFrame
      id=""
      config={{ ...config, title: `TPO PROFILE - ${symbol}` }}
      loading={loading}
      lastUpdated={lastUpdated}
      refresh={() => {
        setData(generateTPOProfile(symbol, levels, periods))
        refresh()
      }}
    >
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className="px-2 py-1.5 border-b border-line bg-bg-2/40 grid grid-cols-4 gap-2 text-2xs">
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
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px] flex items-center gap-1">
              <AlertTriangle className="h-3 w-3 text-info" /> Singleprints
            </div>
            <div className="font-mono num text-info font-semibold">
              {data.singlePrintZones.length}
            </div>
          </div>
        </div>

        {/* Period markers */}
        <div className="px-2 py-1 border-b border-line-subtle flex items-center gap-1 overflow-x-auto">
          {Array.from({ length: data.periodCount }).map((_, i) => (
            <div
              key={i}
              className="flex flex-col items-center min-w-[24px] text-[9px] text-fg-dim"
            >
              <div className="font-mono num font-semibold text-fg">
                {String.fromCharCode(65 + i)}
              </div>
              <div className="font-mono num">
                {9 + Math.floor(i / 2)}:{i % 2 === 0 ? '15' : '45'}
              </div>
            </div>
          ))}
        </div>

        {/* TPO rows (top to bottom = high to low) */}
        <div className="flex-1 min-h-0 overflow-auto">
          {data.levels
            .slice()
            .reverse()
            .map((lvl) => {
              const isPOC = lvl.price === data.poc
              const isVAH = lvl.price === data.vah
              const isVAL = lvl.price === data.val
              const inVA = lvl.price >= data.val && lvl.price <= data.vah
              return (
                <div
                  key={lvl.price}
                  className={cn(
                    'flex items-center px-2 h-[18px] text-[10px] font-mono num border-b border-line-subtle/30',
                    isPOC && 'bg-warning/8',
                    !isPOC && isVAH && 'bg-bearish/8',
                    !isPOC && isVAL && 'bg-bullish/8',
                    !isPOC && !isVAH && !isVAL && inVA && 'bg-info/3',
                    lvl.isSinglePrint && 'bg-accent/5',
                  )}
                >
                  {/* Price */}
                  <div
                    className={cn(
                      'w-[60px] flex-shrink-0',
                      isPOC && 'text-warning font-semibold',
                      !isPOC && isVAH && 'text-bearish font-semibold',
                      !isPOC && isVAL && 'text-bullish font-semibold',
                      !isPOC && !isVAH && !isVAL && 'text-fg-muted',
                    )}
                  >
                    {formatIN(lvl.price)}
                  </div>

                  {/* TPO letters */}
                  <div className="flex-1 flex items-center gap-[2px]">
                    {lvl.letters.map((letter, i) => (
                      <span
                        key={i}
                        className={cn(
                          'inline-block min-w-[12px] text-center font-mono num text-[10px] px-0.5',
                          lvl.isSinglePrint
                            ? 'text-accent font-semibold'
                            : isPOC
                              ? 'text-warning font-semibold'
                              : 'text-info/90',
                        )}
                        title={`Period ${letter}`}
                      >
                        {letter}
                      </span>
                    ))}
                    {lvl.count === 0 && (
                      <span className="text-fg-dim text-[9px]">—</span>
                    )}
                  </div>

                  {/* Letter count */}
                  <div className="w-[40px] text-right text-fg-dim text-[10px] flex-shrink-0">
                    {lvl.count > 0 && (
                      <span
                        className={cn(
                          'inline-block px-1 py-0.5 rounded text-[9px]',
                          isPOC
                            ? 'bg-warning/20 text-warning'
                            : lvl.isSinglePrint
                              ? 'bg-accent/20 text-accent'
                              : 'bg-bg-3 text-fg-muted',
                        )}
                      >
                        ×{lvl.count}
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
        </div>

        {/* Footer */}
        <div className="px-2 py-1.5 border-t border-line bg-bg-2/30 flex items-center justify-between text-[10px] text-fg-dim">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-warning" /> POC
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-info/50" /> Value Area
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-accent" /> Single Print
            </span>
            {data.poorHigh && (
              <span className="flex items-center gap-1 text-warning">
                <AlertTriangle className="h-3 w-3" /> Poor High
              </span>
            )}
            {data.poorLow && (
              <span className="flex items-center gap-1 text-warning">
                <AlertTriangle className="h-3 w-3" /> Poor Low
              </span>
            )}
          </div>
          <div className="font-mono num">{data.periodCount} periods</div>
        </div>
      </div>
    </WidgetFrame>
  )
}
