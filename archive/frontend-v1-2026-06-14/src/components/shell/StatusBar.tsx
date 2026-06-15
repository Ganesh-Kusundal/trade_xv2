/**
 * StatusBar — redesigned bottom bar with system status, broker status, and time.
 */

import { cn, formatIN, pnlColor, formatTime } from '@/lib/utils'
import { useUIStore } from '@/store/uiStore'
import { useEffect, useState } from 'react'
import { POSITIONS, OPEN_ORDERS, PORTFOLIO } from '@/services/mockData'
import { Activity, Server, Wifi, Clock, AlertCircle, Database, Zap, Heart } from 'lucide-react'

export function StatusBar() {
  const { marketOpen } = useUIStore()
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const totalPnl = POSITIONS.reduce((s, p) => s + p.pnl, 0)

  return (
    <div className="h-7 flex items-center bg-bg-1 border-t border-line text-2xs flex-shrink-0">
      {/* Left: system status */}
      <div className="flex items-center gap-3 px-3 border-r border-line h-full">
        <div className="flex items-center gap-1 text-bullish">
          <Wifi className="h-3 w-3" />
          <span className="font-semibold uppercase tracking-wider">Connected</span>
        </div>
        <span className="text-fg-dim">|</span>
        <div className="flex items-center gap-1 text-fg-muted">
          <Database className="h-3 w-3" />
          <span>Market Data</span>
        </div>
        <span className="text-fg-dim">|</span>
        <div className="flex items-center gap-1 text-bullish">
          <Server className="h-3 w-3" />
          <span>Dhan Connected</span>
        </div>
        <div className="flex items-center gap-1 text-bullish">
          <Server className="h-3 w-3" />
          <span>Upstox Connected</span>
        </div>
      </div>

      {/* Center: server time */}
      <div className="flex-1 flex items-center justify-center gap-2 text-fg-muted">
        <Clock className="h-3 w-3" />
        <span className="font-mono num">Server Time</span>
        <span className="text-fg font-mono num">{formatTime(now)} IST</span>
      </div>

      {/* Right: P&L summary */}
      <div className="flex items-center gap-3 px-3 border-l border-line h-full">
        <div className="flex items-center gap-1.5">
          <span className="text-fg-dim">Data Latency</span>
          <span className="font-mono num text-info">12ms</span>
        </div>
        <span className="text-fg-dim">|</span>
        <div className="flex items-center gap-1.5">
          <Heart className="h-3 w-3 text-bullish" />
          <span className="text-fg-dim">System Status</span>
          <span className="font-mono num text-bullish">Healthy</span>
        </div>
        <span className="text-fg-dim">|</span>
        <div className="flex items-center gap-1.5">
          <span className="text-fg-dim">PnL</span>
          <span className={cn('font-mono num font-semibold', pnlColor(totalPnl))}>
            {totalPnl >= 0 ? '+' : ''}₹{formatIN(Math.abs(totalPnl), 0)}
          </span>
        </div>
        <span className="text-fg-dim">|</span>
        <div className="flex items-center gap-1.5">
          <span className="text-fg-dim">Day</span>
          <span className={cn('font-mono num font-semibold', pnlColor(PORTFOLIO.todayPnlPct))}>
            {PORTFOLIO.todayPnl >= 0 ? '+' : ''}₹{formatIN(Math.abs(PORTFOLIO.todayPnl))} ({PORTFOLIO.todayPnlPct.toFixed(2)}%)
          </span>
        </div>
        <span className="text-fg-dim">|</span>
        <div className="flex items-center gap-1.5">
          <span className="text-fg-dim">Pos</span>
          <span className="font-mono num">{POSITIONS.length}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-fg-dim">Ord</span>
          <span className="font-mono num">{OPEN_ORDERS.length}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className={cn('h-1.5 w-1.5 rounded-full', marketOpen ? 'bg-bullish pulse-dot' : 'bg-bearish')} />
          <span className="font-semibold uppercase tracking-wider">{marketOpen ? 'Open' : 'Closed'}</span>
        </div>
      </div>
    </div>
  )
}
