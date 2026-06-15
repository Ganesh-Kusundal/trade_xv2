import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { cn, formatIN, pnlColor, formatNumber } from '@/lib/utils'
import type { WidgetProps } from '../../Widget'
import { Star } from 'lucide-react'

interface ScanResultsConfig {
  scannerId?: string
  title?: string
  topN?: number
}

export default function ScanResultsWidget({ config, refresh, loading, lastUpdated }: WidgetProps<ScanResultsConfig>) {
  const scannerId = config.scannerId || 'sc-1'
  const topN = config.topN || 50
  const { data } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.runScan(scannerId)),
    intervalMs: 30_000,
  })

  return (
    <WidgetFrame
      id=""
      config={{ ...config, title: data?.name?.toUpperCase() || 'SCANNER RESULTS' }}
      loading={loading}
      lastUpdated={lastUpdated}
      refresh={refresh}
    >
      {data && (
        <div className="px-2 py-1 border-b border-line flex items-center justify-between text-2xs text-fg-muted bg-bg-2/30">
          <span>NIFTY 500 · <span className="text-fg">{data.name}</span></span>
          <span className="font-mono num">{new Date(data.executedAt).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}</span>
        </div>
      )}
      <div className="overflow-y-auto" style={{ maxHeight: '100%' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th className="w-6">#</th>
              <th>Symbol</th>
              <th className="text-right">Price</th>
              <th className="text-right">Change %</th>
              <th className="text-right">RS Score</th>
              <th className="text-right">Volume Ratio</th>
              <th className="text-right">Score</th>
            </tr>
          </thead>
          <tbody>
            {data?.candidates.slice(0, topN).map((c) => (
              <tr key={c.symbol}>
                <td className="text-fg-dim font-mono text-2xs">{c.rank}</td>
                <td>
                  <div className="flex items-center gap-1">
                    <Star className="h-2.5 w-2.5 text-fg-dim" />
                    <span className="font-semibold text-xs">{c.symbol}</span>
                  </div>
                </td>
                <td className="text-right font-mono text-xs">{formatIN(c.metrics.rsi ? 2900 + (c.metrics.rsi * 4) : 0)}</td>
                <td className={cn('text-right font-mono text-xs', pnlColor(c.metrics.roc || 0))}>
                  {c.metrics.roc >= 0 ? '+' : ''}{c.metrics.roc.toFixed(2)}%
                </td>
                <td className="text-right font-mono text-2xs">
                  {formatNumber(c.score, 1)}
                </td>
                <td className="text-right font-mono text-2xs">
                  {c.metrics.volRatio?.toFixed(1)}x
                </td>
                <td className="text-right">
                  <div className="flex items-center gap-1.5 justify-end">
                    <div className="w-12 h-1 bg-bg-2 rounded">
                      <div className={cn('h-full rounded', c.score > 70 ? 'bg-bullish' : c.score > 40 ? 'bg-warning' : 'bg-bearish')} style={{ width: `${c.score}%` }} />
                    </div>
                    <span className="font-mono num text-2xs w-8 text-right">{c.score.toFixed(1)}</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </WidgetFrame>
  )
}
