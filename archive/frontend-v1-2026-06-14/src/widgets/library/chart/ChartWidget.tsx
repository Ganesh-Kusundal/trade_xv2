import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { CandlestickChart, calcEMA, calcSMA, calcBollingerBands, type IndicatorOverlay } from '@/components/ui/CandlestickChart'
import { useUIStore } from '@/store/uiStore'
import { useMemo } from 'react'
import { cn, formatIN, pnlColor } from '@/lib/utils'
import type { WidgetProps } from '../../Widget'

interface ChartConfig {
  symbol?: string
  timeframe?: '1m' | '3m' | '5m' | '15m' | '1h' | '1d'
  showIndicators?: boolean
  title?: string
}

export default function ChartWidget({ config, refresh, loading, lastUpdated }: WidgetProps<ChartConfig>) {
  const { activeSymbol } = useUIStore()
  const symbol = config.symbol || activeSymbol || 'RELIANCE'
  const tf = config.timeframe || '5m'
  const showIndicators = config.showIndicators !== false

  const { data: candles } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.getCandles(symbol, (tf === '3m' ? '5m' : tf) as any, 200)),
    intervalMs: 5000,
  })
  const { data: quote } = useWidgetData({
    fetcher: () => import('@/widgets/DataLayer').then((m) => m.dataLayer.getQuote(symbol)),
    intervalMs: 1500,
  })

  const indicators: IndicatorOverlay[] = useMemo(() => {
    if (!candles || !showIndicators) return []
    const close = candles.map((c) => c.close)
    return [
      { name: 'EMA 9', type: 'line', data: calcEMA(close, 9), color: '#3b82f6', paneIndex: 0 },
      { name: 'SMA 20', type: 'line', data: calcSMA(close, 20), color: '#f59e0b', paneIndex: 0 },
      { name: 'BB', type: 'band', data: calcBollingerBands(close).upper, secondary: calcBollingerBands(close).lower, color: '#a855f7', secondaryColor: 'rgb(168 85 247 / 0.05)', paneIndex: 0 },
    ]
  }, [candles, showIndicators])

  return (
    <WidgetFrame
      id=""
      config={{ ...config, title: `CHART - ${symbol} (${tf})` }}
      loading={loading}
      lastUpdated={lastUpdated}
      refresh={refresh}
    >
      <div className="px-2 py-1 border-b border-line flex items-center justify-between text-2xs bg-bg-2/30">
        <div className="flex items-center gap-3 text-fg-muted">
          <span className="text-fg font-semibold">{symbol}</span>
          <span>{tf}</span>
          <span className="font-mono num">VWAP <span className="text-fg">2,901.10</span></span>
          <span className="font-mono num">EMA 50 <span className="text-fg">2,883.95</span></span>
        </div>
        {quote && (
          <span className={cn('font-mono num font-semibold', pnlColor(quote.changePct))}>
            {formatIN(quote.ltp)} {quote.changePct >= 0 ? '+' : ''}{quote.changePct.toFixed(2)}%
          </span>
        )}
      </div>
      {candles && candles.length > 0 ? (
        <CandlestickChart
          candles={candles}
          indicators={indicators}
          livePrice={quote?.ltp}
          height={undefined}
        />
      ) : (
        <div className="p-4 text-center text-fg-muted text-xs">Loading chart...</div>
      )}
    </WidgetFrame>
  )
}
