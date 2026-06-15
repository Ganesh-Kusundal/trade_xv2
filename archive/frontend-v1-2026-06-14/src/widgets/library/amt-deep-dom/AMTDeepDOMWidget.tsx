/**
 * AMT Deep DOM Widget — canvas-rendered bid/ask ladder in AMT Scalper style.
 */

import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { AMTDeepDOM } from '@/components/ui/AMTDeepDOM'
import { useUIStore } from '@/store/uiStore'
import type { WidgetProps } from '../../Widget'
import { useEffect, useState } from 'react'

interface AMTDeepDOMConfig {
  symbol?: string
  levels?: number
  title?: string
}

export default function AMTDeepDOMWidget({
  config,
  refresh,
  loading,
  lastUpdated,
}: WidgetProps<AMTDeepDOMConfig>) {
  const { activeSymbol } = useUIStore()
  const symbol = config.symbol || activeSymbol || 'XAUUSDm'
  const levels = config.levels || 16

  const { data: quote } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.getQuote(symbol)),
    intervalMs: 1000,
  })

  // Generate live DOM around the LTP
  const [domLevels, setDomLevels] = useState<{ price: number; bid: number; ask: number }[]>([])
  useEffect(() => {
    if (!quote) return
    const mid = quote.ltp
    const tick = 0.05
    const arr: { price: number; bid: number; ask: number }[] = []
    for (let i = levels; i > 0; i--) {
      const price = Number((mid - i * tick).toFixed(2))
      const base = 50000 + Math.random() * 1_500_000
      arr.push({ price, bid: Math.floor(base * (0.4 + Math.random() * 0.6)), ask: 0 })
    }
    for (let i = 1; i <= levels; i++) {
      const price = Number((mid + i * tick).toFixed(2))
      const base = 50000 + Math.random() * 1_500_000
      arr.push({ price, bid: 0, ask: Math.floor(base * (0.4 + Math.random() * 0.6)) })
    }
    setDomLevels(arr)
    const id = window.setInterval(() => {
      setDomLevels((prev) =>
        prev.map((l) => ({
          ...l,
          bid: l.bid > 0 ? Math.max(0, l.bid + Math.floor((Math.random() - 0.5) * 80000)) : 0,
          ask: l.ask > 0 ? Math.max(0, l.ask + Math.floor((Math.random() - 0.5) * 80000)) : 0,
        })),
      )
    }, 1000)
    return () => clearInterval(id)
  }, [quote?.ltp, levels])

  return (
    <div className="h-full w-full flex flex-col bg-[#0a0a0a] border border-cyan-500/20 rounded overflow-hidden">
      <div className="px-2 py-1 border-b border-cyan-500/20 bg-[#000] text-2xs font-mono flex items-center justify-between">
        <span className="text-cyan-400 font-bold tracking-wider">DEEP DOM</span>
        <span className="text-cyan-300 text-[10px]">{symbol}</span>
      </div>
      <div className="flex-1 min-h-0 p-1">
        {quote ? (
          <AMTDeepDOM
            symbol={symbol}
            levels={domLevels}
            spread={0.05}
            lastPrice={quote.ltp}
            levelsToShow={levels}
            height={undefined}
          />
        ) : (
          <div className="h-full flex items-center justify-center text-cyan-400/40 text-xs font-mono">
            Loading DOM...
          </div>
        )}
      </div>
    </div>
  )
}
