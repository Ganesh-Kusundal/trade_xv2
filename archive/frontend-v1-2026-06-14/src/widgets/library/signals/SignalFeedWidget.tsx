import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { Pill } from '@/components/ui/Pill'
import { cn, formatIN } from '@/lib/utils'
import type { WidgetProps } from '../../Widget'

interface SignalsConfig {
  title?: string
  count?: number
}

export default function SignalFeedWidget({ config, refresh, loading, lastUpdated }: WidgetProps<SignalsConfig>) {
  const { data: signals } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.getSignals()),
    intervalMs: 5000,
  })
  const count = config.count || 8

  return (
    <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
      <div className="overflow-y-auto" style={{ maxHeight: '100%' }}>
        {(signals || []).slice(0, count).map((s) => (
          <div key={s.id} className="flex items-center gap-2 px-2.5 py-1.5 border-b border-line-subtle hover:bg-bg-2">
            <Pill
              variant={s.signalType === 'STRONG_BUY' ? 'bull' : s.signalType === 'BUY' ? 'info' : s.signalType === 'SELL' ? 'bear' : 'neutral'}
              className="text-2xs w-20 justify-center"
            >
              {s.signalType.replace('_', ' ')}
            </Pill>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-semibold">{s.symbol}</div>
              <div className="text-2xs text-fg-dim truncate">{s.reasons[0]}</div>
            </div>
            <div className="text-right">
              <div className="text-2xs font-mono num font-semibold">{(s.confidence * 100).toFixed(0)}%</div>
              <div className="text-2xs text-fg-muted">{s.strategy.split(' ')[0]}</div>
            </div>
          </div>
        ))}
      </div>
    </WidgetFrame>
  )
}
