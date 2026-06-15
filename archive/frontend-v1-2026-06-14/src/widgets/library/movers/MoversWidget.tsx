import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { useUIStore } from '@/store/uiStore'
import { useMemo } from 'react'
import { Sparkline } from '@/components/ui/Sparkline'
import type { Position } from '@/types/trading'
import { cn, formatIN, pnlColor } from '@/lib/utils'
import type { WidgetProps } from '../../Widget'
import { TrendingUp, TrendingDown } from 'lucide-react'

interface MoversConfig {
  direction?: 'gainers' | 'losers' | 'both'
  count?: number
}

export default function MoversWidget({ config, refresh, loading, lastUpdated }: WidgetProps<MoversConfig>) {
  const { activeSymbol } = useUIStore()
  const { data: positions } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.getPositions()),
    intervalMs: 3000,
  })
  const dir = config.direction || 'both'
  const count = config.count || 5

  const ranked = useMemo(() => {
    if (!positions || positions.length === 0) return { gainers: [], losers: [] }
    const sorted = [...positions].sort((a, b) => b.pnlPct - a.pnlPct)
    return {
      gainers: sorted.slice(0, count),
      losers: sorted.slice(-count).reverse(),
    }
  }, [positions, count])

  const renderRow = (p: Position) => {
    const data = Array.from({ length: 20 }).map((_, i) => (p.ltp) * (1 + Math.sin(i / 3) * 0.02))
    return (
      <div key={p.symbol} className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-bg-2">
        <div className="font-semibold text-xs">{p.symbol}</div>
        <div className="flex-1" />
        <div className="font-mono num text-2xs text-fg-muted">{p.quantity}</div>
        <Sparkline data={data} width={40} height={16} />
        <div className={cn('font-mono num text-2xs font-semibold w-14 text-right', pnlColor(p.pnlPct))}>
          {p.pnlPct >= 0 ? '+' : ''}{p.pnlPct.toFixed(2)}%
        </div>
      </div>
    )
  }

  return (
    <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
      <div className={cn('h-full', (dir === 'both') && 'grid grid-cols-2')}>
        {(dir === 'both' || dir === 'gainers') && (
          <div className={cn(dir === 'both' && 'border-r border-line')}>
            <div className="px-2 py-1.5 border-b border-line text-2xs font-semibold uppercase tracking-wider text-bullish flex items-center gap-1">
              <TrendingUp className="h-3 w-3" /> Gainers
            </div>
            <div className="overflow-y-auto" style={{ maxHeight: 'calc(100% - 30px)' }}>
              {ranked.gainers.map(renderRow)}
            </div>
          </div>
        )}
        {(dir === 'both' || dir === 'losers') && (
          <div>
            <div className="px-2 py-1.5 border-b border-line text-2xs font-semibold uppercase tracking-wider text-bearish flex items-center gap-1">
              <TrendingDown className="h-3 w-3" /> Losers
            </div>
            <div className="overflow-y-auto" style={{ maxHeight: 'calc(100% - 30px)' }}>
              {ranked.losers.map(renderRow)}
            </div>
          </div>
        )}
      </div>
    </WidgetFrame>
  )
}
