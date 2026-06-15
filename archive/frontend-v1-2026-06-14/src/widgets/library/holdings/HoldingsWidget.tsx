import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { cn, formatIN, pnlColor, formatNumber } from '@/lib/utils'
import { useState, useMemo } from 'react'
import type { WidgetProps } from '../../Widget'
import { Search, X } from 'lucide-react'

interface HoldingsConfig {
  title?: string
  product?: 'CNC' | 'all'
}

export default function HoldingsWidget({ config, refresh, loading, lastUpdated }: WidgetProps<HoldingsConfig>) {
  const { data: holdings } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.getHoldings()),
    intervalMs: 5000,
  })
  const [filter, setFilter] = useState('')

  const filtered = useMemo(() => {
    if (!holdings) return []
    return holdings.filter((h) => !filter || h.symbol.toLowerCase().includes(filter.toLowerCase()))
  }, [holdings, filter])

  const totalValue = (filtered || []).reduce((s, h) => s + h.ltp * h.quantity, 0)
  const totalPnl = (filtered || []).reduce((s, h) => s + h.pnl, 0)

  return (
    <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
      <div className="px-2 py-1.5 border-b border-line">
        <div className="flex items-center gap-1.5 px-2 h-6 bg-bg-0 border border-line rounded">
          <Search className="h-3 w-3 text-fg-dim" />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter..."
            className="flex-1 bg-transparent border-0 outline-none text-xs placeholder:text-fg-dim"
          />
        </div>
      </div>
      <div className="overflow-y-auto" style={{ maxHeight: 'calc(100% - 36px)' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th className="text-right">Qty</th>
              <th className="text-right">LTP</th>
              <th className="text-right">P&L</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((h) => (
              <tr key={h.symbol}>
                <td className="font-semibold text-xs">{h.symbol}</td>
                <td className="text-right font-mono text-xs">{h.quantity}</td>
                <td className="text-right font-mono text-xs">{formatIN(h.ltp)}</td>
                <td className={cn('text-right font-mono text-xs font-semibold', pnlColor(h.pnl))}>
                  {h.pnl >= 0 ? '+' : ''}₹{formatIN(Math.abs(h.pnl), 0)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length > 0 && (
          <div className="sticky bottom-0 bg-bg-2 border-t border-line p-2 flex items-center justify-between text-2xs">
            <span className="text-fg-muted">{filtered.length} holdings</span>
            <span className={cn('font-mono num font-semibold', pnlColor(totalPnl))}>
              {totalPnl >= 0 ? '+' : ''}₹{formatIN(Math.abs(totalPnl), 0)}
            </span>
          </div>
        )}
      </div>
    </WidgetFrame>
  )
}
