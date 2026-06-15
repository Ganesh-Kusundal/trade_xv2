import { Panel } from '@/components/ui/Panel'
import { Pill } from '@/components/ui/Pill'
import { POSITIONS } from '@/services/mockData'
import { useLiveQuotes } from '@/services/liveSimulator'
import { cn, formatIN, pnlColor, formatPercent } from '@/lib/utils'
import { X, Settings, Filter, Plus, ArrowUpRight, ArrowDownRight, AlertTriangle, Target, Activity } from 'lucide-react'

export function Positions() {
  const symbols = POSITIONS.map((p) => p.symbol)
  const quotes = useLiveQuotes({ symbols, intervalMs: 1500 })
  const totalPnl = POSITIONS.reduce((s, p) => s + p.pnl, 0)
  const totalCost = POSITIONS.reduce((s, p) => s + p.avgPrice * p.quantity, 0)
  const totalPnlPct = (totalPnl / totalCost) * 100

  return (
    <div className="h-full p-2 space-y-2 overflow-y-auto">
      <div className="grid grid-cols-4 gap-2">
        <div className="p-3 bg-bg-1 border border-line rounded">
          <div className="text-2xs text-fg-dim uppercase tracking-wider">Total Positions</div>
          <div className="text-2xl font-semibold font-mono num mt-1">{POSITIONS.length}</div>
        </div>
        <div className="p-3 bg-bg-1 border border-line rounded">
          <div className="text-2xs text-fg-dim uppercase tracking-wider">Total P&L</div>
          <div className={cn('text-2xl font-semibold font-mono num mt-1', pnlColor(totalPnl))}>
            {totalPnl >= 0 ? '+' : ''}₹{formatIN(Math.abs(totalPnl))}
          </div>
        </div>
        <div className="p-3 bg-bg-1 border border-line rounded">
          <div className="text-2xs text-fg-dim uppercase tracking-wider">P&L %</div>
          <div className={cn('text-2xl font-semibold font-mono num mt-1', pnlColor(totalPnlPct))}>
            {formatPercent(totalPnlPct)}
          </div>
        </div>
        <div className="p-3 bg-bg-1 border border-line rounded">
          <div className="text-2xs text-fg-dim uppercase tracking-wider">Exposure</div>
          <div className="text-2xl font-semibold font-mono num mt-1">₹{formatIN(totalCost)}</div>
        </div>
      </div>

      <Panel
        title="Open Positions"
        subtitle="MIS · Auto square-off 15:15"
        actions={
          <>
            <button className="btn btn-ghost"><Filter className="h-3.5 w-3.5" /></button>
            <button className="btn btn-secondary"><X className="h-3.5 w-3.5" /> Exit All</button>
          </>
        }
        noPadding
      >
        <table className="data-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th className="text-right">Qty</th>
              <th className="text-right">Avg</th>
              <th className="text-right">LTP</th>
              <th className="text-right">Day Chg</th>
              <th className="text-right">P&L</th>
              <th className="text-right">P&L %</th>
              <th className="text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {POSITIONS.map((p) => {
              const q = quotes[p.symbol]
              const ltp = q?.ltp || p.ltp
              const livePnl = (ltp - p.avgPrice) * p.quantity
              return (
                <tr key={p.symbol} className="cursor-pointer">
                  <td>
                    <div className="flex items-center gap-1.5">
                      <span className="font-semibold">{p.symbol}</span>
                      <Pill variant="info" className="text-2xs">LONG</Pill>
                    </div>
                  </td>
                  <td className="text-right font-mono">{p.quantity}</td>
                  <td className="text-right font-mono">{formatIN(p.avgPrice)}</td>
                  <td className="text-right font-mono font-semibold">{formatIN(ltp)}</td>
                  <td className={cn('text-right font-mono', pnlColor(p.dayChangePct))}>
                    {formatPercent(p.dayChangePct)}
                  </td>
                  <td className={cn('text-right font-mono font-semibold', pnlColor(livePnl))}>
                    {livePnl >= 0 ? '+' : ''}₹{formatIN(Math.abs(livePnl))}
                  </td>
                  <td className={cn('text-right font-mono', pnlColor(p.pnlPct))}>
                    {formatPercent(p.pnlPct)}
                  </td>
                  <td className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button className="h-6 px-2 text-2xs rounded bg-bearish/15 text-bearish border border-bearish/30 hover:bg-bearish/25">
                        Exit
                      </button>
                      <button className="h-6 px-2 text-2xs rounded bg-bg-2 hover:bg-bg-3 text-fg-muted">
                        SL
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </Panel>
    </div>
  )
}
