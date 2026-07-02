/**
 * MarketDepth — Level 2 order book (bid/ask ladder).
 *
 * Shows the top N levels on each side, with bar-intensity proportional
 * to size, a summary header (total bid/ask, imbalance) and a footer
 * with the spread and a "pull" indicator.
 *
 * Uses real WebSocket depth data via useMarketDepth hook. Falls back
 * to mock when backend is unavailable.
 */

import { useState } from 'react'
import { Layers, TrendingUp, TrendingDown, ArrowDownUp, Wifi, WifiOff } from 'lucide-react'
import { useMarketDepth, type DOMSnapshot } from '@/hooks/useMarketDepth'
import { cn, formatIN, formatNumber, pnlColor } from '@/lib/utils'

interface MarketDepthProps {
  symbol: string
  levels?: number
  height?: number
}

export function MarketDepth({ symbol, levels = 10, height = 400 }: MarketDepthProps) {
  const { depth: realDepth, connected } = useMarketDepth({ symbol, levels })
  const [showOrders, setShowOrders] = useState(false)

  // Use real depth if connected and has data, otherwise null (shows loading state)
  const useReal = connected && realDepth !== null
  const snap: DOMSnapshot | null = useReal ? realDepth : null

  if (!snap) {
    return (
      <div className="b-panel rounded-sm flex flex-col items-center justify-center text-fg-dim text-2xs" style={{ height }}>
        <div className="flex items-center gap-1.5 mb-1">
          {!connected ? (
            <WifiOff className="h-3 w-3 text-bear" />
          ) : (
            <Layers className="h-3 w-3" />
          )}
        </div>
        <span>{!connected ? 'Disconnected' : 'Waiting for depth data...'}</span>
      </div>
    )
  }

  const maxSize = Math.max(
    ...snap.bids.map((b: { bidSize: number }) => b.bidSize),
    ...snap.asks.map((a: { askSize: number }) => a.askSize),
  )

  return (
    <div className="flex flex-col b-panel rounded-sm overflow-hidden" style={{ height }}>
      {/* Header */}
      <div className="flex items-center justify-between px-2 py-1 border-b border-bline bg-bbg2">
        <div className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wider">
          <Layers className="h-3 w-3 text-bcy" />
          <span>Market Depth</span>
        </div>
        <div className="flex items-center gap-2 text-2xs font-mono num">
          {useReal ? <Wifi className="h-2.5 w-2.5 text-bull" /> : <WifiOff className="h-2.5 w-2.5 text-bear" />}
          <span className="text-fg-dim">spread</span>
          <span className="text-fg">{formatIN(snap.spread)}</span>
        </div>
      </div>

      {/* Imbalance strip */}
      <div className="px-2 py-1 border-b border-bline bg-bbg1 flex items-center justify-between text-2xs">
        <div className="flex items-center gap-1.5">
          <span className="text-fg-dim uppercase tracking-wider text-[10px]">Imbalance</span>
          <span className={cn('font-mono num font-semibold', pnlColor(snap.imbalance))}>
            {(snap.imbalance * 100).toFixed(1)}%
          </span>
        </div>
        <div className="flex items-center gap-2 font-mono num">
          <span className="text-fg-dim">B</span>
          <span className="text-bull font-semibold">{formatNumber(snap.totalBid)}</span>
          <ArrowDownUp className="h-2.5 w-2.5 text-fg-dim" />
          <span className="text-bear font-semibold">{formatNumber(snap.totalAsk)}</span>
          <span className="text-fg-dim">A</span>
        </div>
      </div>
      <div className="h-1 flex">
        <div
          className="bg-bull transition-all"
          style={{ width: `${(snap.totalBid / (snap.totalBid + snap.totalAsk)) * 100}%` }}
        />
        <div
          className="bg-bear transition-all"
          style={{ width: `${(snap.totalAsk / (snap.totalBid + snap.totalAsk)) * 100}%` }}
        />
      </div>

      {/* Column header */}
      <div className={cn(
        'grid px-1.5 py-0.5 text-[10px] text-fg-dim uppercase tracking-wider border-b border-bline',
        showOrders ? 'grid-cols-[1fr_36px_60px_36px_1fr]' : 'grid-cols-[1fr_60px_1fr]',
      )}>
        {showOrders && <span className="text-right">#Ord</span>}
        <span className="text-right">Size</span>
        <span className="text-center">Price</span>
        {showOrders && <span className="text-left">#Ord</span>}
        <span className="text-left">Size</span>
      </div>

      {/* Ladder — asks on top (reversed), mid, bids */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {[...snap.asks].reverse().map((ask: { price: number; askSize: number; askOrders?: number }) => (
          <LadderRow
            key={ask.price}
            price={ask.price}
            bidSize={0}
            askSize={ask.askSize}
            bidOrders={0}
            askOrders={ask.askOrders ?? 0}
            maxSize={maxSize}
            showOrders={showOrders}
            side="ASK"
          />
        ))}
        <div className="px-2 py-1 text-center bg-brand/10 border-y border-brand/30 text-2xs font-mono num font-semibold text-brand flex items-center justify-center gap-2">
          <span>MID {formatIN(snap.mid)}</span>
          <span className="text-fg-dim">spread {formatIN(snap.spread)}</span>
        </div>
        {snap.bids.map((bid: { price: number; bidSize: number; bidOrders?: number }) => (
          <LadderRow
            key={bid.price}
            price={bid.price}
            bidSize={bid.bidSize}
            askSize={0}
            bidOrders={bid.bidOrders ?? 0}
            askOrders={0}
            maxSize={maxSize}
            showOrders={showOrders}
            side="BID"
          />
        ))}
      </div>

      {/* Footer toggle */}
      <div className="px-2 py-1 border-t border-bline bg-bbg2 flex items-center justify-between text-2xs">
        <button
          onClick={() => setShowOrders((v) => !v)}
          className={cn(
            'h-5 px-1.5 text-[10px] rounded-sm border',
            showOrders
              ? 'bg-bcy/15 border-bcy/30 text-bcy'
              : 'bg-bbg1 border-bline text-bfgm',
          )}
        >
          # orders
        </button>
        <div className="flex items-center gap-2 text-[10px] text-fg-dim font-mono num">
          {snap.imbalance > 0.1 ? (
            <span className="flex items-center gap-0.5 text-bull"><TrendingUp className="h-2.5 w-2.5" />buy pressure</span>
          ) : snap.imbalance < -0.1 ? (
            <span className="flex items-center gap-0.5 text-bear"><TrendingDown className="h-2.5 w-2.5" />sell pressure</span>
          ) : (
            <span className="text-fg-dim">balanced</span>
          )}
          <span>{useReal ? 'LIVE' : 'SIM'}</span>
        </div>
      </div>
    </div>
  )
}

function LadderRow({
  price, bidSize, askSize, bidOrders, askOrders, maxSize, showOrders, side,
}: {
  price: number
  bidSize: number
  askSize: number
  bidOrders: number
  askOrders: number
  maxSize: number
  showOrders: boolean
  side: 'BID' | 'ASK'
}) {
  const bidW = maxSize > 0 ? (bidSize / maxSize) * 100 : 0
  const askW = maxSize > 0 ? (askSize / maxSize) * 100 : 0
  return (
    <div className={cn(
      'grid items-center text-2xs font-mono num h-[20px] px-1.5 relative border-b border-bline-subtle/30',
      showOrders ? 'grid-cols-[1fr_36px_60px_36px_1fr]' : 'grid-cols-[1fr_60px_1fr]',
    )}>
      {/* Bid */}
      <div className="text-right relative h-full flex items-center justify-end">
        {bidSize > 0 && (
          <div className="absolute inset-y-0 right-0 bg-bull/15" style={{ width: `${bidW}%` }} />
        )}
        <span className="relative text-bull pr-1">{bidSize > 0 ? formatNumber(bidSize) : ''}</span>
      </div>
      {showOrders && (
        <div className="text-right text-fg-dim text-[10px] pr-1">{bidOrders > 0 ? `×${bidOrders}` : ''}</div>
      )}
      <div className={cn(
        'text-center font-semibold relative z-10',
        side === 'BID' ? 'text-bull' : 'text-bear',
      )}>
        {formatIN(price)}
      </div>
      {showOrders && (
        <div className="text-left text-fg-dim text-[10px] pl-1">{askOrders > 0 ? `×${askOrders}` : ''}</div>
      )}
      {/* Ask */}
      <div className="text-left relative h-full flex items-center justify-start">
        {askSize > 0 && (
          <div className="absolute inset-y-0 left-0 bg-bear/15" style={{ width: `${askW}%` }} />
        )}
        <span className="relative text-bear pl-1">{askSize > 0 ? formatNumber(askSize) : ''}</span>
      </div>
    </div>
  )
}
