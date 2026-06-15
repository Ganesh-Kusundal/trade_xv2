import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { cn, formatIN, pnlColor } from '@/lib/utils'
import type { WidgetProps } from '../../Widget'
import { TrendingUp } from 'lucide-react'

interface PnLConfig {
  title?: string
}

export default function PnLSummaryWidget({ config, refresh, loading, lastUpdated }: WidgetProps<PnLConfig>) {
  const { data: portfolio } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.getPortfolio()),
    intervalMs: 5000,
  })

  if (!portfolio) {
    return (
      <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
        <div className="p-4 text-center text-fg-muted text-xs">Loading portfolio...</div>
      </WidgetFrame>
    )
  }

  return (
    <WidgetFrame id="" config={{ ...config, title: 'P&L' }} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
      <div className="px-2 py-1 border-b border-line bg-bg-2/30 flex items-center justify-between text-2xs text-fg-muted">
        <span>Total Equity</span>
        <span className="font-mono num">03:52:10 pm</span>
      </div>
      <div className="p-3">
        <div className="text-2xs text-fg-dim uppercase tracking-wider">Total Value</div>
        <div className="text-2xl font-semibold num mb-2">₹{formatIN(portfolio.totalValue)}</div>
        <div className="grid grid-cols-2 gap-2">
          <div className="p-2 bg-bg-2 rounded border border-line-subtle">
            <div className="text-2xs text-fg-dim">Today</div>
            <div className={cn('text-sm font-mono num font-semibold', pnlColor(portfolio.todayPnl))}>
              {portfolio.todayPnl >= 0 ? '+' : ''}₹{formatIN(Math.abs(portfolio.todayPnl))}
            </div>
            <div className={cn('text-2xs', pnlColor(portfolio.todayPnlPct))}>
              {portfolio.todayPnlPct >= 0 ? '+' : ''}{portfolio.todayPnlPct.toFixed(2)}%
            </div>
          </div>
          <div className="p-2 bg-bg-2 rounded border border-line-subtle">
            <div className="text-2xs text-fg-dim">Total</div>
            <div className={cn('text-sm font-mono num font-semibold', pnlColor(portfolio.totalPnl))}>
              {portfolio.totalPnl >= 0 ? '+' : ''}₹{formatIN(Math.abs(portfolio.totalPnl))}
            </div>
            <div className={cn('text-2xs', pnlColor(portfolio.totalPnlPct))}>
              {portfolio.totalPnlPct >= 0 ? '+' : ''}{portfolio.totalPnlPct.toFixed(2)}%
            </div>
          </div>
        </div>
      </div>
    </WidgetFrame>
  )
}
