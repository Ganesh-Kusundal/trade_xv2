import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { cn, formatIN, pnlColor, formatNumber } from '@/lib/utils'
import { useUIStore } from '@/store/uiStore'
import type { WidgetProps } from '../../Widget'
import { Star, Search } from 'lucide-react'
import { useState } from 'react'

interface WatchlistConfig {
  symbols: string[]
  title?: string
}

export default function WatchlistWidget({ config, refresh, loading, lastUpdated }: WidgetProps<WatchlistConfig>) {
  const { data } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.getQuotes(config.symbols)),
    intervalMs: 2000,
  })
  const { activeSymbol, setActiveSymbol } = useUIStore()
  const [filter, setFilter] = useState('')

  const filtered = data ? Object.values(data).filter((q) => !filter || q.symbol.toLowerCase().includes(filter.toLowerCase())) : []

  return (
    <WidgetFrame id="" config={{ ...config, title: 'WATCHLIST' }} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
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
      <div className="overflow-y-auto" style={{ maxHeight: 'calc(100% - 33px)' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th className="text-right">LTP</th>
              <th className="text-right">Chg%</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((q) => (
              <tr key={q.symbol} onClick={() => setActiveSymbol(q.symbol)} className={cn('cursor-pointer', q.symbol === activeSymbol && 'row-active')}>
                <td>
                  <div className="flex items-center gap-1">
                    <Star className={cn('h-2.5 w-2.5', q.symbol === activeSymbol ? 'text-warning fill-warning' : 'text-fg-dim')} />
                    <span className="font-semibold text-xs">{q.symbol}</span>
                  </div>
                </td>
                <td className="text-right font-mono text-xs">{formatIN(q.ltp)}</td>
                <td className={cn('text-right font-mono text-xs', pnlColor(q.changePct))}>
                  {q.changePct >= 0 ? '+' : ''}{q.changePct.toFixed(2)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </WidgetFrame>
  )
}
