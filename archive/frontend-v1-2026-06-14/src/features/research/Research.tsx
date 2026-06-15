import { Panel } from '@/components/ui/Panel'
import { Pill } from '@/components/ui/Pill'
import { CandlestickChart, calcEMA, calcSMA, calcRSI, calcATR, calcBollingerBands, calcVWAP, type IndicatorOverlay } from '@/components/ui/CandlestickChart'
import { useLiveCandles, useLiveQuotes } from '@/services/liveSimulator'
import { useMemo, useState } from 'react'
import { generateCandles, SYMBOLS } from '@/services/mockData'
import { cn, formatIN, pnlColor } from '@/lib/utils'
import { Search, Plus, BarChart3, TrendingUp, Activity, Settings2, Layers, Eye, EyeOff, X, Maximize2, BarChart2 } from 'lucide-react'
import { useUIStore } from '@/store/uiStore'

const INDICATOR_LIBRARY = [
  { group: 'Trend', items: ['EMA 9', 'EMA 21', 'SMA 20', 'SMA 50', 'SMA 200', 'VWAP', 'SuperTrend', 'HalfTrend', 'Ichimoku'] },
  { group: 'Momentum', items: ['RSI(14)', 'MACD', 'Stochastic', 'CCI', 'Williams %R', 'MFI'] },
  { group: 'Volatility', items: ['Bollinger Bands', 'ATR(14)', 'Keltner Channel', 'Donchian Channel', 'StdDev'] },
  { group: 'Volume', items: ['Volume', 'OBV', 'Volume Profile', 'Volume Oscillator', 'A/D Line', 'VWAP Bands'] },
  { group: 'Custom', items: ['Relative Strength', 'Market Breadth', 'Sector Rotation', 'Custom Formula'] },
]

export function Research() {
  const { activeSymbol, setActiveSymbol } = useUIStore()
  const initialCandles = useMemo(() => generateCandles(activeSymbol, '5m', 200), [activeSymbol])
  const { candles } = useLiveCandles({ symbol: activeSymbol, initialCandles, intervalMs: 1000 })
  const quotes = useLiveQuotes({ symbols: [activeSymbol], intervalMs: 1500 })
  const [activeIndicators, setActiveIndicators] = useState<string[]>(['EMA 9', 'SMA 20', 'VWAP', 'Bollinger Bands', 'RSI(14)', 'ATR(14)'])
  const [tf, setTf] = useState('5m')
  const [search, setSearch] = useState('')

  const close = candles.map((c) => c.close)
  const rsi = calcRSI(close, 14)
  const atr = calcATR(candles, 14)
  const bb = calcBollingerBands(close)
  const vwap = calcVWAP(candles)

  const indicators: IndicatorOverlay[] = useMemo(() => {
    const arr: IndicatorOverlay[] = []
    if (activeIndicators.includes('EMA 9')) arr.push({ name: 'EMA 9', type: 'line', data: calcEMA(close, 9), color: '#3b82f6', paneIndex: 0 })
    if (activeIndicators.includes('EMA 21')) arr.push({ name: 'EMA 21', type: 'line', data: calcEMA(close, 21), color: '#06b6d4', paneIndex: 0 })
    if (activeIndicators.includes('SMA 20')) arr.push({ name: 'SMA 20', type: 'line', data: calcSMA(close, 20), color: '#f59e0b', paneIndex: 0 })
    if (activeIndicators.includes('SMA 50')) arr.push({ name: 'SMA 50', type: 'line', data: calcSMA(close, 50), color: '#ec4899', paneIndex: 0 })
    if (activeIndicators.includes('Bollinger Bands')) arr.push({ name: 'BB', type: 'band', data: bb.upper, secondary: bb.lower, color: '#a855f7', secondaryColor: 'rgb(168 85 247 / 0.05)', paneIndex: 0 })
    if (activeIndicators.includes('VWAP')) arr.push({ name: 'VWAP', type: 'line', data: vwap, color: '#eab308', lineWidth: 1.5, paneIndex: 0 })
    return arr
  }, [activeIndicators, close, bb, vwap])

  const filteredSymbols = SYMBOLS.filter((s) => s.symbol.toLowerCase().includes(search.toLowerCase())).slice(0, 30)

  return (
    <div className="h-full grid grid-cols-12 gap-2 p-2">
      {/* Symbol Picker */}
      <Panel className="col-span-2" title="Symbols" noPadding>
        <div className="p-2 border-b border-line">
          <div className="flex items-center gap-1.5 px-2 h-7 bg-bg-0 border border-line rounded">
            <Search className="h-3 w-3 text-fg-dim" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Symbol..."
              className="flex-1 bg-transparent border-0 outline-none text-xs placeholder:text-fg-dim"
            />
          </div>
        </div>
        <div className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 160px)' }}>
          {filteredSymbols.map((s) => {
            const q = quotes[s.symbol]
            return (
              <button
                key={s.symbol}
                onClick={() => setActiveSymbol(s.symbol)}
                className={cn(
                  'w-full text-left px-2 py-1.5 hover:bg-bg-2 flex items-center justify-between text-xs',
                  activeSymbol === s.symbol && 'bg-brand/10 border-l-2 border-brand',
                )}
              >
                <div>
                  <div className="font-semibold">{s.symbol}</div>
                  <div className="text-2xs text-fg-dim truncate">{s.sector}</div>
                </div>
                {q && (
                  <div className="text-right">
                    <div className="font-mono num text-2xs">{formatIN(q.ltp)}</div>
                    <div className={cn('font-mono num text-2xs', pnlColor(q.changePct))}>
                      {q.changePct >= 0 ? '+' : ''}{q.changePct.toFixed(2)}%
                    </div>
                  </div>
                )}
              </button>
            )
          })}
        </div>
      </Panel>

      {/* Main Chart */}
      <div className="col-span-7 flex flex-col gap-2 min-h-0">
        <Panel
          title={activeSymbol}
          subtitle={`NSE · ${tf}`}
          actions={
            <>
              <Pill variant="info" dot className="text-2xs">Live</Pill>
              {['1m', '3m', '5m', '15m', '1h', '4h', '1d'].map((t) => (
                <button
                  key={t}
                  onClick={() => setTf(t)}
                  className={cn(
                    'h-6 px-2 text-2xs rounded font-medium',
                    tf === t ? 'bg-bg-3 text-fg' : 'text-fg-muted hover:bg-bg-2',
                  )}
                >
                  {t}
                </button>
              ))}
              <button className="h-6 w-6 rounded hover:bg-bg-3 text-fg-muted flex items-center justify-center"><Maximize2 className="h-3.5 w-3.5" /></button>
            </>
          }
          noPadding
        >
          <CandlestickChart
            candles={candles}
            indicators={indicators}
            livePrice={quotes[activeSymbol]?.ltp}
            height={460}
          />
        </Panel>

        <div className="grid grid-cols-2 gap-2 flex-1 min-h-0">
          {/* RSI Pane */}
          <Panel
            title="RSI (14)"
            actions={
              <div className="flex items-center gap-2 text-2xs">
                <Pill variant={rsi[rsi.length - 1] > 70 ? 'bear' : rsi[rsi.length - 1] < 30 ? 'bull' : 'neutral'}>
                  {rsi[rsi.length - 1]?.toFixed(1)}
                </Pill>
                <span className="text-fg-dim">{rsi[rsi.length - 1] > 70 ? 'Overbought' : rsi[rsi.length - 1] < 30 ? 'Oversold' : 'Neutral'}</span>
              </div>
            }
            noPadding
          >
            <CandlestickChart
              candles={candles.map((c, i) => ({ ...c, open: rsi[i] || 50, high: rsi[i] || 50, low: rsi[i] || 50, close: rsi[i] || 50 }))}
              height={140}
              showVolume={false}
            />
          </Panel>

          {/* ATR Pane */}
          <Panel
            title="ATR (14)"
            actions={
              <Pill variant="neutral" className="text-2xs">{atr[atr.length - 1]?.toFixed(2)}</Pill>
            }
            noPadding
          >
            <CandlestickChart
              candles={candles.map((c, i) => ({ ...c, open: atr[i] || 0, high: atr[i] || 0, low: atr[i] || 0, close: atr[i] || 0 }))}
              height={140}
              showVolume={false}
            />
          </Panel>
        </div>
      </div>

      {/* Right: Indicators + Studies */}
      <div className="col-span-3 flex flex-col gap-2 min-h-0">
        <Panel title="Indicators" subtitle={`${activeIndicators.length} active`} noPadding>
          <div className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 380px)' }}>
            {INDICATOR_LIBRARY.map((group) => (
              <div key={group.group} className="border-b border-line-subtle">
                <div className="px-2 py-1.5 text-2xs font-semibold uppercase tracking-wider text-fg-dim bg-bg-2/40 sticky top-0 z-10">
                  {group.group}
                </div>
                {group.items.map((item) => {
                  const active = activeIndicators.includes(item)
                  return (
                    <button
                      key={item}
                      onClick={() =>
                        setActiveIndicators((prev) =>
                          active ? prev.filter((x) => x !== item) : [...prev, item],
                        )
                      }
                      className={cn(
                        'w-full flex items-center justify-between px-2 py-1.5 text-xs hover:bg-bg-2',
                        active && 'bg-brand/10',
                      )}
                    >
                      <span className={cn(active ? 'text-brand' : 'text-fg-muted')}>{item}</span>
                      {active ? <Eye className="h-3 w-3 text-brand" /> : <EyeOff className="h-3 w-3 text-fg-dim" />}
                    </button>
                  )
                })}
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Active Studies" noPadding>
          <div className="p-2 flex flex-wrap gap-1.5">
            {activeIndicators.length === 0 && (
              <div className="text-2xs text-fg-dim py-2 text-center w-full">No active studies</div>
            )}
            {activeIndicators.map((ind) => (
              <Pill
                key={ind}
                variant="brand"
                className="cursor-pointer"
                dot
                onClick={() => setActiveIndicators((prev) => prev.filter((x) => x !== ind))}
              >
                {ind} <X className="h-2.5 w-2.5 ml-0.5" />
              </Pill>
            ))}
          </div>
        </Panel>

        <Panel title="Notes" subtitle="Chart annotations" noPadding className="flex-1 min-h-0">
          <div className="p-2">
            <textarea
              placeholder="Type observation, hypothesis, or thesis..."
              className="w-full h-32 bg-bg-0 border border-line rounded p-2 text-xs resize-none focus:border-brand focus:outline-none"
              defaultValue={`${activeSymbol} - Intraday observation:
- HalfTrend flipped bullish at 09:48
- Volume 1.8x avg on breakout
- RSI 58, room to run
- Key resistance: 2,950 (supply zone)
- Stop: below 2,900 (HalfTrend bear line)`}
            />
            <div className="mt-2 flex items-center gap-1.5">
              <button className="flex-1 h-7 bg-bg-2 hover:bg-bg-3 rounded text-xs">+ Drawing</button>
              <button className="flex-1 h-7 bg-bg-2 hover:bg-bg-3 rounded text-xs">+ Note</button>
              <button className="flex-1 h-7 bg-brand text-white rounded text-xs">Save</button>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  )
}
