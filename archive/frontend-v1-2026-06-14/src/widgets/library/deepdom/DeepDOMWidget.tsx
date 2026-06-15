/**
 * DeepDOM Widget — Depth-of-Market with Iceberg Detection
 *
 * Inspired by DeepCharts' DeepDOM:
 *   - Multi-level bid/ask ladder
 *   - Heatmap background intensity (size × persistence)
 *   - Iceberg detection (small visible + repeated refills → "Not in Book")
 *   - Cumulative volume + imbalance visualisation
 *
 * Reference: https://www.deepcharts.com/features/deepdom
 */

import { useEffect, useState } from 'react'
import { WidgetFrame } from '../../WidgetFrame'
import type { WidgetProps } from '../../Widget'
import { cn, formatIN, formatNumber } from '@/lib/utils'
import { generateDeepDOM, type DeepDOMSnapshot } from '@/services/deepchartsData'
import { Snowflake, Flame, Layers, Eye } from 'lucide-react'

interface DeepDOMConfig {
  symbol?: string
  levels?: number
  title?: string
  showHeatmap?: boolean
  showIcebergs?: boolean
}

export default function DeepDOMWidget({
  config,
  refresh,
  loading,
  lastUpdated,
}: WidgetProps<DeepDOMConfig>) {
  const symbol = config.symbol || 'NIFTY'
  const levels = config.levels || 20
  const [snap, setSnap] = useState<DeepDOMSnapshot | null>(null)
  const [highlightIceberg, setHighlightIceberg] = useState(true)

  useEffect(() => {
    setSnap(generateDeepDOM(symbol, levels))
    const id = window.setInterval(() => {
      setSnap(generateDeepDOM(symbol, levels))
    }, 1500)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, levels])

  if (!snap) {
    return (
      <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
        <div className="p-4 text-center text-fg-muted text-xs">Loading DOM…</div>
      </WidgetFrame>
    )
  }

  const maxSize = Math.max(
    ...snap.bids.map((b) => b.bidSize),
    ...snap.asks.map((a) => a.askSize),
  )
  const totalBid = snap.bids.reduce((s, b) => s + b.bidSize, 0)
  const totalAsk = snap.asks.reduce((s, a) => s + a.askSize, 0)
  const imbalance = (totalBid - totalAsk) / (totalBid + totalAsk)
  const icebergs = [...snap.bids.filter((b) => b.icebergSize > 0), ...snap.asks.filter((a) => a.icebergSize > 0)]

  return (
    <WidgetFrame
      id=""
      config={{ ...config, title: `DEEPDOM - ${symbol}` }}
      loading={loading}
      lastUpdated={lastUpdated}
      refresh={() => {
        setSnap(generateDeepDOM(symbol, levels))
        refresh()
      }}
    >
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className="px-2 py-1.5 border-b border-line bg-bg-2/40 grid grid-cols-3 gap-2 text-2xs">
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px]">Mid</div>
            <div className="font-mono num text-fg font-semibold">{formatIN(snap.midPrice)}</div>
          </div>
          <div>
            <div className="text-fg-dim uppercase tracking-wider text-[10px]">Imbalance</div>
            <div
              className={cn(
                'font-mono num font-semibold',
                imbalance > 0.05 ? 'text-bullish' : imbalance < -0.05 ? 'text-bearish' : 'text-fg-muted',
              )}
            >
              {(imbalance * 100).toFixed(1)}%
            </div>
          </div>
          <div className="flex items-center justify-end gap-1.5">
            <button
              onClick={() => setHighlightIceberg((v) => !v)}
              className={cn(
                'h-5 px-1.5 text-2xs rounded flex items-center gap-1',
                highlightIceberg ? 'bg-accent/20 text-accent border border-accent/30' : 'bg-bg-3 text-fg-dim border border-line',
              )}
              title="Highlight iceberg levels"
            >
              <Eye className="h-3 w-3" /> {icebergs.length} Iceberg{icebergs.length !== 1 ? 's' : ''}
            </button>
          </div>
        </div>

        {/* Bid/ask totals bar */}
        <div className="h-1.5 w-full flex">
          <div
            className="h-full bg-bullish/40 transition-all"
            style={{ width: `${(totalBid / (totalBid + totalAsk)) * 100}%` }}
          />
          <div
            className="h-full bg-bearish/40 transition-all"
            style={{ width: `${(totalAsk / (totalBid + totalAsk)) * 100}%` }}
          />
        </div>

        {/* Column headers */}
        <div className="grid grid-cols-[1.4fr_1fr_60px_1fr_1.4fr] text-[10px] text-fg-dim uppercase tracking-wider px-1.5 py-1 border-b border-line-subtle">
          <div className="text-right">Bid Size</div>
          <div className="text-right">Aggr</div>
          <div className="text-center">Price</div>
          <div className="text-left">Aggr</div>
          <div className="text-left">Ask Size</div>
        </div>

        {/* Ladder (asks on top reversed, mid in middle, bids on bottom) */}
        <div className="flex-1 min-h-0 overflow-auto">
          {snap.asks
            .slice()
            .reverse()
            .map((ask) => (
              <DOMRow
                key={ask.price}
                price={ask.price}
                bidSize={0}
                askSize={ask.askSize}
                bidAggr={0}
                askAggr={ask.askAggressive}
                maxSize={maxSize}
                iceberg={highlightIceberg ? ask.icebergSize : 0}
                refillCount={ask.refillCount}
                side="ASK"
                isIcebergLevel={ask.icebergSize > 0}
              />
            ))}
          <div className="px-2 py-1 text-center bg-brand/10 border-y border-brand/30 text-2xs font-mono num font-semibold text-brand">
            SPREAD {formatIN(snap.spread)} • MID {formatIN(snap.midPrice)}
          </div>
          {snap.bids.map((bid) => (
            <DOMRow
              key={bid.price}
              price={bid.price}
              bidSize={bid.bidSize}
              askSize={0}
              bidAggr={bid.bidAggressive}
              askAggr={0}
              maxSize={maxSize}
              iceberg={highlightIceberg ? bid.icebergSize : 0}
              refillCount={bid.refillCount}
              side="BID"
              isIcebergLevel={bid.icebergSize > 0}
            />
          ))}
        </div>

        {/* Footer stats */}
        <div className="px-2 py-1.5 border-t border-line bg-bg-2/30 grid grid-cols-4 gap-2 text-[10px] text-fg-dim">
          <div className="flex items-center gap-1">
            <Flame className="h-3 w-3 text-bearish" /> Total Ask: {formatNumber(totalAsk)}
          </div>
          <div className="flex items-center gap-1">
            <Snowflake className="h-3 w-3 text-bullish" /> Total Bid: {formatNumber(totalBid)}
          </div>
          <div className="flex items-center gap-1">
            <Layers className="h-3 w-3 text-accent" /> Iceberg: {icebergs.length}
          </div>
          <div className="text-right font-mono num">
            Ratio{' '}
            <span
              className={cn(
                'font-semibold',
                imbalance > 0 ? 'text-bullish' : imbalance < 0 ? 'text-bearish' : 'text-fg-muted',
              )}
            >
              {(totalBid / Math.max(1, totalAsk)).toFixed(2)}
            </span>
          </div>
        </div>
      </div>
    </WidgetFrame>
  )
}

// ─── DOMRow — single price level row ──────────────────────────────────

function DOMRow({
  price,
  bidSize,
  askSize,
  bidAggr,
  askAggr,
  maxSize,
  iceberg,
  refillCount,
  side,
  isIcebergLevel,
}: {
  price: number
  bidSize: number
  askSize: number
  bidAggr: number
  askAggr: number
  maxSize: number
  iceberg: number
  refillCount: number
  side: 'BID' | 'ASK'
  isIcebergLevel: boolean
}) {
  const bidW = (bidSize / maxSize) * 100
  const askW = (askSize / maxSize) * 100
  return (
    <div
      className={cn(
        'grid grid-cols-[1.4fr_1fr_60px_1fr_1.4fr] text-[11px] font-mono num items-center px-1.5 h-[20px] relative border-b border-line-subtle/30',
        isIcebergLevel && 'bg-accent/8',
      )}
    >
      {/* Bid size cell */}
      <div className="text-right relative h-full flex items-center justify-end">
        {bidSize > 0 && (
          <div
            className="absolute inset-y-0 right-0 bg-bullish/20"
            style={{ width: `${bidW}%` }}
          />
        )}
        {isIcebergLevel && side === 'BID' && (
          <span
            className="absolute left-1 top-1/2 -translate-y-1/2 h-1.5 w-1.5 rounded-full bg-accent shadow-[0_0_5px_rgb(168,85,247,0.9)]"
            title={`Iceberg: ${iceberg} shares (refilled ${refillCount}x)`}
          />
        )}
        <span className="relative text-bullish pr-1">{bidSize > 0 ? formatNumber(bidSize) : ''}</span>
      </div>

      {/* Bid aggressive */}
      <div className="text-right text-fg-dim text-[10px] pr-1">{bidAggr > 0 ? formatNumber(bidAggr) : ''}</div>

      {/* Price */}
      <div
        className={cn(
          'text-center font-semibold relative',
          side === 'BID' ? 'text-bullish' : 'text-bearish',
        )}
      >
        {formatIN(price)}
      </div>

      {/* Ask aggressive */}
      <div className="text-left text-fg-dim text-[10px] pl-1">{askAggr > 0 ? formatNumber(askAggr) : ''}</div>

      {/* Ask size cell */}
      <div className="text-left relative h-full flex items-center justify-start">
        {askSize > 0 && (
          <div
            className="absolute inset-y-0 left-0 bg-bearish/20"
            style={{ width: `${askW}%` }}
          />
        )}
        {isIcebergLevel && side === 'ASK' && (
          <span
            className="absolute right-1 top-1/2 -translate-y-1/2 h-1.5 w-1.5 rounded-full bg-accent shadow-[0_0_5px_rgb(168,85,247,0.9)]"
            title={`Iceberg: ${iceberg} shares (refilled ${refillCount}x)`}
          />
        )}
        <span className="relative text-bearish pl-1">{askSize > 0 ? formatNumber(askSize) : ''}</span>
      </div>
    </div>
  )
}
