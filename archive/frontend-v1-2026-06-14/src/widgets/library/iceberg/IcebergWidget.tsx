/**
 * Iceberg Detector Widget
 *
 * Detects and visualises potential iceberg orders:
 *   - Tracks refill events at each price level
 *   - Estimates hidden / "not in book" iceberg size
 *   - Renders iceberg as floating bubbles overlaid on the price ladder
 *
 * Reference: https://www.deepcharts.com/features/icebergorders
 */

import { useEffect, useMemo, useState } from 'react'
import { WidgetFrame } from '../../WidgetFrame'
import type { WidgetProps } from '../../Widget'
import { cn, formatIN, formatNumber, timeAgo } from '@/lib/utils'
import { generateDeepDOM, type DeepDOMSnapshot } from '@/services/deepchartsData'
import { AlertTriangle, Snowflake, TrendingUp, TrendingDown } from 'lucide-react'

interface IcebergConfig {
  symbol?: string
  levels?: number
  title?: string
  minSize?: number
}

export default function IcebergWidget({
  config,
  refresh,
  loading,
  lastUpdated,
}: WidgetProps<IcebergConfig>) {
  const symbol = config.symbol || 'NIFTY'
  const levels = config.levels || 30
  const minSize = config.minSize || 5000
  const [snap, setSnap] = useState<DeepDOMSnapshot | null>(null)

  useEffect(() => {
    const reload = () => setSnap(generateDeepDOM(symbol, levels))
    reload()
    const id = window.setInterval(reload, 2000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, levels])

  const icebergs = useMemo(() => {
    if (!snap) return []
    const all = [
      ...snap.bids
        .filter((b) => b.icebergSize >= minSize)
        .map((b) => ({ ...b, side: 'BID' as const })),
      ...snap.asks
        .filter((a) => a.icebergSize >= minSize)
        .map((a) => ({ ...a, side: 'ASK' as const })),
    ]
    return all.sort((a, b) => b.icebergSize - a.icebergSize)
  }, [snap, minSize])

  if (!snap) {
    return (
      <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
        <div className="p-4 text-center text-fg-muted text-xs">Scanning…</div>
      </WidgetFrame>
    )
  }

  const totalHidden = icebergs.reduce((s, i) => s + i.icebergSize, 0)
  const buyIcebergs = icebergs.filter((i) => i.side === 'BID')
  const sellIcebergs = icebergs.filter((i) => i.side === 'ASK')
  const totalBidIce = buyIcebergs.reduce((s, i) => s + i.icebergSize, 0)
  const totalAskIce = sellIcebergs.reduce((s, i) => s + i.icebergSize, 0)
  const netIce = totalBidIce - totalAskIce

  // Visualize the price range with iceberg positions
  const minPrice = Math.min(...snap.bids.map((b) => b.price))
  const maxPrice = Math.max(...snap.asks.map((a) => a.price))
  const priceRange = maxPrice - minPrice

  return (
    <WidgetFrame
      id=""
      config={{ ...config, title: `ICEBERGS - ${symbol}` }}
      loading={loading}
      lastUpdated={lastUpdated}
      refresh={() => {
        setSnap(generateDeepDOM(symbol, levels))
        refresh()
      }}
    >
      <div className="flex flex-col h-full">
        {/* Header summary */}
        <div className="px-2 py-1.5 border-b border-line bg-bg-2/40 grid grid-cols-4 gap-2 text-2xs">
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px]">Active</div>
            <div className="font-mono num text-accent font-semibold flex items-center gap-1">
              <AlertTriangle className="h-3 w-3" /> {icebergs.length}
            </div>
          </div>
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px]">Hidden Qty</div>
            <div className="font-mono num text-fg font-semibold">{formatNumber(totalHidden)}</div>
          </div>
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px]">Bid : Ask</div>
            <div className="font-mono num text-fg">
              {formatNumber(totalBidIce)} : {formatNumber(totalAskIce)}
            </div>
          </div>
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px]">Net Ice</div>
            <div
              className={cn(
                'font-mono num font-semibold',
                netIce > 0 ? 'text-bullish' : netIce < 0 ? 'text-bearish' : 'text-fg-muted',
              )}
            >
              {netIce > 0 ? '+' : ''}
              {formatNumber(netIce)}
            </div>
          </div>
        </div>

        {/* Visualization band — price axis with iceberg bubbles */}
        <div className="px-2 py-2 border-b border-line-subtle">
          <div className="text-[10px] text-fg-dim uppercase tracking-wider mb-1">
            Visible Orders + Hidden Iceberg (size-bubble)
          </div>
          <div className="relative h-[120px] bg-bg-2/30 rounded">
            {/* Mid line */}
            <div
              className="absolute left-0 right-0 border-t border-dashed border-line-strong"
              style={{ top: `${((snap.midPrice - minPrice) / priceRange) * 100}%` }}
            >
              <span className="absolute -top-2.5 left-1 text-[9px] text-fg-dim font-mono num">
                MID {formatIN(snap.midPrice)}
              </span>
            </div>

            {/* Asks (top) */}
            {sellIcebergs.map((ice) => {
              const top = ((ice.price - minPrice) / priceRange) * 100
              const size = Math.min(40, 8 + Math.log10(ice.icebergSize) * 6)
              return (
                <div
                  key={`a-${ice.price}`}
                  className="absolute -translate-y-1/2 flex items-center gap-1"
                  style={{ top: `${top}%`, right: '8px' }}
                >
                  <div className="text-[10px] font-mono num text-bearish">
                    {formatIN(ice.price)}
                  </div>
                  <div
                    className="rounded-full bg-accent/30 border-2 border-accent flex items-center justify-center text-[9px] font-mono num text-accent font-semibold"
                    style={{ width: `${size}px`, height: `${size}px` }}
                    title={`Iceberg ${formatNumber(ice.icebergSize)}`}
                  >
                    {Math.round(ice.icebergSize / 1000)}k
                  </div>
                </div>
              )
            })}

            {/* Bids (bottom) */}
            {buyIcebergs.map((ice) => {
              const top = ((ice.price - minPrice) / priceRange) * 100
              const size = Math.min(40, 8 + Math.log10(ice.icebergSize) * 6)
              return (
                <div
                  key={`b-${ice.price}`}
                  className="absolute -translate-y-1/2 flex items-center gap-1"
                  style={{ top: `${top}%`, left: '8px' }}
                >
                  <div
                    className="rounded-full bg-accent/30 border-2 border-accent flex items-center justify-center text-[9px] font-mono num text-accent font-semibold"
                    style={{ width: `${size}px`, height: `${size}px` }}
                    title={`Iceberg ${formatNumber(ice.icebergSize)}`}
                  >
                    {Math.round(ice.icebergSize / 1000)}k
                  </div>
                  <div className="text-[10px] font-mono num text-bullish">
                    {formatIN(ice.price)}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Table of icebergs */}
        <div className="flex-1 min-h-0 overflow-auto">
          <table className="w-full text-2xs">
            <thead className="sticky top-0 bg-bg-2 z-10">
              <tr className="text-fg-dim uppercase tracking-wider text-[10px]">
                <th className="px-2 py-1 text-left">Side</th>
                <th className="px-2 py-1 text-right">Price</th>
                <th className="px-2 py-1 text-right">Visible</th>
                <th className="px-2 py-1 text-right">Hidden</th>
                <th className="px-2 py-1 text-right">Refills</th>
                <th className="px-2 py-1 text-right">Conf.</th>
              </tr>
            </thead>
            <tbody>
              {icebergs.map((ice) => {
                const conf = Math.min(99, 40 + ice.refillCount * 7 + Math.log10(ice.icebergSize) * 4)
                return (
                  <tr
                    key={`${ice.side}-${ice.price}`}
                    className="border-b border-line-subtle/40 hover:bg-bg-2/40"
                  >
                    <td className="px-2 py-1.5">
                      <span
                        className={cn(
                          'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold',
                          ice.side === 'BID'
                            ? 'bg-bullish/15 text-bullish'
                            : 'bg-bearish/15 text-bearish',
                        )}
                      >
                        {ice.side === 'BID' ? (
                          <Snowflake className="h-2.5 w-2.5" />
                        ) : (
                          <TrendingUp className="h-2.5 w-2.5" />
                        )}
                        {ice.side}
                      </span>
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono num">{formatIN(ice.price)}</td>
                    <td className="px-2 py-1.5 text-right font-mono num text-fg-muted">
                      {formatNumber(ice.bidSize + ice.askSize)}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono num text-accent font-semibold">
                      {formatNumber(ice.icebergSize)}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono num">
                      <span
                        className={cn(
                          'inline-block px-1.5 py-0.5 rounded text-[10px]',
                          ice.refillCount >= 5
                            ? 'bg-accent/20 text-accent'
                            : 'bg-bg-3 text-fg-muted',
                        )}
                      >
                        ×{ice.refillCount}
                      </span>
                    </td>
                    <td className="px-2 py-1.5 text-right">
                      <div className="flex items-center gap-1 justify-end">
                        <div className="w-12 h-1 rounded-full bg-bg-3 overflow-hidden">
                          <div
                            className={cn(
                              'h-full',
                              conf > 75
                                ? 'bg-bullish'
                                : conf > 50
                                  ? 'bg-warning'
                                  : 'bg-fg-dim',
                            )}
                            style={{ width: `${conf}%` }}
                          />
                        </div>
                        <span className="font-mono num text-[10px]">{conf.toFixed(0)}%</span>
                      </div>
                    </td>
                  </tr>
                )
              })}
              {icebergs.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-2 py-6 text-center text-fg-dim text-xs">
                    No active icebergs detected above {formatNumber(minSize)} shares
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
