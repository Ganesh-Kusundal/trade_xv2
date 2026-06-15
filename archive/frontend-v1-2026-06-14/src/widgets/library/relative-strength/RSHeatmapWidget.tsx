import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { cn, formatIN, formatNumber, pnlColor, formatPercent } from '@/lib/utils'
import type { WidgetProps } from '../../Widget'

interface RSHeatmapConfig {
  title?: string
}

export default function RSHeatmapWidget({ config, refresh, loading, lastUpdated }: WidgetProps<RSHeatmapConfig>) {
  const { data: positions } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.getPositions()),
    intervalMs: 5000,
  })

  const sorted = (positions || []).slice().sort((a, b) => b.pnlPct - a.pnlPct)

  return (
    <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
      <div className="p-2 grid grid-cols-3 gap-1.5">
        {sorted.map((p) => (
          <div
            key={p.symbol}
            className="p-1.5 rounded text-center border border-line"
            style={{
              background: p.pnlPct > 0
                ? `linear-gradient(135deg, rgba(22,163,74,${Math.min(0.5, p.pnlPct / 5)}) 0%, transparent 100%)`
                : `linear-gradient(135deg, rgba(220,38,38,${Math.min(0.5, Math.abs(p.pnlPct) / 5)}) 0%, transparent 100%)`,
            }}
          >
            <div className="font-semibold text-xs">{p.symbol}</div>
            <div className={cn('text-base font-mono num font-semibold', pnlColor(p.pnlPct))}>
              {p.pnlPct >= 0 ? '+' : ''}{p.pnlPct.toFixed(2)}%
            </div>
            <div className="text-2xs text-fg-muted font-mono num">RS {Math.round(50 + p.pnlPct * 5)}</div>
          </div>
        ))}
      </div>
    </WidgetFrame>
  )
}
