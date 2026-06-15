import { Panel } from '@/components/ui/Panel'
import { Pill } from '@/components/ui/Pill'
import { CandlestickChart, calcEMA, calcSMA, calcBollingerBands, type IndicatorOverlay } from '@/components/ui/CandlestickChart'
import { useMemo, useState, useEffect, useRef } from 'react'
import { generateCandles, SYMBOLS } from '@/services/mockData'
import { cn, formatIN, formatTime, pnlColor } from '@/lib/utils'
import { Play, Pause, SkipBack, SkipForward, Rewind, FastForward, Camera, Volume2, Calendar, Activity, BarChart3, Plus, Save, Settings, Clock, ChevronRight, Target, TrendingUp, TrendingDown, Eye, Bookmark } from 'lucide-react'
import { useUIStore } from '@/store/uiStore'

const REPLAY_DATES = [
  { date: '2024-12-30', label: 'Budget Day' },
  { date: '2024-11-04', label: 'US Election' },
  { date: '2024-10-01', label: 'Festive Rally' },
  { date: '2024-08-05', label: 'Market Crash' },
  { date: '2024-06-04', label: 'Exit Polls' },
  { date: '2024-05-22', label: 'Election Results' },
]

export function Replay() {
  const { activeSymbol, setActiveSymbol } = useUIStore()
  const [date, setDate] = useState(REPLAY_DATES[0].date)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [time, setTime] = useState(0)        /* 0..100 % */
  const allCandles = useMemo(() => generateCandles(activeSymbol, '5m', 200), [activeSymbol])
  const intervalRef = useRef<number | null>(null)

  // Simulate replay
  useEffect(() => {
    if (playing) {
      intervalRef.current = window.setInterval(() => {
        setTime((t) => {
          if (t >= 100) {
            setPlaying(false)
            return 100
          }
          return t + 0.5
        })
      }, 100 / speed)
    } else if (intervalRef.current) {
      clearInterval(intervalRef.current)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [playing, speed])

  const visibleCandles = useMemo(() => {
    const end = Math.floor((time / 100) * allCandles.length)
    return allCandles.slice(0, Math.max(20, end))
  }, [allCandles, time])

  const indicators: IndicatorOverlay[] = useMemo(() => {
    const close = visibleCandles.map((c) => c.close)
    return [
      { name: 'EMA 9', type: 'line', data: calcEMA(close, 9), color: '#3b82f6', paneIndex: 0 },
      { name: 'SMA 20', type: 'line', data: calcSMA(close, 20), color: '#f59e0b', paneIndex: 0 },
    ]
  }, [visibleCandles])

  // Mock trades taken during replay
  const replayTrades = [
    { time: 18, side: 'BUY' as const, symbol: activeSymbol, qty: 100, entry: visibleCandles[18]?.close || 0, exit: visibleCandles[28]?.close || 0, pnl: 4520, reason: 'HalfTrend bullish flip' },
    { time: 45, side: 'BUY' as const, symbol: activeSymbol, qty: 50, entry: visibleCandles[45]?.close || 0, exit: visibleCandles[60]?.close || 0, pnl: -1240, reason: 'SL hit' },
    { time: 72, side: 'SELL' as const, symbol: activeSymbol, qty: 80, entry: visibleCandles[72]?.close || 0, exit: visibleCandles[88]?.close || 0, pnl: 3280, reason: 'Target' },
  ]

  const markers = replayTrades.map((t) => ({
    timestamp: allCandles[Math.floor((t.time / 100) * allCandles.length)]?.timestamp || Date.now(),
    price: t.entry,
    type: t.side as 'BUY' | 'SELL',
    text: t.side,
  }))

  return (
    <div className="h-full grid grid-cols-12 gap-2 p-2">
      {/* Left: Sessions */}
      <Panel className="col-span-2" title="Sessions" noPadding>
        <div className="p-2 border-b border-line space-y-1.5">
          <button className="w-full btn btn-primary text-xs">
            <Plus className="h-3.5 w-3.5" /> New Session
          </button>
          <div className="flex items-center gap-1.5 px-2 h-7 bg-bg-0 border border-line rounded">
            <Calendar className="h-3 w-3 text-fg-dim" />
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="flex-1 bg-transparent border-0 outline-none text-xs"
            />
          </div>
        </div>
        <div className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 220px)' }}>
          <div className="px-2 py-1.5 text-2xs font-semibold uppercase tracking-wider text-fg-dim bg-bg-2/40">
            Notable Days
          </div>
          {REPLAY_DATES.map((d) => (
            <button
              key={d.date}
              onClick={() => setDate(d.date)}
              className={cn(
                'w-full text-left px-3 py-2 hover:bg-bg-2 border-b border-line-subtle',
                date === d.date && 'bg-brand/10 border-l-2 border-brand',
              )}
            >
              <div className="text-xs font-semibold">{d.label}</div>
              <div className="text-2xs text-fg-dim font-mono">{d.date}</div>
            </button>
          ))}
        </div>
      </Panel>

      {/* Center: Chart + Player */}
      <div className="col-span-7 flex flex-col gap-2 min-h-0">
        <Panel
          title={`Replay · ${activeSymbol}`}
          subtitle={`${date} · ${visibleCandles.length} bars loaded`}
          noPadding
          actions={
            <>
              <Pill variant="info" dot>REC</Pill>
              <select
                value={activeSymbol}
                onChange={(e) => setActiveSymbol(e.target.value)}
                className="h-7 bg-bg-0 border border-line rounded px-2 text-xs"
              >
                {SYMBOLS.slice(0, 30).map((s) => (
                  <option key={s.symbol} value={s.symbol}>{s.symbol}</option>
                ))}
              </select>
            </>
          }
        >
          <CandlestickChart
            candles={visibleCandles}
            indicators={indicators}
            height={380}
            markers={markers}
          />
        </Panel>

        {/* Player Controls */}
        <Panel noPadding>
          <div className="p-3 space-y-2">
            <div className="flex items-center gap-2">
              <button onClick={() => setTime(0)} className="h-8 w-8 rounded bg-bg-2 hover:bg-bg-3 flex items-center justify-center">
                <SkipBack className="h-3.5 w-3.5" />
              </button>
              <button onClick={() => setTime(Math.max(0, time - 10))} className="h-8 w-8 rounded bg-bg-2 hover:bg-bg-3 flex items-center justify-center">
                <Rewind className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setPlaying(!playing)}
                className="h-10 w-10 rounded-full bg-brand text-white flex items-center justify-center hover:bg-brand-600"
              >
                {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4 ml-0.5" />}
              </button>
              <button onClick={() => setTime(Math.min(100, time + 10))} className="h-8 w-8 rounded bg-bg-2 hover:bg-bg-3 flex items-center justify-center">
                <FastForward className="h-3.5 w-3.5" />
              </button>
              <button onClick={() => setTime(100)} className="h-8 w-8 rounded bg-bg-2 hover:bg-bg-3 flex items-center justify-center">
                <SkipForward className="h-3.5 w-3.5" />
              </button>
              <div className="flex-1 mx-3">
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={time}
                  onChange={(e) => setTime(parseFloat(e.target.value))}
                  className="w-full accent-brand"
                />
              </div>
              <div className="flex items-center gap-1">
                {[0.5, 1, 2, 5, 10, 50].map((s) => (
                  <button
                    key={s}
                    onClick={() => setSpeed(s)}
                    className={cn(
                      'h-7 px-2 text-2xs rounded font-mono num',
                      speed === s ? 'bg-bg-3 text-fg' : 'bg-bg-2 text-fg-muted hover:bg-bg-3',
                    )}
                  >
                    {s}x
                  </button>
                ))}
              </div>
            </div>
            <div className="flex items-center justify-between text-2xs">
              <div className="flex items-center gap-3 text-fg-muted">
                <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {visibleCandles[0] ? formatTime(visibleCandles[0].timestamp) : '--:--'}</span>
                <span>→</span>
                <span>{visibleCandles[visibleCandles.length - 1] ? formatTime(visibleCandles[visibleCandles.length - 1].timestamp) : '--:--'}</span>
              </div>
              <div className="flex items-center gap-2">
                <button className="btn btn-ghost text-2xs"><Camera className="h-3 w-3" /> Screenshot</button>
                <button className="btn btn-ghost text-2xs"><Bookmark className="h-3 w-3" /> Bookmark</button>
                <button className="btn btn-secondary text-2xs"><Save className="h-3 w-3" /> Save</button>
              </div>
            </div>
          </div>
        </Panel>
      </div>

      {/* Right: Replay trades + state */}
      <div className="col-span-3 flex flex-col gap-2 min-h-0">
        <Panel title="Replay Trades" actions={<Pill variant="bull" className="text-2xs">+₹6,560</Pill>} noPadding>
          <div className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 540px)' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Side</th>
                  <th className="text-right">Entry</th>
                  <th className="text-right">P&L</th>
                </tr>
              </thead>
              <tbody>
                {replayTrades.map((t, i) => (
                  <tr key={i} className="cursor-pointer">
                    <td className="text-2xs font-mono text-fg-dim">{(t.time / 100 * 6.25).toFixed(2)}h</td>
                    <td>
                      <Pill variant={t.side === 'BUY' ? 'bull' : 'bear'} className="text-2xs w-10 justify-center">{t.side}</Pill>
                    </td>
                    <td className="text-right font-mono">{formatIN(t.entry)}</td>
                    <td className={cn('text-right font-mono font-semibold', pnlColor(t.pnl))}>
                      {t.pnl >= 0 ? '+' : ''}₹{formatIN(Math.abs(t.pnl))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="Market State" noPadding>
          <div className="p-3 space-y-2 text-2xs">
            <div className="flex justify-between"><span className="text-fg-dim">Session</span><span className="text-fg">09:15 - 15:30</span></div>
            <div className="flex justify-between"><span className="text-fg-dim">Phase</span><Pill variant="info" className="text-2xs">Mid-Session</Pill></div>
            <div className="flex justify-between"><span className="text-fg-dim">Trend</span><Pill variant="bull" className="text-2xs">Up</Pill></div>
            <div className="flex justify-between"><span className="text-fg-dim">Volatility</span><span className="text-warn">Med-High</span></div>
            <div className="flex justify-between"><span className="text-fg-dim">Volume</span><span className="text-bullish font-mono num">+1.8x avg</span></div>
            <div className="flex justify-between"><span className="text-fg-dim">Order Flow</span><span className="text-bullish">Net Buy</span></div>
            <div className="pt-2 border-t border-line flex justify-between">
              <span className="text-fg-dim">Signals Fired</span>
              <span className="font-mono num">4</span>
            </div>
            <div className="flex justify-between">
              <span className="text-fg-dim">Drawdown</span>
              <span className="text-bearish font-mono num">-1.4%</span>
            </div>
          </div>
        </Panel>

        <Panel title="Hypothetical P&L" noPadding>
          <div className="p-3">
            <div className="text-2xl font-semibold font-mono num text-bullish">+₹6,560</div>
            <div className="text-2xs text-fg-muted">+0.66% on ₹10L capital</div>
            <div className="grid grid-cols-2 gap-2 mt-2 text-2xs">
              <div className="p-1.5 bg-bg-2 rounded">
                <div className="text-fg-dim">Win Rate</div>
                <div className="font-mono num text-bullish">66.7%</div>
              </div>
              <div className="p-1.5 bg-bg-2 rounded">
                <div className="text-fg-dim">Avg Win</div>
                <div className="font-mono num">₹3,900</div>
              </div>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  )
}
