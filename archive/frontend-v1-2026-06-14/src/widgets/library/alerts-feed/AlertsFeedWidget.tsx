import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { cn, formatIN, pnlColor, timeAgo } from '@/lib/utils'
import { Pill } from '@/components/ui/Pill'
import { Bell } from 'lucide-react'
import type { WidgetProps } from '../../Widget'

interface AlertsConfig {
  title?: string
  maxItems?: number
}

export default function AlertsFeedWidget({ config, refresh, loading, lastUpdated }: WidgetProps<AlertsConfig>) {
  const { data } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.listAlerts()),
    intervalMs: 10_000,
  })
  const maxItems = config.maxItems || 20

  return (
    <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
      <div className="overflow-y-auto" style={{ maxHeight: '100%' }}>
        {(data || []).slice(0, maxItems).map((a) => {
          const Icon = Bell
          return (
            <div
              key={a.id}
              className={cn(
                'flex items-start gap-2 px-2.5 py-2 border-b border-line-subtle',
                a.priority === 'CRITICAL' && 'bg-bearish/5',
                a.priority === 'HIGH' && 'bg-warning/5',
              )}
            >
              <Icon className={cn('h-3.5 w-3.5 mt-0.5',
                a.priority === 'CRITICAL' ? 'text-bearish' :
                a.priority === 'HIGH' ? 'text-warning' : 'text-info'
              )} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <Pill variant={a.priority === 'CRITICAL' ? 'bear' : a.priority === 'HIGH' ? 'warn' : 'info'} className="text-2xs">
                    {a.priority}
                  </Pill>
                  <span className="text-xs font-semibold">{a.symbol}</span>
                  <span className="ml-auto text-2xs text-fg-dim font-mono">{timeAgo(a.triggeredAt)}</span>
                </div>
                <div className="text-2xs text-fg-muted mt-0.5 line-clamp-2">{a.message}</div>
              </div>
            </div>
          )
        })}
      </div>
    </WidgetFrame>
  )
}
