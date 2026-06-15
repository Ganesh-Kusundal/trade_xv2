import { Panel } from '@/components/ui/Panel'
import { Pill } from '@/components/ui/Pill'
import { Sparkline } from '@/components/ui/Sparkline'
import { Distribution, Gauge } from '@/components/ui/Progress'
import { LineChart } from '@/components/ui/LineChart'
import { useLiveQuotes } from '@/services/liveSimulator'
import { CandlestickChart, calcSMA, calcEMA, calcBollingerBands, type IndicatorOverlay } from '@/components/ui/CandlestickChart'
import { generateCandles, POSITIONS, OPEN_ORDERS, PORTFOLIO, STRATEGIES, SIGNALS, RISK_METRICS } from '@/services/mockData'
import { useMemo } from 'react'
import { formatIN, formatPercent, pnlColor, cn } from '@/lib/utils'
import { TrendingUp, Target, Shield, Briefcase, ChevronRight } from 'lucide-react'
import { useUIStore } from '@/store/uiStore'

const DASH_SYMBOLS = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'SBIN', 'ITC', 'LT', 'AXISBANK', 'BHARTIARTL']
const RELIANCE_CANDLES = generateCandles('RELIANCE', '5m', 200)

function SparkFor({ ltp }: { ltp: number }) {
  const data = useMemo(() => {
    const arr = []
    for (let i = 0; i < 20; i++) arr.push(ltp * (1 + Math.sin(i / 3) * 0.01))
    return arr
  }, [ltp])
  return <Sparkline data={data} width={60} height={20} />
}

export function Dashboard() {
  const { setWorkspace } = useUIStore()
  const quotes = useLiveQuotes({ symbols: DASH_SYMBOLS, intervalMs: 1500 })

  const indicators: IndicatorOverlay[] = useMemo(() => {
    const close = RELIANCE_CANDLES.map((c) => c.close)
    return [
      { name: 'EMA 9', type: 'line', data: calcEMA(close, 9), color: '#3b82f6', lineWidth: 1.2, paneIndex: 0 },
      { name: 'SMA 20', type: 'line', data: calcSMA(close, 20), color: '#f59e0b', lineWidth: 1.2, paneIndex: 0 },
      { name: 'BB(20,2)', type: 'band', data: calcBollingerBands(close).upper, secondary: calcBollingerBands(close).lower, color: '#a855f7', secondaryColor: 'rgb(168 85 247 / 0.05)', paneIndex: 0 },
    ]
  }, [])

  const equityCurve = useMemo(() => {
    const pts = []
    const benchPts = []
    let eq = 1_000_000
    let bench = 1_000_000
    const now = Date.now()
    for (let i = 0; i < 252; i++) {
      eq *= 1 + (Math.sin(i / 8) * 0.003 + 0.0028)
      bench *= 1 + (Math.sin(i / 12) * 0.002 + 0.0015)
      pts.push({ x: now - (252 - i) * 86_400_000, y: eq })
      benchPts.push({ x: now - (252 - i) * 86_400_000, y: bench })
    }
    return { pts, benchPts }
  }, [])

  const totalPnl = POSITIONS.reduce((s, p) => s + p.pnl, 0)

  return (
    <div className="h-full overflow-auto p-3 space-y-3 bg-grid">
      <div className="grid grid-cols-12 gap-3">
        <Panel className="col-span-3" noPadding>
          <div className="p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="text-2xs uppercase tracking-wider text-fg-dim font-medium">Total Equity</div>
              <Briefcase className="h-3.5 w-3.5 text-fg-dim" />
            </div>
            <div className="text-xl font-semibold num truncate">₹{formatIN(PORTFOLIO.totalValue)}</div>
            <div className="flex items-center gap-2 mt-2">
              <Pill variant={PORTFOLIO.todayPnl >= 0 ? 'bull' : 'bear'} dot>
                {formatPercent(PORTFOLIO.todayPnlPct)}
              </Pill>
              <span className="text-2xs text-fg-muted">today</span>
              <span className="text-fg-dim">·</span>
              <span className={cn('text-2xs num font-mono', pnlColor(PORTFOLIO.todayPnl))}>
                ₹{formatIN(PORTFOLIO.todayPnl)}
              </span>
            </div>
            <div className="mt-3 pt-3 border-t border-line grid grid-cols-3 gap-2 text-2xs">
              <div>
                <div className="text-fg-dim uppercase tracking-wider">Invested</div>
                <div className="font-mono num text-fg">₹{formatIN(PORTFOLIO.investedValue)}</div>
              </div>
              <div>
                <div className="text-fg-dim uppercase tracking-wider">Cash</div>
                <div className="font-mono num text-fg">₹{formatIN(PORTFOLIO.availableCash)}</div>
              </div>
              <div>
                <div className="text-fg-dim uppercase tracking-wider">Buying Power</div>
                <div className="font-mono num text-fg">₹{formatIN(PORTFOLIO.buyingPower)}</div>
              </div>
            </div>
          </div>
        </Panel>

        <Panel className="col-span-3" noPadding>
          <div className="p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="text-2xs uppercase tracking-wider text-fg-dim font-medium">P&L (Today)</div>
              <TrendingUp className="h-3.5 w-3.5 text-bullish" />
            </div>
            <div className={cn('text-xl font-semibold num truncate', pnlColor(PORTFOLIO.todayPnl))}>
              ₹{formatIN(Math.abs(PORTFOLIO.todayPnl))}
            </div>
            <div className="flex items-center gap-2 mt-2">
              <Pill variant={PORTFOLIO.todayPnlPct >= 0 ? 'bull' : 'bear'} dot>
                {formatPercent(PORTFOLIO.todayPnlPct)}
              </Pill>
              <span className="text-2xs text-fg-muted">vs NIFTY 50 +0.21%</span>
            </div>
            <div className="mt-3 pt-3 border-t border-line grid grid-cols-3 gap-2 text-2xs">
              <div>
                <div className="text-fg-dim uppercase tracking-wider">Week</div>
                <div className={cn('font-mono num', pnlColor(PORTFOLIO.weekPnl))}>₹{formatIN(PORTFOLIO.weekPnl)}</div>
              </div>
              <div>
                <div className="text-fg-dim uppercase tracking-wider">Month</div>
                <div className={cn('font-mono num', pnlColor(PORTFOLIO.monthPnl))}>₹{formatIN(PORTFOLIO.monthPnl)}</div>
              </div>
              <div>
                <div className="text-fg-dim uppercase tracking-wider">Total</div>
                <div className={cn('font-mono num', pnlColor(PORTFOLIO.totalPnl))}>₹{formatIN(PORTFOLIO.totalPnl)}</div>
              </div>
            </div>
          </div>
        </Panel>

        <Panel className="col-span-3" noPadding>
          <div className="p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="text-2xs uppercase tracking-wider text-fg-dim font-medium">Win Rate</div>
              <Target className="h-3.5 w-3.5 text-info" />
            </div>
            <div className="text-xl font-semibold num">62.35%</div>
            <div className="flex items-center gap-2 mt-2">
              <Pill variant="info" dot>152W / 93L</Pill>
              <span className="text-2xs text-fg-muted">245 trades</span>
            </div>
            <div className="mt-3 pt-3 border-t border-line grid grid-cols-3 gap-2 text-2xs">
              <div>
                <div className="text-fg-dim uppercase tracking-wider">Sharpe</div>
                <div className="font-mono num text-bullish">1.85</div>
              </div>
              <div>
                <div className="text-fg-dim uppercase tracking-wider">Sortino</div>
                <div className="font-mono num text-bullish">2.45</div>
              </div>
              <div>
                <div className="text-fg-dim uppercase tracking-wider">Max DD</div>
                <div className="font-mono num text-bearish">-8.35%</div>
              </div>
            </div>
          </div>
        </Panel>

        <Panel className="col-span-3" noPadding>
          <div className="p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="text-2xs uppercase tracking-wider text-fg-dim font-medium">Risk Score</div>
              <Shield className="h-3.5 w-3.5 text-bullish" />
            </div>
            <div className="flex items-center gap-3">
              <Gauge value={28} size={70} thickness={6} label="VAR (1D)" />
              <div className="flex-1 space-y-1.5 text-2xs">
                <div className="flex justify-between">
                  <span className="text-fg-dim">Exposure</span>
                  <span className="font-mono num">{RISK_METRICS.exposure.net.toFixed(1)}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-fg-dim">Beta</span>
                  <span className="font-mono num">{RISK_METRICS.beta.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-fg-dim">Alpha</span>
                  <span className="font-mono num text-bullish">+{RISK_METRICS.alpha.toFixed(1)}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-fg-dim">Margin</span>
                  <span className="font-mono num">{RISK_METRICS.margin.utilization.toFixed(1)}%</span>
                </div>
              </div>
            </div>
          </div>
        </Panel>
      </div>

      <div className="grid grid-cols-12 gap-3">
        <Panel
          className="col-span-4"
          title="Equity Curve"
          subtitle="1Y · vs NIFTY 50"
          actions={
            <>
              <Pill variant="bull" dot>+85.42%</Pill>
              <Pill variant="neutral" className="text-2xs">vs +28.4%</Pill>
            </>
          }
        >
          <div className="text-xl font-semibold num">₹{formatIN(PORTFOLIO.totalValue)}</div>
          <div className="text-2xs text-fg-muted mb-2">+₹{formatIN(PORTFOLIO.totalPnl)} · 22.89% all-time</div>
          <LineChart
            data={equityCurve.pts}
            benchmark={equityCurve.benchPts}
            height={120}
            yLabel={(v) => `${(v / 100000).toFixed(0)}L`}
            xLabel={(v) => new Date(v).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })}
          />
          <div className="grid grid-cols-4 gap-2 mt-3 pt-3 border-t border-line text-2xs">
            <div>
              <div className="text-fg-dim uppercase tracking-wider">CAGR</div>
              <div className="font-mono num text-bullish">+28.5%</div>
            </div>
            <div>
              <div className="text-fg-dim uppercase tracking-wider">Calmar</div>
              <div className="font-mono num">2.15</div>
            </div>
            <div>
              <div className="text-fg-dim uppercase tracking-wider">Avg Win</div>
              <div className="font-mono num text-bullish">₹4,520</div>
            </div>
            <div>
              <div className="text-fg-dim uppercase tracking-wider">Avg Loss</div>
              <div className="font-mono num text-bearish">-₹2,450</div>
            </div>
          </div>
        </Panel>

        <Panel
          className="col-span-5"
          title="RELIANCE · NSE"
          subtitle="Intraday 5m · 18 Jun"
          actions={
            <>
              <Pill variant="bull" dot>+3.38%</Pill>
              <Pill variant="neutral">OI ↑</Pill>
              <Pill variant="info">RS 92</Pill>
            </>
          }
        >
          <CandlestickChart
            candles={RELIANCE_CANDLES}
            indicators={indicators}
            livePrice={quotes['RELIANCE']?.ltp || RELIANCE_CANDLES[RELIANCE_CANDLES.length - 1].close}
            height={220}
          />
          <div className="mt-2 flex items-center justify-between text-2xs">
            <div className="flex items-center gap-3 text-fg-muted">
              <span>HalfTrend(2.3) <span className="text-bullish">3,932.15</span></span>
              <span>VWAP <span className="text-fg">{formatIN(RELIANCE_CANDLES[RELIANCE_CANDLES.length - 1].vwap || 2930)}</span></span>
              <span>Vol <span className="text-fg">128.0K</span></span>
            </div>
            <button onClick={() => setWorkspace('research')} className="text-brand hover:underline flex items-center gap-1">
              Open in Research <ChevronRight className="h-3 w-3" />
            </button>
          </div>
        </Panel>

        <Panel
          className="col-span-3"
          title="P&L Distribution"
          subtitle="Winning vs Losing Days"
          actions={<Pill variant="neutral">{POSITIONS.length} Positions</Pill>}
        >
          <div className="flex items-center gap-4">
            <Distribution
              data={[
                { label: 'Winning Days', value: 152 },
                { label: 'Losing Days', value: 93 },
              ]}
              size={120}
              thickness={16}
              centerLabel="TOTAL TRADES"
              centerValue="245"
            />
            <div className="flex-1 space-y-2 text-2xs">
              <div>
                <div className="flex justify-between text-fg-muted">
                  <span>Winning Days</span>
                  <span className="font-mono num">152</span>
                </div>
                <div className="h-1.5 bg-bg-2 rounded mt-1 overflow-hidden">
                  <div className="h-full bg-bullish" style={{ width: `${(152 / 245) * 100}%` }} />
                </div>
              </div>
              <div>
                <div className="flex justify-between text-fg-muted">
                  <span>Losing Days</span>
                  <span className="font-mono num">93</span>
                </div>
                <div className="h-1.5 bg-bg-2 rounded mt-1 overflow-hidden">
                  <div className="h-full bg-bearish" style={{ width: `${(93 / 245) * 100}%` }} />
                </div>
              </div>
              <div className="pt-2 border-t border-line">
                <div className="text-fg-dim uppercase tracking-wider">Profit Factor</div>
                <div className="font-mono num text-bullish text-base">1.85x</div>
              </div>
            </div>
          </div>
        </Panel>
      </div>

      <div className="grid grid-cols-12 gap-3">
        <Panel
          className="col-span-4"
          title="Recent Scans"
          actions={
            <button onClick={() => setWorkspace('scanner')} className="text-2xs text-brand hover:underline flex items-center gap-1">
              View All <ChevronRight className="h-3 w-3" />
            </button>
          }
        >
          <div className="space-y-1.5">
            {[
              { name: 'RS Momentum Scan', universe: 'NIFTY 500', result: '+3.38%', sym: 'RELIANCE' },
              { name: 'Volume Breakout Scan', universe: 'NIFTY 500', result: '+1.40%', sym: 'TCS' },
              { name: 'OI Build-up Scan', universe: 'NIFTY 50', result: '+2.24%', sym: 'HDFCBANK' },
            ].map((s, i) => (
              <div key={i} className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-bg-2">
                <Pill variant="bull" dot className="text-2xs">▲</Pill>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium truncate">{s.name}</div>
                  <div className="text-2xs text-fg-dim">{s.universe}</div>
                </div>
                <div className="text-right">
                  <div className="text-2xs font-mono num text-bullish">{s.sym}</div>
                  <div className="text-2xs text-fg-muted">{s.result}</div>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel
          className="col-span-4"
          title="Active Strategies"
          actions={
            <button onClick={() => setWorkspace('strategies')} className="text-2xs text-brand hover:underline flex items-center gap-1">
              View All <ChevronRight className="h-3 w-3" />
            </button>
          }
        >
          <div className="space-y-1.5">
            {STRATEGIES.slice(0, 3).map((s) => (
              <div key={s.id} className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-bg-2">
                <Pill variant={s.status === 'LIVE' ? 'bull' : s.status === 'CERTIFIED' ? 'info' : 'warn'} dot className="w-12 justify-center">
                  {s.status}
                </Pill>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium truncate">{s.name}</div>
                  <div className="text-2xs text-fg-dim">{s.trades.today} trades today</div>
                </div>
                <div className="text-right">
                  <div className="text-2xs font-mono num text-bullish">+₹{formatIN(s.pnl.today)}</div>
                  <div className="text-2xs text-fg-muted">{s.winRate.toFixed(1)}% WR</div>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel
          className="col-span-4"
          title="Recent Signals"
          actions={
            <button onClick={() => setWorkspace('scanner')} className="text-2xs text-brand hover:underline flex items-center gap-1">
              View All <ChevronRight className="h-3 w-3" />
            </button>
          }
        >
          <div className="space-y-1.5">
            {SIGNALS.slice(0, 4).map((s) => (
              <div key={s.id} className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-bg-2">
                <Pill
                  variant={s.signalType === 'STRONG_BUY' ? 'bull' : s.signalType === 'BUY' ? 'info' : s.signalType === 'SELL' ? 'bear' : 'neutral'}
                  className="w-20 justify-center"
                >
                  {s.signalType.replace('_', ' ')}
                </Pill>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium">{s.symbol}</div>
                  <div className="text-2xs text-fg-dim truncate">{s.reasons[0]}</div>
                </div>
                <div className="text-right">
                  <div className="text-2xs font-mono num">{(s.confidence * 100).toFixed(0)}%</div>
                  <div className="text-2xs text-fg-muted">{s.strategy}</div>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <div className="grid grid-cols-12 gap-3">
        <Panel
          className="col-span-6"
          title="Open Positions"
          subtitle={`${POSITIONS.length} active · P&L ${totalPnl >= 0 ? '+' : ''}₹${formatIN(Math.abs(totalPnl))}`}
          actions={
            <button onClick={() => setWorkspace('positions')} className="text-2xs text-brand hover:underline flex items-center gap-1">
              All Positions <ChevronRight className="h-3 w-3" />
            </button>
          }
        >
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Qty</th>
                <th className="text-right">Avg</th>
                <th className="text-right">LTP</th>
                <th className="text-right">P&L</th>
                <th className="text-right">P&L %</th>
                <th>Sparkline</th>
              </tr>
            </thead>
            <tbody>
              {POSITIONS.map((p) => {
                const q = quotes[p.symbol]
                const ltp = q?.ltp || p.ltp
                return (
                  <tr key={p.symbol} className="cursor-pointer">
                    <td>
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-semibold">{p.symbol}</span>
                        <Pill variant="neutral" className="text-2xs">MIS</Pill>
                      </div>
                    </td>
                    <td>{p.quantity}</td>
                    <td className="text-right">{formatIN(p.avgPrice)}</td>
                    <td className="text-right font-semibold">{formatIN(ltp)}</td>
                    <td className={cn('text-right font-semibold', pnlColor(p.pnl))}>
                      {p.pnl >= 0 ? '+' : ''}₹{formatIN(Math.abs(p.pnl))}
                    </td>
                    <td className={cn('text-right', pnlColor(p.pnlPct))}>
                      {formatPercent(p.pnlPct)}
                    </td>
                    <td>
                      <SparkFor ltp={ltp} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </Panel>

        <Panel
          className="col-span-3"
          title="Open Orders"
          subtitle={`${OPEN_ORDERS.length} pending`}
          actions={
            <button onClick={() => setWorkspace('orders')} className="text-2xs text-brand hover:underline">
              All
            </button>
          }
        >
          <div className="space-y-1">
            {OPEN_ORDERS.map((o) => (
              <div key={o.orderId} className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-bg-2 text-xs">
                <Pill variant="info" className="w-10 justify-center">{o.side}</Pill>
                <div className="flex-1 min-w-0">
                  <div className="font-mono text-2xs text-fg-dim">{o.orderId.slice(-8)}</div>
                  <div className="font-medium">{o.symbol}</div>
                </div>
                <div className="text-right">
                  <div className="text-2xs text-fg-muted">{o.quantity} @ {formatIN(o.price)}</div>
                  <div className="text-2xs text-fg-dim">{o.orderType}</div>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel
          className="col-span-3"
          title="Quick Order"
          subtitle="Fast bracket order entry"
          actions={<Pill variant="info" className="text-2xs">Dhan Routed</Pill>}
        >
          <div className="space-y-2">
            <div>
              <label className="text-2xs text-fg-dim uppercase tracking-wider">Symbol</label>
              <div className="flex items-center gap-1.5 h-8 px-2 bg-bg-0 border border-line rounded mt-1">
                <input
                  defaultValue="RELIANCE"
                  className="flex-1 bg-transparent border-0 outline-none text-sm font-medium"
                />
                <Pill variant="info" className="text-2xs">NSE</Pill>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-2xs text-fg-dim uppercase tracking-wider">Qty</label>
                <input
                  defaultValue={100}
                  className="w-full h-8 bg-bg-0 border border-line rounded px-2 text-sm num mt-1"
                />
              </div>
              <div>
                <label className="text-2xs text-fg-dim uppercase tracking-wider">Price</label>
                <input
                  defaultValue="2,935.40"
                  className="w-full h-8 bg-bg-0 border border-line rounded px-2 text-sm num mt-1"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-2xs text-fg-dim uppercase tracking-wider">Stop Loss</label>
                <input
                  defaultValue="2,910.00"
                  className="w-full h-8 bg-bearish/10 border border-bearish/30 rounded px-2 text-sm num mt-1"
                />
              </div>
              <div>
                <label className="text-2xs text-fg-dim uppercase tracking-wider">Target</label>
                <input
                  defaultValue="3,000.00"
                  className="w-full h-8 bg-bullish/10 border border-bullish/30 rounded px-2 text-sm num mt-1"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 pt-2">
              <button className="h-9 rounded bg-bearish text-white font-semibold text-sm hover:bg-red-600">SELL</button>
              <button className="h-9 rounded bg-bullish text-white font-semibold text-sm hover:bg-green-600">BUY</button>
            </div>
            <div className="grid grid-cols-3 gap-1.5 text-2xs pt-1">
              <button className="h-7 bg-bg-2 hover:bg-bg-3 rounded text-fg-muted">MKT</button>
              <button className="h-7 bg-bg-2 hover:bg-bg-3 rounded text-fg-muted">LMT</button>
              <button className="h-7 bg-bg-2 hover:bg-bg-3 rounded text-fg-muted">SL</button>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  )
}
