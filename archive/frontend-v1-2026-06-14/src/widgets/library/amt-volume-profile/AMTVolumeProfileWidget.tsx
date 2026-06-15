/**
 * AMT Volume Profile Widget — canvas-rendered histogram in AMT Scalper style.
 */

import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { AMTVolumeProfile } from '@/components/ui/AMTVolumeProfile'
import { useUIStore } from '@/store/uiStore'
import type { WidgetProps } from '../../Widget'

interface AMTVolumeProfileConfig {
  symbol?: string
  title?: string
}

export default function AMTVolumeProfileWidget({
  config,
  refresh,
  loading,
  lastUpdated,
}: WidgetProps<AMTVolumeProfileConfig>) {
  const { activeSymbol } = useUIStore()
  const symbol = config.symbol || activeSymbol || 'XAUUSDm'

  const { data } = useWidgetData({
    fetcher: async () => {
      const { generateVolumeProfile } = await import('@/services/deepchartsData')
      return generateVolumeProfile(symbol, 24)
    },
    intervalMs: 30000,
  })

  return (
    <div className="h-full w-full flex flex-col bg-[#0a0a0a] border border-cyan-500/20 rounded overflow-hidden">
      <div className="px-2 py-1 border-b border-cyan-500/20 bg-[#000] text-2xs font-mono flex items-center justify-between">
        <span className="text-cyan-400 font-bold tracking-wider">VOLUME PROFILE</span>
        <span className="text-cyan-300 text-[10px]">{symbol}</span>
      </div>
      <div className="flex-1 min-h-0 p-1">
        {data ? (
          <AMTVolumeProfile
            symbol={symbol}
            bins={data.levels}
            poc={data.poc}
            vah={data.vah}
            val={data.val}
            height={undefined}
          />
        ) : (
          <div className="h-full flex items-center justify-center text-cyan-400/40 text-xs font-mono">
            Loading...
          </div>
        )}
      </div>
    </div>
  )
}
