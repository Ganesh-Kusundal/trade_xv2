import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { useUIStore } from '@/store/uiStore'
import { Pill } from '@/components/ui/Pill'
import { useState } from 'react'
import { useLiveQuotes } from '@/services/liveSimulator'
import { cn, formatIN, pnlColor, formatNumber } from '@/lib/utils'
import type { WidgetProps } from '../../Widget'
import { Search } from 'lucide-react'

interface QuickOrderConfig {
  title?: string
  defaultSymbol?: string
}

export default function QuickOrderWidget({ config, refresh, loading, lastUpdated }: WidgetProps<QuickOrderConfig>) {
  const [symbol, setSymbol] = useState(config.defaultSymbol || 'RELIANCE')
  const [qty, setQty] = useState(100)
  const [price, setPrice] = useState(2935.4)
  const [sl, setSl] = useState(2910)
  const [target, setTarget] = useState(3000)
  const [product, setProduct] = useState<'MIS' | 'CNC' | 'NRML'>('MIS')
  const { data: quote } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.getQuote(symbol)),
    intervalMs: 1500,
  })
  const live = useLiveQuotes({ symbols: [symbol], intervalMs: 1500 })
  const ltp = live[symbol]?.ltp || quote?.ltp || price

  return (
    <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
      <div className="p-3 space-y-2">
        <div>
          <label className="text-2xs text-fg-dim uppercase tracking-wider">Symbol</label>
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            className="w-full h-7 bg-bg-0 border border-line rounded px-2 text-xs font-medium mt-1"
          />
        </div>
        <div className="grid grid-cols-3 gap-1">
          {(['MIS', 'CNC', 'NRML'] as const).map((p) => (
            <button
              key={p}
              onClick={() => setProduct(p)}
              className={cn('h-6 text-2xs rounded font-medium',
                product === p ? 'bg-brand text-white' : 'bg-bg-2 text-fg-muted hover:bg-bg-3'
              )}
            >
              {p}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          <div>
            <label className="text-2xs text-fg-dim">Qty</label>
            <input type="number" value={qty} onChange={(e) => setQty(+e.target.value)} className="w-full h-7 bg-bg-0 border border-line rounded px-2 text-xs num mt-1" />
          </div>
          <div>
            <label className="text-2xs text-fg-dim">Price</label>
            <input type="number" value={price} onChange={(e) => setPrice(+e.target.value)} className="w-full h-7 bg-bg-0 border border-line rounded px-2 text-xs num mt-1" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          <div>
            <label className="text-2xs text-fg-dim">SL</label>
            <input type="number" value={sl} onChange={(e) => setSl(+e.target.value)} className="w-full h-7 bg-bearish/10 border border-bearish/30 rounded px-2 text-xs num mt-1" />
          </div>
          <div>
            <label className="text-2xs text-fg-dim">Target</label>
            <input type="number" value={target} onChange={(e) => setTarget(+e.target.value)} className="w-full h-7 bg-bullish/10 border border-bullish/30 rounded px-2 text-xs num mt-1" />
          </div>
        </div>
        <div className="flex items-center justify-between text-2xs py-1">
          <span className="text-fg-dim">LTP</span>
          <span className={cn('font-mono num font-semibold', pnlColor(quote?.changePct || 0))}>{formatIN(ltp)}</span>
        </div>
        <div className="grid grid-cols-2 gap-1.5 pt-1">
          <button className="h-8 rounded bg-bearish text-white font-semibold text-xs">SELL</button>
          <button className="h-8 rounded bg-bullish text-white font-semibold text-xs">BUY</button>
        </div>
      </div>
    </WidgetFrame>
  )
}
