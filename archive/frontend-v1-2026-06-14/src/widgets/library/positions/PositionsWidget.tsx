import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { cn, formatIN, pnlColor } from '@/lib/utils'
import { useLiveQuotes } from '@/services/liveSimulator'
import { useUIStore } from '@/store/uiStore'
import { useMemo } from 'react'
import { Sparkline } from '@/components/ui/Sparkline'
import type { WidgetProps } from '../../Widget'
import { X } from 'lucide-react'

interface PositionsConfig {
  title?: string
  compact?: boolean
}

export default function PositionsWidget({ config, refresh, loading, lastUpdated }: WidgetProps<PositionsConfig>) {
  const { data: positions } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.getPositions()),
    intervalMs: 5000,
  })
  const symbols = useMemo(() => (positions || []).map((p) => p.symbol), [positions])
  const quotes = useLiveQuotes({ symbols, intervalMs: 1500 })
  const { setActiveSymbol } = useUIStore()

  const totalPnl = (positions || []).reduce((s, p) => s + p.pnl, 0)
  const totalCost = (positions || []).reduce((s, p) => s + p.avgPrice * p.quantity, 0)

  return (
    <WidgetFrame id="" config={{ ...config, title: 'POSITIONS' }} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
      <div className="overflow-y-auto" style={{ maxHeight: '100%' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th className="text-right">Qty</th>
              <th className="text-right">Avg Price</th>
              <th className="text-right">LTP</th>
              <th className="text-right">P&L</th>
              <th className="text-right">P&L %</th>
              <th>Strategy</th>
            </tr>
          </thead>
          <tbody>
            {(positions || []).map((p) => {
              const q = quotes[p.symbol]
              const ltp = q?.ltp || p.ltp
              return (
                <tr key={p.symbol} onClick={() => setActiveSymbol(p.symbol)} className="cursor-pointer">
                  <td className="font-semibold text-xs">{p.symbol}</td>
                  <td className="text-right font-mono text-xs">{p.quantity}</td>
                  <td className="text-right font-mono text-xs">{formatIN(p.avgPrice)}</td>
                  <td className="text-right font-mono text-xs font-semibold">{formatIN(ltp)}</td>
                  <td className={cn('text-right font-mono text-xs font-semibold', pnlColor(p.pnl))}>
                    {p.pnl >= 0 ? '+' : ''}₹{formatIN(Math.abs(p.pnl), 0)}
                  </td>
                  <td className={cn('text-right font-mono text-xs', pnlColor(p.pnlPct))}>
                    {p.pnlPct >= 0 ? '+' : ''}{p.pnlPct.toFixed(2)}%
                  </td>
                  <td className="text-2xs text-fg-muted">{p.product === 'MIS' ? 'HalfTrend' : 'VWAP'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {positions && positions.length > 0 && (
          <div className="sticky bottom-0 bg-bg-2 border-t border-line p-2 grid grid-cols-4 gap-2 text-2xs">
            <div>
              <div className="text-fg-dim">Positions</div>
              <div className="font-mono num font-semibold">{positions.length}</div>
            </div>
            <div>
              <div className="text-fg-dim">Day P&L</div>
              <div className={cn('font-mono num font-semibold', pnlColor(totalPnl))}>
                {totalPnl >= 0 ? '+' : ''}₹{formatIN(Math.abs(totalPnl), 0)}
              </div>
            </div>
            <div>
              <div className="text-fg-dim">Total P&L</div>
              <div className={cn('font-mono num font-semibold', pnlColor(totalPnl))}>
                {totalPnl >= 0 ? '+' : ''}₹{formatIN(Math.abs(totalPnl), 0)}
              </div>
            </div>
            <div>
              <div className="text-fg-dim">Exposure</div>
              <div className="font-mono num font-semibold">₹{formatIN(totalCost, 0)}</div>
            </div>
          </div>
        )}
      </div>
    </WidgetFrame>
  )
}
