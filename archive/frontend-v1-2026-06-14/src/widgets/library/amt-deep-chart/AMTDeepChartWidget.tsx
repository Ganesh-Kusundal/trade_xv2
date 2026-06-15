/**
 * AMT Deep Chart Widget — full AMT Scalper-style chart.
 *
 * Wraps the AMTChart canvas component with the AMT-styled chrome
 * (top selector bar, indicator pills, footer stats).
 */

import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { AMTChart } from '@/components/ui/AMTChart'
import { cn, formatIN, pnlColor } from '@/lib/utils'
import { useState, useEffect } from 'react'
import type { WidgetProps } from '../../Widget'
import { RefreshCw, Camera, Settings2, Maximize2 } from 'lucide-react'
import { generateVolumeProfile } from '@/services/deepchartsData'

interface AMTDeepChartConfig {
  symbol?: string
  timeframe?: string
  showIndicators?: boolean
  showVolume?: boolean
  title?: string
}

const TF_OPTIONS = ['M1', 'M5', 'M15', 'H1', 'H4', 'D1']

export default function AMTDeepChartWidget({
  config,
  refresh,
  loading,
  lastUpdated,
}: WidgetProps<AMTDeepChartConfig>) {
  const symbol = config.symbol || 'XAUUSDm'
  const [tf, setTf] = useState(config.timeframe || 'M1')
  const { data: candles } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.getCandles(symbol, '1m', 200)),
    intervalMs: 3000,
  })
  const { data: quote } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.getQuote(symbol)),
    intervalMs: 1500,
  })

  // Indicators on/off state
  const [activeIndicators, setActiveIndicators] = useState({
    VWAP: true,
    POC: true,
    PVG: true,
    IB: true,
    LIQ: false,
  })

  // Generate AMT-style volume profile for adjacent display
  const { data: profileData } = useWidgetData({
    fetcher: async () => {
      // use the deepcharts generator
      const { generateVolumeProfile } = await import('@/services/deepchartsData')
      return generateVolumeProfile(symbol, 24)
    },
    intervalMs: 30000,
  })

  return (
    <div className="h-full w-full flex flex-col bg-[#0a0a0a] border border-cyan-500/20 rounded overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-2 py-1 border-b border-cyan-500/20 bg-[#000] text-2xs font-mono">
        <div className="flex items-center gap-2">
          <span className="text-cyan-400 font-bold tracking-wider">DEEP CHART</span>
          <span className="text-cyan-400/60">|</span>
          <select
            value={symbol}
            onChange={(e) => (window.location.hash = `#${e.target.value}`)}
            className="bg-[#0a0a0a] border border-cyan-500/30 text-cyan-300 text-[10px] px-1.5 py-0.5 rounded font-mono"
          >
            <option>XAUUSDm</option>
            <option>EURUSDm</option>
            <option>GBPUSDm</option>
          </select>
          <select
            value={tf}
            onChange={(e) => setTf(e.target.value)}
            className="bg-[#0a0a0a] border border-cyan-500/30 text-cyan-300 text-[10px] px-1.5 py-0.5 rounded font-mono"
          >
            {TF_OPTIONS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-1">
          {(Object.keys(activeIndicators) as Array<keyof typeof activeIndicators>).map((k) => (
            <button
              key={k}
              onClick={() => setActiveIndicators((s) => ({ ...s, [k]: !s[k] }))}
              className={cn(
                'px-1.5 py-0.5 text-[10px] font-mono rounded border transition-colors',
                activeIndicators[k]
                  ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40'
                  : 'bg-[#0a0a0a] text-fg-dim border-line',
              )}
            >
              {k}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1.5 text-cyan-300">
          {quote && (
            <>
              <span className="text-[10px]">O</span>
              <span className="text-[10px] num">{formatIN(quote.open, 2)}</span>
              <span className="text-[10px]">H</span>
              <span className="text-[10px] num">{formatIN(quote.high, 2)}</span>
              <span className="text-[10px]">L</span>
              <span className="text-[10px] num">{formatIN(quote.low, 2)}</span>
              <span className="text-[10px]">C</span>
              <span className={cn('text-[10px] num font-bold', pnlColor(quote.changePct))}>
                {formatIN(quote.ltp, 2)}
              </span>
              <span className={cn('text-[10px] num', pnlColor(quote.changePct))}>
                {quote.change >= 0 ? '+' : ''}
                {quote.changePct.toFixed(2)}%
              </span>
            </>
          )}
        </div>
      </div>

      {/* Chart */}
      {candles && candles.length > 0 ? (
        <div className="flex-1 min-h-0 relative">
          <AMTChart
            candles={candles}
            livePrice={quote?.ltp}
            symbol={symbol}
            height={undefined}
            showIndicators={true}
            showVolume={config.showVolume !== false}
            showDelta={true}
          />
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-cyan-400/40 text-xs font-mono">
          Loading chart...
        </div>
      )}

      {/* Footer bar */}
      <div className="px-2 py-0.5 border-t border-cyan-500/20 bg-[#000] text-[9px] font-mono text-cyan-400/70 flex items-center justify-between">
        <span>
          {candles?.length || 0} bars · {tf} · {symbol}
        </span>
        <span>
          {quote && (
            <>
              V: {quote.volume.toLocaleString()} · VWAP: {formatIN(quote.vwap, 2)}
            </>
          )}
        </span>
      </div>
    </div>
  )
}
