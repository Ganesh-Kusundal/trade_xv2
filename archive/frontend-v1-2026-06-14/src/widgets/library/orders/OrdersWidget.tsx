import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { cn, formatIN, formatTime, pnlColor } from '@/lib/utils'
import { Pill } from '@/components/ui/Pill'
import { Edit, X } from 'lucide-react'
import type { WidgetProps } from '../../Widget'

interface OrdersConfig {
  title?: string
  status?: 'OPEN' | 'all'
}

export default function OrdersWidget({ config, refresh, loading, lastUpdated }: WidgetProps<OrdersConfig>) {
  const { data: orders } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.getOpenOrders()),
    intervalMs: 5000,
  })

  return (
    <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
      <div className="overflow-y-auto" style={{ maxHeight: '100%' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Symbol</th>
              <th>Side</th>
              <th className="text-right">Qty</th>
              <th className="text-right">Price</th>
              <th className="text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {(orders || []).map((o) => (
              <tr key={o.orderId}>
                <td className="text-2xs font-mono text-fg-dim">{formatTime(o.placedAt, false)}</td>
                <td className="font-semibold text-xs">{o.symbol}</td>
                <td>
                  <Pill variant={o.side === 'BUY' ? 'bull' : 'bear'} className="text-2xs w-10 justify-center">
                    {o.side}
                  </Pill>
                </td>
                <td className="text-right font-mono text-xs">{o.quantity}</td>
                <td className="text-right font-mono text-xs">{formatIN(o.price)}</td>
                <td className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    <button className="h-5 w-5 rounded bg-bg-2 hover:bg-bg-3 text-fg-muted flex items-center justify-center">
                      <Edit className="h-2.5 w-2.5" />
                    </button>
                    <button className="h-5 w-5 rounded bg-bearish/15 text-bearish hover:bg-bearish/25 flex items-center justify-center">
                      <X className="h-2.5 w-2.5" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {orders && orders.length === 0 && (
          <div className="p-4 text-center text-fg-muted text-xs">No open orders</div>
        )}
      </div>
    </WidgetFrame>
  )
}
