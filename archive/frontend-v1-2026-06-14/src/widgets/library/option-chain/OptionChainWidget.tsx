import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { cn, formatIN, pnlColor } from '@/lib/utils'
import { useState } from 'react'
import type { WidgetProps } from '../../Widget'

interface OptionChainConfig {
  underlying?: string
  title?: string
}

export default function OptionChainWidget({ config, refresh, loading, lastUpdated }: WidgetProps<OptionChainConfig>) {
  const underlying = config.underlying || 'NIFTY'
  const { data } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.getOptionChain(underlying)),
    intervalMs: 3000,
  })
  const [showCount, setShowCount] = useState(10)

  if (!data) {
    return (
      <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
        <div className="p-4 text-center text-fg-muted text-xs">Loading option chain...</div>
      </WidgetFrame>
    )
  }

  const startIdx = Math.floor((data.strikes.length - showCount) / 2)

  return (
    <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
      <div className="px-2 py-1.5 border-b border-line flex items-center justify-between text-2xs">
        <div className="flex items-center gap-2">
          <span className="font-semibold">{underlying}</span>
          <span className="text-fg-muted">SPOT {data.spot}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-bullish">PCR {data.pcr}</span>
          <span className="text-fg-muted">MP {data.maxPain}</span>
        </div>
      </div>
      <div className="overflow-y-auto" style={{ maxHeight: 'calc(100% - 30px)' }}>
        <table className="data-table text-2xs">
          <thead>
            <tr>
              <th colSpan={3} className="text-center bg-bearish/10 text-bearish border-r border-line text-2xs">CALL</th>
              <th className="text-center">STRIKE</th>
              <th colSpan={3} className="text-center bg-bullish/10 text-bullish border-l border-line text-2xs">PUT</th>
            </tr>
          </thead>
          <tbody>
            {data.strikes.slice(startIdx, startIdx + showCount).map((s) => (
              <tr key={s.strike} className={cn(s.strike === data.atm && 'bg-bg-3')}>
                <td className="text-right text-bearish font-mono text-2xs">{s.callOI > 1000000 ? `${(s.callOI / 1000000).toFixed(1)}M` : `${(s.callOI / 1000).toFixed(0)}K`}</td>
                <td className="text-right text-bearish font-mono text-2xs">{s.callLTP.toFixed(1)}</td>
                <td className="text-right text-fg-muted font-mono text-2xs border-r border-line">{s.callIV.toFixed(1)}</td>
                <td className="text-center font-mono font-bold bg-bg-2 text-2xs">{s.strike}</td>
                <td className="text-left text-fg-muted font-mono text-2xs border-l border-line">{s.putIV.toFixed(1)}</td>
                <td className="text-left text-bullish font-mono text-2xs">{s.putLTP.toFixed(1)}</td>
                <td className="text-left text-bullish font-mono text-2xs">{s.putOI > 1000000 ? `${(s.putOI / 1000000).toFixed(1)}M` : `${(s.putOI / 1000).toFixed(0)}K`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </WidgetFrame>
  )
}
