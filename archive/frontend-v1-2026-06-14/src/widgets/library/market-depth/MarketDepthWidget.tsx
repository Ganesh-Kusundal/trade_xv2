import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { Pill } from '@/components/ui/Pill'
import { useLiveQuotes } from '@/services/liveSimulator'
import { useMemo } from 'react'
import { formatIN, pnlColor, cn } from '@/lib/utils'
import type { WidgetProps } from '../../Widget'

interface MarketDepthConfig {
  symbol?: string
  levels?: number
}

export default function MarketDepthWidget({ config, refresh, loading, lastUpdated }: WidgetProps<MarketDepthConfig>) {
  const { data: quote } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.getQuote(config.symbol || 'RELIANCE')),
    intervalMs: 1000,
  })
  const levels = config.levels || 5
  const ltp = quote?.ltp || 0

  return (
    <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
      <div className="grid grid-cols-2 h-full">
        <div className="border-r border-line">
          <div className="px-2 py-1 text-2xs text-fg-dim uppercase tracking-wider bg-bearish/10 border-b border-line font-semibold">BID</div>
          <div className="space-y-0.5 p-1">
            {Array.from({ length: levels }).map((_, i) => {
              const price = ltp - (i + 1) * 0.5
              const qty = Math.floor(1000 * (levels - i) * Math.random())
              return (
                <div key={i} className="flex items-center text-2xs font-mono px-1.5">
                  <span className="text-bearish flex-1">{formatIN(price)}</span>
                  <span className="text-fg-muted">{qty}</span>
                </div>
              )
            })}
          </div>
        </div>
        <div>
          <div className="px-2 py-1 text-2xs text-fg-dim uppercase tracking-wider bg-bullish/10 border-b border-line font-semibold">ASK</div>
          <div className="space-y-0.5 p-1">
            {Array.from({ length: levels }).map((_, i) => {
              const price = ltp + (i + 1) * 0.5
              const qty = Math.floor(1000 * (levels - i) * Math.random())
              return (
                <div key={i} className="flex items-center text-2xs font-mono px-1.5">
                  <span className="text-bullish flex-1">{formatIN(price)}</span>
                  <span className="text-fg-muted">{qty}</span>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </WidgetFrame>
  )
}
