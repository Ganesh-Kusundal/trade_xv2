import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { LineChart } from '@/components/ui/LineChart'
import type { WidgetProps } from '../../Widget'

interface EquityCurveConfig {
  title?: string
  days?: number
}

export default function EquityCurveWidget({ config, refresh, loading, lastUpdated }: WidgetProps<EquityCurveConfig>) {
  const { data } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.listBacktests()).then((bts) => bts[0]?.equityCurve || []),
    intervalMs: 30_000,
  })

  const points = (data || []).map((p) => ({ x: p.timestamp, y: p.equity }))
  const benchmarks = (data || []).map((p) => ({ x: p.timestamp, y: p.benchmark }))

  return (
    <WidgetFrame id="" config={{ ...config, title: 'EQUITY CURVE' }} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
      {points.length > 0 ? (
        <div className="relative h-full">
          <LineChart
            data={points}
            benchmark={benchmarks}
            height={undefined}
            yLabel={(v) => `₹${(v / 100000).toFixed(1)}L`}
            xLabel={(v) => new Date(v).toLocaleDateString('en-IN', { month: 'short', day: '2-digit' })}
          />
          <div className="absolute top-2 left-2 text-2xs space-y-0.5 pointer-events-none">
            <div className="flex items-center gap-1.5">
              <div className="h-2 w-2 rounded-full bg-bullish" />
              <span className="text-fg-muted">Strategy</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="h-2 w-2 rounded-full bg-fg-dim" />
              <span className="text-fg-dim">Benchmark</span>
            </div>
          </div>
        </div>
      ) : (
        <div className="p-4 text-center text-fg-muted text-xs">Loading equity curve...</div>
      )}
    </WidgetFrame>
  )
}
