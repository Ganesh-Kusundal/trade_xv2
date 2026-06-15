import { Panel } from '@/components/ui/Panel'
import { Pill } from '@/components/ui/Pill'
import { Sparkline } from '@/components/ui/Sparkline'
import { CandlestickChart, calcEMA, calcSMA, calcBollingerBands, type IndicatorOverlay } from '@/components/ui/CandlestickChart'
import { SYMBOLS, generateCandles, INDICES } from '@/services/mockData'
import { useLiveQuotes } from '@/services/liveSimulator'
import { useMemo, useState } from 'react'
import { formatIN, pnlColor, cn, formatNumber } from '@/lib/utils'
import { Search, Plus, Filter, Star, Activity, ChevronUp, ChevronDown, Settings2, LayoutGrid, List, BarChart3, ArrowUpDown, Eye, EyeOff } from 'lucide-react'
import { useUIStore } from '@/store/uiStore'

const SYMBOL_LIST = [
  ...SYMBOLS.slice(0, 25).map((s) => s.symbol),
  'MARUTI', 'TATAMOTORS', 'JSWSTEEL', 'TATASTEEL', 'HINDALCO',
  'POWERGRID', 'NTPC', 'BPCL', 'IOC', 'GAIL', 'ONGC',
  'TITAN', 'ASIANPAINT', 'MARICO', 'BRITANNIA', 'PIDILITIND',
  'COFORGE', 'PERSISTENT', 'MPHASIS', 'LTIM', 'OFSS',
].slice(0, 60)

export function Market() {
  const { activeSymbol, setActiveSymbol } = useUIStore()
  const quotes = useLiveQuotes({ symbols: SYMBOL_LIST, intervalMs: 1500 })
  const [filter, setFilter] = useState('')
  const [sortBy, setSortBy] = useState<'symbol' | 'ltp' | 'change' | 'volume'>('change')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  const filtered = useMemo(() => {
    const list = SYMBOL_LIST
      .map((s) => quotes[s])
      .filter(Boolean)
      .filter((q) => !filter || q.symbol.toLowerCase().includes(filter.toLowerCase()))
    list.sort((a, b) => {
      const av = sortBy === 'symbol' ? a.symbol : sortBy === 'ltp' ? a.ltp : sortBy === 'volume' ? a.volume : a.changePct
      const bv = sortBy === 'symbol' ? b.symbol : sortBy === 'ltp' ? b.ltp : sortBy === 'volume' ? b.volume : b.changePct
      const cmp = av < bv ? -1 : av > bv ? 1 : 0
      return sortDir === 'asc' ? cmp : -cmp
    })
    return list
  }, [quotes, filter, sortBy, sortDir])

  const selectedQuote = quotes[activeSymbol] || quotes['RELIANCE']
  const candles = useMemo(() => generateCandles(activeSymbol, '5m', 200), [activeSymbol])
  const indicators: IndicatorOverlay[] = useMemo(() => {
    const close = candles.map((c) => c.close)
    return [
      { name: 'EMA 9', type: 'line', data: calcEMA(close, 9), color: '#3b82f6', paneIndex: 0 },
      { name: 'SMA 20', type: 'line', data: calcSMA(close, 20), color: '#f59e0b', paneIndex: 0 },
      { name: 'BB', type: 'band', data: calcBollingerBands(close).upper, secondary: calcBollingerBands(close).lower, color: '#a855f7', secondaryColor: 'rgb(168 85 247 / 0.05)', paneIndex: 0 },
    ]
  }, [candles])

  const handleSort = (col: 'symbol' | 'ltp' | 'change' | 'volume') => {
    if (sortBy === col) setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    else { setSortBy(col); setSortDir('desc') }
  }

  return (
    <div className="h-full grid grid-cols-12 gap-2 p-2">
      {/* Watchlist */}
      <Panel
        className="col-span-3"
        title="Watchlist"
        subtitle="Live"
        noPadding
        actions={
          <>
            <button className="h-6 w-6 rounded hover:bg-bg-3 text-fg-muted flex items-center justify-center"><Plus className="h-3.5 w-3.5" /></button>
            <button className="h-6 w-6 rounded hover:bg-bg-3 text-fg-muted flex items-center justify-center"><Settings2 className="h-3.5 w-3.5" /></button>
          </>
        }
      >
        <div className="px-2 py-1.5 border-b border-line">
          <div className="flex items-center gap-1.5 px-2 h-7 bg-bg-0 border border-line rounded">
            <Search className="h-3 w-3 text-fg-dim" />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Search symbols..."
              className="flex-1 bg-transparent border-0 outline-none text-xs placeholder:text-fg-dim"
            />
          </div>
        </div>
        <div className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 180px)' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th onClick={() => handleSort('symbol')} className="cursor-pointer">
                  <span className="flex items-center gap-1">Symbol {sortBy === 'symbol' && (sortDir === 'asc' ? <ChevronUp className="h-2.5 w-2.5" /> : <ChevronDown className="h-2.5 w-2.5" />)}</span>
                </th>
                <th onClick={() => handleSort('ltp')} className="cursor-pointer text-right">LTP {sortBy === 'ltp' && (sortDir === 'asc' ? <ChevronUp className="h-2.5 w-2.5 inline" /> : <ChevronDown className="h-2.5 w-2.5 inline" />)}</th>
                <th onClick={() => handleSort('change')} className="cursor-pointer text-right">Chg% {sortBy === 'change' && (sortDir === 'asc' ? <ChevronUp className="h-2.5 w-2.5 inline" /> : <ChevronDown className="h-2.5 w-2.5 inline" />)}</th>
                <th onClick={() => handleSort('volume')} className="cursor-pointer text-right">Vol {sortBy === 'volume' && (sortDir === 'asc' ? <ChevronUp className="h-2.5 w-2.5 inline" /> : <ChevronDown className="h-2.5 w-2.5 inline" />)}</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((q) => (
                <tr
                  key={q.symbol}
                  onClick={() => setActiveSymbol(q.symbol)}
                  className={cn('cursor-pointer', q.symbol === activeSymbol && 'row-active')}
                >
                  <td>
                    <div className="flex items-center gap-1">
                      <Star className={cn('h-3 w-3', q.symbol === activeSymbol ? 'text-warning fill-warning' : 'text-fg-dim')} />
                      <span className="font-semibold">{q.symbol}</span>
                    </div>
                  </td>
                  <td className="text-right font-mono">{formatIN(q.ltp)}</td>
                  <td className={cn('text-right font-mono', pnlColor(q.changePct))}>
                    {q.changePct >= 0 ? '+' : ''}{q.changePct.toFixed(2)}%
                  </td>
                  <td className="text-right text-fg-muted font-mono text-2xs">{formatNumber(q.volume / 1000, 0)}K</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* Center: Chart + Orderbook */}
      <div className="col-span-6 flex flex-col gap-2 min-h-0">
        <Panel
          title={selectedQuote?.symbol || activeSymbol}
          subtitle={`${selectedQuote?.exchange || 'NSE'} · 5 Min`}
          actions={
            <>
              <Pill variant={selectedQuote?.changePct >= 0 ? 'bull' : 'bear'} dot className="text-xs">
                ₹{formatIN(selectedQuote?.ltp || 0)} {selectedQuote?.changePct >= 0 ? '+' : ''}{selectedQuote?.changePct.toFixed(2)}%
              </Pill>
              {['1m', '5m', '15m', '1h', '1d'].map((tf) => (
                <button
                  key={tf}
                  className={cn(
                    'h-6 px-2 text-2xs rounded font-medium',
                    tf === '5m' ? 'bg-bg-3 text-fg' : 'text-fg-muted hover:bg-bg-2'
                  )}
                >
                  {tf}
                </button>
              ))}
              <button className="h-6 w-6 rounded hover:bg-bg-3 text-fg-muted flex items-center justify-center"><BarChart3 className="h-3.5 w-3.5" /></button>
            </>
          }
          noPadding
        >
          <CandlestickChart
            candles={candles}
            indicators={indicators}
            livePrice={selectedQuote?.ltp}
            height={360}
          />
        </Panel>

        <div className="grid grid-cols-2 gap-2 flex-1 min-h-0">
          <Panel title="Market Depth" actions={<Pill variant="info" className="text-2xs">5 Levels</Pill>} noPadding>
            <div className="grid grid-cols-2 h-full">
              <div className="border-r border-line">
                <div className="px-2 py-1 text-2xs text-fg-dim uppercase tracking-wider bg-bearish/10 border-b border-line font-semibold">BID</div>
                <div className="space-y-0.5 p-1">
                  {Array.from({ length: 5 }).map((_, i) => {
                    const price = (selectedQuote?.ltp || 0) - (i + 1) * 0.5
                    const qty = Math.floor(1000 * (5 - i) * Math.random())
                    return (
                      <div key={i} className="flex items-center text-2xs font-mono px-1.5">
                        <span className="text-bearish flex-1">{formatIN(price)}</span>
                        <span className="text-fg-muted">{qty}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
              <div>
                <div className="px-2 py-1 text-2xs text-fg-dim uppercase tracking-wider bg-bullish/10 border-b border-line font-semibold">ASK</div>
                <div className="space-y-0.5 p-1">
                  {Array.from({ length: 5 }).map((_, i) => {
                    const price = (selectedQuote?.ltp || 0) + (i + 1) * 0.5
                    const qty = Math.floor(1000 * (5 - i) * Math.random())
                    return (
                      <div key={i} className="flex items-center text-2xs font-mono px-1.5">
                        <span className="text-bullish flex-1">{formatIN(price)}</span>
                        <span className="text-fg-muted">{qty}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          </Panel>

          <Panel title="Recent Trades" actions={<Pill variant="neutral" className="text-2xs">NSE</Pill>} noPadding>
            <div className="overflow-y-auto" style={{ maxHeight: '100%' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th className="text-right">Price</th>
                    <th className="text-right">Qty</th>
                    <th>Side</th>
                  </tr>
                </thead>
                <tbody>
                  {Array.from({ length: 12 }).map((_, i) => {
                    const isBuy = Math.random() > 0.5
                    const price = (selectedQuote?.ltp || 0) + (Math.random() - 0.5) * 5
                    const qty = Math.floor(50 + Math.random() * 500)
                    const d = new Date(Date.now() - i * 35000)
                    return (
                      <tr key={i}>
                        <td className="text-fg-dim font-mono text-2xs">{d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}</td>
                        <td className={cn('text-right font-mono', isBuy ? 'text-bullish' : 'text-bearish')}>{formatIN(price)}</td>
                        <td className="text-right font-mono">{qty}</td>
                        <td><Pill variant={isBuy ? 'bull' : 'bear'} className="text-2xs">{isBuy ? 'B' : 'S'}</Pill></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      </div>

      {/* Right: Order entry + Info */}
      <div className="col-span-3 flex flex-col gap-2 min-h-0">
        <Panel title={`${selectedQuote?.symbol || activeSymbol}`} subtitle="Quick Order" noPadding>
          <div className="p-3 space-y-2">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <div className="text-2xs text-fg-dim uppercase tracking-wider">LTP</div>
                <div className={cn('text-xl font-semibold font-mono num', pnlColor(selectedQuote?.change))}>{formatIN(selectedQuote?.ltp || 0)}</div>
              </div>
              <div className="text-right">
                <div className="text-2xs text-fg-dim uppercase tracking-wider">Change</div>
                <div className={cn('text-xl font-semibold font-mono num', pnlColor(selectedQuote?.changePct))}>{formatPercent(selectedQuote?.changePct || 0)}</div>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-1.5 text-2xs">
              <div>
                <div className="text-fg-dim">Open</div>
                <div className="font-mono">{formatIN(selectedQuote?.open || 0)}</div>
              </div>
              <div>
                <div className="text-fg-dim">High</div>
                <div className="font-mono text-bullish">{formatIN(selectedQuote?.high || 0)}</div>
              </div>
              <div>
                <div className="text-fg-dim">Low</div>
                <div className="font-mono text-bearish">{formatIN(selectedQuote?.low || 0)}</div>
              </div>
              <div>
                <div className="text-fg-dim">VWAP</div>
                <div className="font-mono">{formatIN(selectedQuote?.vwap || 0)}</div>
              </div>
              <div>
                <div className="text-fg-dim">Prev</div>
                <div className="font-mono">{formatIN(selectedQuote?.prevClose || 0)}</div>
              </div>
              <div>
                <div className="text-fg-dim">Volume</div>
                <div className="font-mono">{formatNumber((selectedQuote?.volume || 0) / 1000, 0)}K</div>
              </div>
            </div>
            <div className="pt-2 border-t border-line space-y-1.5">
              <div className="flex justify-between text-2xs">
                <span className="text-fg-dim">OI</span>
                <span className="font-mono num">{formatNumber(selectedQuote?.oi || 0)}</span>
              </div>
              <div className="flex justify-between text-2xs">
                <span className="text-fg-dim">OI Change</span>
                <span className={cn('font-mono num', pnlColor(selectedQuote?.oiChange || 0))}>
                  {formatNumber(selectedQuote?.oiChange || 0)}
                </span>
              </div>
              <div className="flex justify-between text-2xs">
                <span className="text-fg-dim">Bid / Ask</span>
                <span className="font-mono num">
                  <span className="text-bearish">{formatIN(selectedQuote?.bid || 0)}</span>
                  <span className="text-fg-dim mx-1">/</span>
                  <span className="text-bullish">{formatIN(selectedQuote?.ask || 0)}</span>
                </span>
              </div>
            </div>
          </div>
        </Panel>

        <Panel title="Order Entry" noPadding className="flex-1 min-h-0">
          <div className="p-3 space-y-2">
            <div className="grid grid-cols-3 gap-1.5 text-2xs">
              <button className="h-7 bg-bg-2 hover:bg-bg-3 rounded text-fg-muted">CNC</button>
              <button className="h-7 bg-brand text-white rounded font-semibold">MIS</button>
              <button className="h-7 bg-bg-2 hover:bg-bg-3 rounded text-fg-muted">NRML</button>
            </div>
            <div>
              <label className="text-2xs text-fg-dim uppercase tracking-wider">Qty</label>
              <div className="flex items-center gap-1 mt-1">
                {[50, 100, 200, 500].map((q) => (
                  <button key={q} className="flex-1 h-7 bg-bg-2 hover:bg-bg-3 rounded text-2xs">{q}</button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-2xs text-fg-dim uppercase tracking-wider">Price</label>
              <input
                defaultValue={formatIN(selectedQuote?.ltp || 0)}
                className="w-full h-9 bg-bg-0 border border-line rounded px-2 text-sm num mt-1 focus:border-brand"
              />
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              <div>
                <label className="text-2xs text-fg-dim uppercase tracking-wider">Stop</label>
                <input
                  defaultValue={formatIN((selectedQuote?.ltp || 0) * 0.99)}
                  className="w-full h-8 bg-bearish/10 border border-bearish/30 rounded px-2 text-xs num mt-1"
                />
              </div>
              <div>
                <label className="text-2xs text-fg-dim uppercase tracking-wider">Target</label>
                <input
                  defaultValue={formatIN((selectedQuote?.ltp || 0) * 1.02)}
                  className="w-full h-8 bg-bullish/10 border border-bullish/30 rounded px-2 text-xs num mt-1"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 pt-2">
              <button className="h-10 rounded bg-bearish text-white font-semibold hover:bg-red-600">SELL</button>
              <button className="h-10 rounded bg-bullish text-white font-semibold hover:bg-green-600">BUY</button>
            </div>
            <div className="text-2xs text-center text-fg-dim">
              Margin: ₹1,46,752 · Charges: ₹32
            </div>
          </div>
        </Panel>
      </div>
    </div>
  )
}

function formatPercent(v: number) {
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}
