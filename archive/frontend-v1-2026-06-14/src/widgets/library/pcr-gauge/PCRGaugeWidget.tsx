import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { cn, formatNumber, pnlColor } from '@/lib/utils'
import type { WidgetProps } from '../../Widget'

interface PCRConfig {
  title?: string
}

export default function PCRGaugeWidget({ config, refresh, loading, lastUpdated }: WidgetProps<PCRConfig>) {
  const { data } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.getOptionChain('NIFTY')),
    intervalMs: 5000,
  })

  if (!data) {
    return (
      <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
        <div className="p-4 text-center text-fg-muted text-xs">Loading option chain...</div>
      </WidgetFrame>
    )
  }

  const regime = data.pcr > 1.2 ? 'Bullish' : data.pcr < 0.85 ? 'Bearish' : 'Neutral'

  return (
    <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
      <div className="p-3 space-y-2">
        <div className="text-center">
          <div className="text-2xs text-fg-dim uppercase tracking-wider">Put-Call Ratio</div>
          <div className={cn('text-3xl font-semibold font-mono num', pnlColor(data.pcr - 1))}>
            {data.pcr.toFixed(2)}
          </div>
          <div className={cn('text-2xs', pnlColor(data.pcr - 1))}>{regime}</div>
        </div>
        <div className="space-y-1.5 text-2xs">
          <div className="flex justify-between">
            <span className="text-fg-dim">Total Call OI</span>
            <span className="font-mono num text-bearish">{formatNumber(data.totalCallOI / 1_000_000, 1)}M</span>
          </div>
          <div className="flex justify-between">
            <span className="text-fg-dim">Total Put OI</span>
            <span className="font-mono num text-bullish">{formatNumber(data.totalPutOI / 1_000_000, 1)}M</span>
          </div>
          <div className="flex justify-between">
            <span className="text-fg-dim">Max Pain</span>
            <span className="font-mono num">{data.maxPain}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-fg-dim">ATM IV</span>
            <span className="font-mono num text-warn">{data.iv.toFixed(1)}%</span>
          </div>
        </div>
      </div>
    </WidgetFrame>
  )
}
