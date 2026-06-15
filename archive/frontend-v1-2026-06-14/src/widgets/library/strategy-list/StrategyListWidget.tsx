import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { cn, formatIN, pnlColor } from '@/lib/utils'
import { Pill } from '@/components/ui/Pill'
import { useUIStore } from '@/store/uiStore'
import type { WidgetProps } from '../../Widget'

interface StrategyConfig {
  title?: string
}

export default function StrategyListWidget({ config, refresh, loading, lastUpdated }: WidgetProps<StrategyConfig>) {
  const { data } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.listStrategies()),
    intervalMs: 30_000,
  })

  return (
    <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
      <div className="overflow-y-auto" style={{ maxHeight: '100%' }}>
        {(data || []).map((s) => (
          <div key={s.id} className="px-2.5 py-2 border-b border-line-subtle hover:bg-bg-2">
            <div className="flex items-center gap-1.5">
              <Pill variant={s.status === 'LIVE' ? 'bull' : s.status === 'CERTIFIED' ? 'info' : 'warn'} dot className="text-2xs">
                {s.status}
              </Pill>
              <Pill variant="neutral" className="text-2xs">{s.type}</Pill>
            </div>
            <div className="font-semibold text-sm mt-1">{s.name}</div>
            <div className="flex items-center justify-between mt-1 text-2xs">
              <span className={cn('font-mono num font-semibold', pnlColor(s.pnl.today))}>
                +₹{formatIN(s.pnl.today, 0)}
              </span>
              <span className="text-fg-muted">{s.winRate.toFixed(1)}% · {s.trades.today} trd</span>
            </div>
          </div>
        ))}
      </div>
    </WidgetFrame>
  )
}
