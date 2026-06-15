import { Panel } from '@/components/ui/Panel'
import { Pill } from '@/components/ui/Pill'
import { OPEN_ORDERS, CLOSED_ORDERS } from '@/services/mockData'
import { cn, formatIN, formatTime, pnlColor } from '@/lib/utils'
import { X, Edit, Plus, RefreshCw, Filter, ChevronRight, Activity, CheckCircle2, XCircle, Clock, AlertCircle, Download, RotateCcw } from 'lucide-react'
import { useState } from 'react'

export function Orders() {
  const [tab, setTab] = useState<'open' | 'executed' | 'cancelled' | 'all'>('open')
  return (
    <div className="h-full p-2 space-y-2 overflow-y-auto">
      <div className="grid grid-cols-5 gap-2">
        {[
          { label: 'Open Orders', value: OPEN_ORDERS.length, color: 'text-info', status: 'OPEN' },
          { label: 'Executed Today', value: 8, color: 'text-bullish', status: 'FILLED' },
          { label: 'Cancelled', value: 2, color: 'text-fg-dim', status: 'CANCELLED' },
          { label: 'Rejected', value: 1, color: 'text-bearish', status: 'REJECTED' },
          { label: 'Total Value', value: '₹8,42,156', color: 'text-fg', status: '' },
        ].map((s, i) => (
          <div key={i} className="p-3 bg-bg-1 border border-line rounded">
            <div className="text-2xs text-fg-dim uppercase tracking-wider">{s.label}</div>
            <div className={cn('text-2xl font-semibold font-mono num mt-1', s.color)}>{s.value}</div>
          </div>
        ))}
      </div>

      <Panel
        title="Order Management"
        actions={
          <>
            <div className="flex items-center gap-1 mr-2">
              {(['open', 'executed', 'cancelled', 'all'] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={cn(
                    'h-7 px-2.5 text-2xs font-medium rounded uppercase tracking-wider',
                    tab === t ? 'bg-bg-3 text-fg' : 'text-fg-muted hover:bg-bg-2',
                  )}
                >
                  {t}
                </button>
              ))}
            </div>
            <button className="btn btn-ghost"><Filter className="h-3.5 w-3.5" /></button>
            <button className="btn btn-ghost"><RefreshCw className="h-3.5 w-3.5" /></button>
            <button className="btn btn-secondary"><Download className="h-3.5 w-3.5" /> Export</button>
          </>
        }
        noPadding
      >
        <table className="data-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Order ID</th>
              <th>Symbol</th>
              <th>Side</th>
              <th>Type</th>
              <th className="text-right">Qty</th>
              <th className="text-right">Filled</th>
              <th className="text-right">Price</th>
              <th className="text-right">Avg</th>
              <th>Status</th>
              <th>Strategy</th>
              <th className="text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {tab === 'open' && OPEN_ORDERS.map((o) => (
              <tr key={o.orderId} className="cursor-pointer">
                <td className="text-2xs font-mono text-fg-dim">{formatTime(o.placedAt)}</td>
                <td className="font-mono text-2xs text-fg-muted">{o.orderId}</td>
                <td className="font-semibold">{o.symbol}</td>
                <td>
                  <Pill variant={o.side === 'BUY' ? 'bull' : 'bear'} className="text-2xs w-10 justify-center">{o.side}</Pill>
                </td>
                <td><Pill variant="neutral" className="text-2xs">{o.orderType}</Pill></td>
                <td className="text-right font-mono">{o.quantity}</td>
                <td className="text-right font-mono text-fg-muted">{o.filledQty}</td>
                <td className="text-right font-mono">{formatIN(o.price)}</td>
                <td className="text-right font-mono text-fg-dim">-</td>
                <td>
                  <Pill variant="info" dot className="text-2xs">
                    <Clock className="h-2.5 w-2.5" /> {o.status}
                  </Pill>
                </td>
                <td className="text-2xs text-fg-muted">{o.strategy}</td>
                <td className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    <button className="h-6 px-2 text-2xs rounded bg-bg-2 hover:bg-bg-3 text-fg-muted">
                      <Edit className="h-2.5 w-2.5" />
                    </button>
                    <button className="h-6 px-2 text-2xs rounded bg-bearish/15 text-bearish border border-bearish/30 hover:bg-bearish/25">
                      <X className="h-2.5 w-2.5" /> Cancel
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {(tab === 'executed' || tab === 'all' || tab === 'cancelled') && CLOSED_ORDERS.map((o) => (
              <tr key={o.orderId} className="cursor-pointer">
                <td className="text-2xs font-mono text-fg-dim">{formatTime(o.placedAt)}</td>
                <td className="font-mono text-2xs text-fg-muted">{o.orderId}</td>
                <td className="font-semibold">{o.symbol}</td>
                <td>
                  <Pill variant={o.side === 'BUY' ? 'bull' : 'bear'} className="text-2xs w-10 justify-center">{o.side}</Pill>
                </td>
                <td><Pill variant="neutral" className="text-2xs">{o.orderType}</Pill></td>
                <td className="text-right font-mono">{o.quantity}</td>
                <td className="text-right font-mono">{o.filledQty}</td>
                <td className="text-right font-mono">{formatIN(o.price)}</td>
                <td className="text-right font-mono">{formatIN(o.avgPrice)}</td>
                <td>
                  <Pill variant={o.status === 'FILLED' ? 'bull' : o.status === 'CANCELLED' ? 'neutral' : 'bear'} dot className="text-2xs">
                    {o.status === 'FILLED' && <CheckCircle2 className="h-2.5 w-2.5" />}
                    {o.status === 'CANCELLED' && <XCircle className="h-2.5 w-2.5" />}
                    {o.status}
                  </Pill>
                </td>
                <td className="text-2xs text-fg-muted">{o.strategy}</td>
                <td className="text-right">
                  <button className="h-6 px-2 text-2xs rounded bg-bg-2 hover:bg-bg-3 text-fg-muted">
                    Details
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  )
}
