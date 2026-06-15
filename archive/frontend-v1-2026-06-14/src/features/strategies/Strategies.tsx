import { Panel } from '@/components/ui/Panel'
import { Pill } from '@/components/ui/Pill'
import { Sparkline } from '@/components/ui/Sparkline'
import { LineChart } from '@/components/ui/LineChart'
import { STRATEGIES } from '@/services/mockData'
import { cn, formatIN, formatPercent, pnlColor, formatNumber, formatTime } from '@/lib/utils'
import { Play, Pause, Edit, Copy, Trash2, MoreVertical, Plus, Brain, GitBranch, Target, Shield, TrendingUp, Activity, Zap, BarChart3, Settings, FlaskConical, CheckCircle2, AlertCircle, Clock } from 'lucide-react'
import { useState, useMemo } from 'react'
import type { Strategy } from '@/types/trading'

export function Strategies() {
  const [selected, setSelected] = useState<Strategy>(STRATEGIES[0])
  const [tab, setTab] = useState<'overview' | 'blocks' | 'backtest' | 'logs' | 'params'>('overview')

  const equityCurve = useMemo(() => {
    const pts = []
    let eq = selected.capital
    for (let i = 0; i < 90; i++) {
      eq *= 1 + (Math.sin(i / 5) * 0.003 + 0.0028 + (Math.random() - 0.5) * 0.005)
      pts.push({ x: i, y: eq })
    }
    return pts
  }, [selected])

  return (
    <div className="h-full grid grid-cols-12 gap-2 p-2">
      {/* List */}
      <Panel
        className="col-span-3"
        title="Strategies"
        subtitle={`${STRATEGIES.length} configured`}
        actions={
          <>
            <button className="h-6 w-6 rounded hover:bg-bg-3 text-fg-muted flex items-center justify-center"><Plus className="h-3.5 w-3.5" /></button>
            <button className="h-6 w-6 rounded hover:bg-bg-3 text-fg-muted flex items-center justify-center"><Settings className="h-3.5 w-3.5" /></button>
          </>
        }
        noPadding
      >
        <div className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 160px)' }}>
          {STRATEGIES.map((s) => (
            <button
              key={s.id}
              onClick={() => setSelected(s)}
              className={cn(
                'w-full text-left px-3 py-2.5 hover:bg-bg-2 border-b border-line-subtle',
                selected.id === s.id && 'bg-brand/10 border-l-2 border-brand',
              )}
            >
              <div className="flex items-center gap-1.5">
                <Pill
                  variant={s.status === 'LIVE' ? 'bull' : s.status === 'CERTIFIED' ? 'info' : s.status === 'TESTING' ? 'warn' : 'neutral'}
                  dot
                  className="text-2xs"
                >
                  {s.status}
                </Pill>
                <Pill variant="neutral" className="text-2xs">{s.type}</Pill>
              </div>
              <div className="font-semibold text-sm mt-1">{s.name}</div>
              <div className="text-2xs text-fg-dim mt-0.5 line-clamp-2">{s.description}</div>
              <div className="flex items-center gap-3 mt-1.5 text-2xs">
                <span className={cn('font-mono num font-semibold', pnlColor(s.pnl.today))}>
                  ₹{formatIN(s.pnl.today)}
                </span>
                <span className="text-fg-dim">·</span>
                <span className="text-fg-muted">{s.winRate.toFixed(1)}% WR</span>
                <span className="text-fg-dim">·</span>
                <span className="text-fg-muted">{s.trades.today} trd</span>
              </div>
            </button>
          ))}
        </div>
      </Panel>

      {/* Detail */}
      <div className="col-span-9 flex flex-col gap-2 min-h-0">
        <Panel
          title={selected.name}
          subtitle={selected.description}
          noPadding
          actions={
            <>
              <Pill
                variant={selected.status === 'LIVE' ? 'bull' : selected.status === 'CERTIFIED' ? 'info' : selected.status === 'TESTING' ? 'warn' : 'neutral'}
                dot
              >
                {selected.status}
              </Pill>
              <Pill variant="neutral" className="text-2xs">{selected.type}</Pill>
              <Pill variant="neutral" className="text-2xs">{selected.universe}</Pill>
              {selected.status === 'LIVE' ? (
                <button className="btn btn-secondary"><Pause className="h-3.5 w-3.5" /> Pause</button>
              ) : (
                <button className="btn btn-primary"><Play className="h-3.5 w-3.5" /> Activate</button>
              )}
              <button className="btn btn-secondary"><Edit className="h-3.5 w-3.5" /> Edit</button>
              <button className="btn btn-ghost"><Copy className="h-3.5 w-3.5" /></button>
              <button className="btn btn-ghost"><MoreVertical className="h-3.5 w-3.5" /></button>
            </>
          }
        >
          <div className="flex items-center gap-1 border-b border-line px-2">
            {(['overview', 'blocks', 'backtest', 'logs', 'params'] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cn(
                  'h-8 px-3 text-xs font-medium relative',
                  tab === t ? 'text-brand' : 'text-fg-muted hover:text-fg',
                )}
              >
                {t.charAt(0).toUpperCase() + t.slice(1)}
                {tab === t && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-brand" />}
              </button>
            ))}
          </div>

          {tab === 'overview' && (
            <div className="p-3 space-y-3">
              {/* KPIs */}
              <div className="grid grid-cols-4 gap-3">
                {[
                  { label: 'Today P&L', value: `₹${formatIN(selected.pnl.today)}`, color: selected.pnl.today, sub: `${selected.trades.today} trades` },
                  { label: 'Total P&L', value: `₹${formatIN(selected.pnl.total)}`, color: selected.pnl.total, sub: `${selected.trades.total} trades` },
                  { label: 'Win Rate', value: `${selected.winRate.toFixed(1)}%`, color: null, sub: `${selected.trades.winning}W / ${selected.trades.losing}L` },
                  { label: 'Sharpe', value: selected.sharpe.toFixed(2), color: null, sub: `Risk-adj.` },
                ].map((kpi, i) => (
                  <div key={i} className="p-3 bg-bg-2 rounded border border-line">
                    <div className="text-2xs text-fg-dim uppercase tracking-wider">{kpi.label}</div>
                    <div className={cn('text-2xl font-semibold font-mono num mt-1', kpi.color != null && pnlColor(kpi.color))}>
                      {kpi.value}
                    </div>
                    <div className="text-2xs text-fg-muted mt-1">{kpi.sub}</div>
                  </div>
                ))}
              </div>

              {/* Equity curve */}
              <Panel title="Live Equity Curve" subtitle="Last 90 days" noPadding>
                <LineChart
                  data={equityCurve}
                  height={180}
                  yLabel={(v) => `₹${(v / 1000).toFixed(0)}K`}
                  xLabel={(v) => `D${v + 1}`}
                />
              </Panel>

              {/* Recent trades */}
              <Panel title="Recent Trades" noPadding>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Symbol</th>
                      <th>Side</th>
                      <th className="text-right">Qty</th>
                      <th className="text-right">Entry</th>
                      <th className="text-right">Exit</th>
                      <th className="text-right">P&L</th>
                      <th>Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Array.from({ length: 8 }).map((_, i) => {
                      const isWin = Math.random() > 0.4
                      const sym = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'SBIN'][i % 5]
                      const qty = 50 + Math.floor(Math.random() * 150)
                      const entry = 1000 + Math.random() * 2000
                      const exit = entry * (1 + (isWin ? 0.015 : -0.008) * (1 + Math.random()))
                      const pnl = (exit - entry) * qty * (Math.random() > 0.5 ? 1 : -1)
                      return (
                        <tr key={i}>
                          <td className="text-fg-dim font-mono text-2xs">{formatTime(Date.now() - i * 3600_000)}</td>
                          <td className="font-semibold">{sym}</td>
                          <td>
                            <Pill variant={Math.random() > 0.5 ? 'bull' : 'bear'} className="text-2xs w-10 justify-center">
                              {Math.random() > 0.5 ? 'BUY' : 'SELL'}
                            </Pill>
                          </td>
                          <td className="text-right font-mono">{qty}</td>
                          <td className="text-right font-mono">{formatIN(entry)}</td>
                          <td className="text-right font-mono">{formatIN(exit)}</td>
                          <td className={cn('text-right font-mono font-semibold', pnlColor(pnl))}>
                            {pnl >= 0 ? '+' : ''}₹{formatIN(Math.abs(pnl))}
                          </td>
                          <td className="text-2xs text-fg-muted">{['Target hit', 'SL hit', 'EOD exit', 'Trail SL'][i % 4]}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </Panel>
            </div>
          )}

          {tab === 'blocks' && (
            <div className="p-3 grid grid-cols-2 gap-3">
              <Panel title="Entry Block" actions={<Pill variant="info" className="text-2xs">{selected.entry.logic}</Pill>}>
                <div className="space-y-1.5">
                  <div className="text-2xs text-fg-dim">Indicators</div>
                  <div className="flex flex-wrap gap-1.5">
                    {selected.entry.indicators.map((i) => (
                      <Pill key={i} variant="brand" className="text-2xs">{i}</Pill>
                    ))}
                  </div>
                  <div className="text-2xs text-fg-dim mt-3">Conditions</div>
                  {selected.entry.conditions.map((c, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs px-2 py-1 bg-bg-2 rounded">
                      <span className="text-fg-dim font-mono">{i + 1}</span>
                      <span>{c}</span>
                    </div>
                  ))}
                  {selected.entry.time && (
                    <div className="text-2xs text-fg-dim mt-3">
                      Time window: <span className="text-fg font-mono">{selected.entry.time.from} - {selected.entry.time.to}</span>
                    </div>
                  )}
                </div>
              </Panel>

              <Panel title="Exit Block" actions={<Pill variant="bear" className="text-2xs">{selected.exit.logic}</Pill>}>
                <div className="space-y-1.5">
                  <div className="text-2xs text-fg-dim">Indicators</div>
                  <div className="flex flex-wrap gap-1.5">
                    {selected.exit.indicators.map((i) => (
                      <Pill key={i} variant="brand" className="text-2xs">{i}</Pill>
                    ))}
                  </div>
                  <div className="text-2xs text-fg-dim mt-3">Conditions</div>
                  {selected.exit.conditions.map((c, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs px-2 py-1 bg-bg-2 rounded">
                      <span className="text-fg-dim font-mono">{i + 1}</span>
                      <span>{c}</span>
                    </div>
                  ))}
                </div>
              </Panel>

              <Panel title="Risk Management" className="col-span-2">
                <div className="grid grid-cols-4 gap-3">
                  <div className="p-2 bg-bg-2 rounded border border-line">
                    <div className="text-2xs text-fg-dim">Stop Loss</div>
                    <div className="text-xl font-semibold font-mono num text-bearish">-{selected.risk.stopLoss}%</div>
                  </div>
                  <div className="p-2 bg-bg-2 rounded border border-line">
                    <div className="text-2xs text-fg-dim">Target</div>
                    <div className="text-xl font-semibold font-mono num text-bullish">+{selected.risk.target}%</div>
                  </div>
                  <div className="p-2 bg-bg-2 rounded border border-line">
                    <div className="text-2xs text-fg-dim">Position Size</div>
                    <div className="text-xl font-semibold font-mono num">{selected.risk.positionSize}%</div>
                  </div>
                  <div className="p-2 bg-bg-2 rounded border border-line">
                    <div className="text-2xs text-fg-dim">Max Positions</div>
                    <div className="text-xl font-semibold font-mono num">{selected.risk.maxPositions}</div>
                  </div>
                </div>
              </Panel>
            </div>
          )}

          {tab === 'backtest' && (
            <div className="p-3">
              <div className="text-center py-8">
                <FlaskConical className="h-12 w-12 text-fg-dim mx-auto mb-2" />
                <div className="text-sm text-fg-muted">Run backtest to see historical performance</div>
                <button className="mt-3 btn btn-primary">Run Backtest</button>
              </div>
            </div>
          )}

          {tab === 'logs' && (
            <div className="p-3">
              <div className="bg-bg-0 border border-line rounded p-3 font-mono text-2xs space-y-1">
                {[
                  { time: '10:24:18', level: 'INFO', msg: 'Position opened: RELIANCE BUY 100 @ 2,935.40' },
                  { time: '10:18:42', level: 'INFO', msg: 'Signal: HDFCBANK BUY (RSI 58, Vol 1.8x)' },
                  { time: '10:12:05', level: 'WARN', msg: 'SLIPPAGE 0.05% on SBIN' },
                  { time: '10:05:33', level: 'INFO', msg: 'Scanner: 4 candidates detected' },
                  { time: '09:48:12', level: 'INFO', msg: 'HalfTrend bullish flip detected' },
                  { time: '09:30:00', level: 'INFO', msg: 'Strategy activated for the day' },
                ].map((log, i) => (
                  <div key={i} className="flex gap-3">
                    <span className="text-fg-dim">{log.time}</span>
                    <span className={cn(
                      'font-semibold w-12',
                      log.level === 'INFO' ? 'text-info' : log.level === 'WARN' ? 'text-warning' : 'text-bearish',
                    )}>{log.level}</span>
                    <span className="text-fg-muted">{log.msg}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {tab === 'params' && (
            <div className="p-3">
              <Panel title="Strategy Parameters">
                <div className="grid grid-cols-2 gap-3">
                  {Object.entries({
                    rsi_period: 14,
                    rsi_oversold: 30,
                    rsi_overbought: 70,
                    atr_period: 14,
                    atr_multiplier: 1.5,
                    sma_fast: 9,
                    sma_slow: 21,
                    vwap_threshold: 0.5,
                  }).map(([k, v]) => (
                    <div key={k} className="flex items-center justify-between p-2 bg-bg-2 rounded border border-line">
                      <span className="text-xs font-mono">{k}</span>
                      <input
                        type="number"
                        defaultValue={v}
                        className="w-20 h-7 bg-bg-0 border border-line rounded px-2 text-xs num text-right focus:border-brand focus:outline-none"
                      />
                    </div>
                  ))}
                </div>
              </Panel>
            </div>
          )}
        </Panel>
      </div>
    </div>
  )
}
