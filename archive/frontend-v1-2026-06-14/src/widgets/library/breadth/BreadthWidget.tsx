import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { Distribution } from '@/components/ui/Progress'
import { LineChart } from '@/components/ui/LineChart'
import { cn, formatNumber } from '@/lib/utils'
import type { WidgetProps } from '../../Widget'

interface BreadthConfig {
  title?: string
}

export default function BreadthWidget({ config, refresh, loading, lastUpdated }: WidgetProps<BreadthConfig>) {
  const { data } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.getMarketBreadth()),
    intervalMs: 30_000,
  })

  const breadthData = data || {
    advances: 0, declines: 0, unchanged: 0, total: 0, advanceDeclineRatio: 0,
    newHighs: 0, newLows: 0, above50DMA: 0, below50DMA: 0, above200DMA: 0, below200DMA: 0,
    rsRotation: [],
  }
  const total = breadthData.advances + breadthData.declines + breadthData.unchanged
  const advPct = total ? (breadthData.advances / total) * 100 : 0

  // Synthetic history for the line chart
  const history = Array.from({ length: 30 }).map((_, i) => ({
    x: i,
    y: 50 + Math.sin(i / 3) * 20 + (i > 15 ? 15 : 0) + Math.random() * 5,
  }))

  return (
    <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
      <div className="p-3">
        <div className="flex items-center gap-4">
          <Distribution
            data={[
              { label: 'Advancing', value: breadthData.advances, color: '#16a34a' },
              { label: 'Declining', value: breadthData.declines, color: '#dc2626' },
              { label: 'Unchanged', value: breadthData.unchanged, color: '#6b7280' },
            ]}
            size={100}
            thickness={14}
            centerValue={`${Math.round(advPct)}%`}
            centerLabel="ADVANCING"
          />
          <div className="flex-1 grid grid-cols-2 gap-1.5 text-2xs">
            <div className="flex items-center gap-1.5">
              <div className="h-1.5 w-1.5 rounded-full bg-bullish" />
              <span className="flex-1 text-fg-muted">Advances</span>
              <span className="font-mono num font-semibold text-bullish">{breadthData.advances}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="h-1.5 w-1.5 rounded-full bg-bearish" />
              <span className="flex-1 text-fg-muted">Declines</span>
              <span className="font-mono num font-semibold text-bearish">{breadthData.declines}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="h-1.5 w-1.5 rounded-full bg-fg-dim" />
              <span className="flex-1 text-fg-muted">Unchanged</span>
              <span className="font-mono num font-semibold">{breadthData.unchanged}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="h-1.5 w-1.5 rounded-full bg-info" />
              <span className="flex-1 text-fg-muted">A/D Ratio</span>
              <span className="font-mono num font-semibold">{breadthData.advanceDeclineRatio.toFixed(2)}</span>
            </div>
          </div>
        </div>
        <div className="mt-3 pt-3 border-t border-line">
          <div className="text-2xs text-fg-dim uppercase tracking-wider mb-1.5">Breadth Trend (30D)</div>
          <LineChart data={history} height={70} showGrid={false} yLabel={(v) => `${Math.round(v)}%`} />
        </div>
      </div>
    </WidgetFrame>
  )
}
