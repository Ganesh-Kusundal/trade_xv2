import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { Gauge } from '@/components/ui/Progress'
import { cn, pnlColor } from '@/lib/utils'
import type { WidgetProps } from '../../Widget'

interface RiskConfig {
  title?: string
}

export default function RiskGaugeWidget({ config, refresh, loading, lastUpdated }: WidgetProps<RiskConfig>) {
  const { data } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.getRiskMetrics()),
    intervalMs: 10_000,
  })

  if (!data) {
    return (
      <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
        <div className="p-4 text-center text-fg-muted text-xs">Loading risk metrics...</div>
      </WidgetFrame>
    )
  }

  return (
    <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
      <div className="p-3 space-y-3">
        <div className="flex items-center justify-around">
          <Gauge value={Math.min(100, data.portfolioVar * 20)} size={80} thickness={6} label="VAR (1D)" />
          <Gauge value={data.sharpe * 25} size={80} thickness={6} label="SHARPE" />
        </div>
        <div className="space-y-1.5 text-2xs">
          <div className="flex justify-between">
            <span className="text-fg-dim">Exposure (Net)</span>
            <span className="font-mono num">{data.exposure.net.toFixed(1)}%</span>
          </div>
          <div className="flex justify-between">
            <span className="text-fg-dim">Margin Used</span>
            <span className="font-mono num text-warn">{data.margin.utilization.toFixed(1)}%</span>
          </div>
          <div className="flex justify-between">
            <span className="text-fg-dim">Beta</span>
            <span className="font-mono num">{data.beta.toFixed(2)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-fg-dim">Alpha</span>
            <span className={cn('font-mono num', pnlColor(data.alpha))}>+{data.alpha.toFixed(1)}%</span>
          </div>
          <div className="flex justify-between">
            <span className="text-fg-dim">Max Drawdown</span>
            <span className="font-mono num text-bearish">{data.maxDrawdown.toFixed(1)}%</span>
          </div>
        </div>
      </div>
    </WidgetFrame>
  )
}
