import { WidgetFrame } from '../../WidgetFrame'
import { useUIStore } from '@/store/uiStore'
import { cn, formatIN, pnlColor } from '@/lib/utils'
import type { WidgetProps } from '../../Widget'

interface IndexStripConfig {
  title?: string
}

export default function IndexStripWidget({ config, refresh, loading, lastUpdated }: WidgetProps<IndexStripConfig>) {
  const { activeSymbol, setActiveSymbol } = useUIStore()
  const indices = [
    { symbol: 'NIFTY 50', ltp: 24906.45, change: 51.20, changePct: 0.21 },
    { symbol: 'BANK NIFTY', ltp: 53256.80, change: -185.40, changePct: -0.35 },
    { symbol: 'NIFTY IT', ltp: 41285.20, change: 752.45, changePct: 1.85 },
    { symbol: 'FIN NIFTY', ltp: 25485.60, change: 124.80, changePct: 0.49 },
    { symbol: 'SENSEX', ltp: 81754.20, change: 152.40, changePct: 0.19 },
    { symbol: 'INDIA VIX', ltp: 14.85, change: -0.42, changePct: -2.75 },
  ]

  return (
    <WidgetFrame id="" config={{ ...config, title: 'MARKET INDICES' }} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
      <div className="px-2 py-1 border-b border-line flex items-center justify-between text-2xs text-fg-muted bg-bg-2/30">
        <span>Indian Markets</span>
        <span className="font-mono num">03:52:10 pm</span>
      </div>
      <div className="grid grid-cols-3 gap-1 p-2">
        {indices.map((idx) => (
          <button
            key={idx.symbol}
            onClick={() => setActiveSymbol(idx.symbol)}
            className="p-2 bg-bg-2 rounded border border-line-subtle text-left hover:border-brand transition-colors"
          >
            <div className="text-2xs text-fg-dim uppercase tracking-wider font-medium">{idx.symbol}</div>
            <div className={cn('text-base font-semibold font-mono num', pnlColor(idx.change))}>
              {formatIN(idx.ltp)}
            </div>
            <div className={cn('text-2xs font-mono num', pnlColor(idx.changePct))}>
              {idx.changePct >= 0 ? '+' : ''}{idx.changePct.toFixed(2)}%
            </div>
          </button>
        ))}
      </div>
    </WidgetFrame>
  )
}
