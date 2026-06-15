import { Panel } from '@/components/ui/Panel'
import { Pill } from '@/components/ui/Pill'
import { LineChart } from '@/components/ui/LineChart'
import { BACKTESTS, STRATEGIES } from '@/services/mockData'
import { cn, formatIN, formatPercent, pnlColor, formatNumber } from '@/lib/utils'
import { Play, Save, FlaskConical, Settings, BarChart3, Calendar, DollarSign, TrendingUp, TrendingDown, Activity, Target, Shield, Award, Zap, Plus, ChevronRight, Clock, Cpu, Download } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { BacktestResult } from '@/types/trading'

export function Backtest() {
  const [selected, setSelected] = useState<BacktestResult>(BACKTESTS[0])
  const [tab, setTab] = useState<'overview' | 'trades' | 'equity' | 'metrics' | 'monte'>('overview')
  const [showNew, setShowNew] = useState(false)

  return (
    <div className="h-full grid grid-cols-12 gap-2 p-2">
      {/* Sidebar: backtests list */}
      <Panel
        className="col-span-3"
        title="Backtests"
        actions={
          <>
            <button onClick={() => setShowNew(true)} className="h-6 w-6 rounded hover:bg-bg-3 text-fg-muted flex items-center justify-center"><Plus className="h-3.5 w-3.5" /></button>
          </>
        }
        noPadding
      >
        <div className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 160px)' }}>
          {BACKTESTS.map((bt) => (
            <button
              key={bt.id}
              onClick={() => setSelected(bt)}
              className={cn(
                'w-full text-left px-3 py-2.5 hover:bg-bg-2 border-b border-line-subtle',
                selected.id === bt.id && 'bg-brand/10 border-l-2 border-brand',
              )}
            >
              <div className="flex items-center gap-1.5">
                <Pill variant={bt.status === 'COMPLETED' ? 'bull' : bt.status === 'RUNNING' ? 'info' : 'warn'} dot className="text-2xs">
                  {bt.status}
                </Pill>
                <Pill variant="neutral" className="text-2xs">{bt.config.timeframe}</Pill>
              </div>
              <div className="font-semibold text-sm mt-1 truncate">{bt.name}</div>
              <div className="flex items-center gap-3 mt-1.5 text-2xs">
                <span className={cn('font-mono num font-semibold', pnlColor(bt.totalReturn))}>
                  {formatPercent(bt.totalReturn)}
                </span>
                <span className="text-fg-dim">·</span>
                <span className="text-fg-muted">{bt.sharpe.toFixed(2)} Sharpe</span>
                <span className="text-fg-dim">·</span>
                <span className={cn('text-fg-muted', pnlColor(bt.maxDrawdown))}>{bt.maxDrawdown.toFixed(1)}% DD</span>
              </div>
            </button>
          ))}
        </div>
      </Panel>

      {/* Detail */}
      <div className="col-span-9 flex flex-col gap-2 min-h-0">
        {showNew ? (
          <NewBacktest onClose={() => setShowNew(false)} onCreate={(b) => { setSelected(b); setShowNew(false) }} />
        ) : (
          <>
            <Panel
              title={selected.name}
              subtitle={`${selected.config.symbol} · ${selected.config.from} → ${selected.config.to}`}
              actions={
                <>
                  <Pill variant={selected.status === 'COMPLETED' ? 'bull' : 'info'} dot>{selected.status}</Pill>
                  <button className="btn btn-secondary"><FlaskConical className="h-3.5 w-3.5" /> Re-run</button>
                  <button className="btn btn-secondary"><Save className="h-3.5 w-3.5" /> Save</button>
                  <button className="btn btn-secondary"><Download className="h-3.5 w-3.5" /> Export</button>
                </>
              }
              noPadding
            >
              <div className="flex items-center gap-1 border-b border-line px-2">
                {(['overview', 'equity', 'trades', 'metrics', 'monte'] as const).map((t) => (
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

              {tab === 'overview' && <Overview bt={selected} />}
              {tab === 'equity' && <EquityTab bt={selected} />}
              {tab === 'trades' && <TradesTab bt={selected} />}
              {tab === 'metrics' && <MetricsTab bt={selected} />}
              {tab === 'monte' && <MonteCarloTab bt={selected} />}
            </Panel>
          </>
        )}
      </div>
    </div>
  )
}

function Overview({ bt }: { bt: BacktestResult }) {
  return (
    <div className="p-3 grid grid-cols-12 gap-3">
      <div className="col-span-8 space-y-3">
        {/* KPIs */}
        <div className="grid grid-cols-4 gap-3">
          {[
            { label: 'Total Return', value: formatPercent(bt.totalReturn), color: pnlColor(bt.totalReturn) },
            { label: 'CAGR', value: formatPercent(bt.cagr), color: pnlColor(bt.cagr) },
            { label: 'Sharpe', value: bt.sharpe.toFixed(2), color: 'text-fg' },
            { label: 'Max DD', value: `${bt.maxDrawdown.toFixed(2)}%`, color: pnlColor(bt.maxDrawdown) },
            { label: 'Win Rate', value: `${bt.winRate.toFixed(1)}%`, color: 'text-fg' },
            { label: 'Profit Factor', value: `${bt.profitFactor.toFixed(2)}x`, color: 'text-bullish' },
            { label: 'Sortino', value: bt.sortino.toFixed(2), color: 'text-fg' },
            { label: 'Calmar', value: bt.calmar.toFixed(2), color: 'text-fg' },
          ].map((k, i) => (
            <div key={i} className="p-2 bg-bg-2 rounded border border-line">
              <div className="text-2xs text-fg-dim uppercase tracking-wider">{k.label}</div>
              <div className={cn('text-lg font-semibold font-mono num', k.color)}>{k.value}</div>
            </div>
          ))}
        </div>

        {/* Equity chart */}
        <Panel title="Equity Curve" actions={<Pill variant="bull" className="text-2xs">vs NIFTY 50</Pill>} noPadding>
          <LineChart
            data={bt.equityCurve.map((p) => ({ x: p.timestamp, y: p.equity }))}
            benchmark={bt.equityCurve.map((p) => ({ x: p.timestamp, y: p.benchmark }))}
            height={220}
            yLabel={(v) => `₹${(v / 100000).toFixed(0)}L`}
            xLabel={(v) => new Date(v).toLocaleDateString('en-IN', { month: 'short', year: '2-digit' })}
          />
        </Panel>

        {/* Drawdown */}
        <Panel title="Drawdown" noPadding>
          <LineChart
            data={bt.equityCurve.map((p) => ({ x: p.timestamp, y: p.drawdown }))}
            height={120}
            zeroLine
            color="bear"
            yLabel={(v) => `${v.toFixed(1)}%`}
            xLabel={(v) => new Date(v).toLocaleDateString('en-IN', { month: 'short' })}
          />
        </Panel>
      </div>

      <div className="col-span-4 space-y-3">
        <Panel title="Config">
          <div className="space-y-2 text-2xs">
            {Object.entries(bt.config).map(([k, v]) => (
              <div key={k} className="flex justify-between">
                <span className="text-fg-dim uppercase tracking-wider">{k.replace(/_/g, ' ')}</span>
                <span className="font-mono num">{String(v)}</span>
              </div>
            ))}
            <div className="pt-2 border-t border-line flex justify-between">
              <span className="text-fg-dim uppercase tracking-wider">Duration</span>
              <span className="font-mono num">
                {((bt.completedAt || Date.now()) - bt.startedAt) / 1000 < 60
                  ? `${(((bt.completedAt || Date.now()) - bt.startedAt) / 1000).toFixed(0)}s`
                  : `${(((bt.completedAt || Date.now()) - bt.startedAt) / 60_000).toFixed(0)}m`}
              </span>
            </div>
          </div>
        </Panel>

        <Panel title="Trade Stats">
          <div className="space-y-2 text-2xs">
            <div className="flex justify-between"><span className="text-fg-dim">Total Trades</span><span className="font-mono num">{bt.trades.total}</span></div>
            <div className="flex justify-between"><span className="text-fg-dim">Winning</span><span className="font-mono num text-bullish">{bt.trades.winning}</span></div>
            <div className="flex justify-between"><span className="text-fg-dim">Losing</span><span className="font-mono num text-bearish">{bt.trades.losing}</span></div>
            <div className="flex justify-between"><span className="text-fg-dim">Avg Win</span><span className="font-mono num text-bullish">₹{formatIN(bt.trades.avgWin)}</span></div>
            <div className="flex justify-between"><span className="text-fg-dim">Avg Loss</span><span className="font-mono num text-bearish">₹{formatIN(bt.trades.avgLoss)}</span></div>
            <div className="flex justify-between"><span className="text-fg-dim">Avg RR</span><span className="font-mono num">{(Math.abs(bt.trades.avgWin / bt.trades.avgLoss)).toFixed(2)}x</span></div>
          </div>
        </Panel>
      </div>
    </div>
  )
}

function EquityTab({ bt }: { bt: BacktestResult }) {
  return (
    <div className="p-3 space-y-3">
      <Panel title="Equity Curve · Linear" noPadding>
        <LineChart
          data={bt.equityCurve.map((p) => ({ x: p.timestamp, y: p.equity }))}
          height={300}
          yLabel={(v) => `₹${(v / 100000).toFixed(1)}L`}
        />
      </Panel>
      <div className="grid grid-cols-2 gap-3">
        <Panel title="Underwater (Drawdown)" noPadding>
          <LineChart
            data={bt.equityCurve.map((p) => ({ x: p.timestamp, y: p.drawdown }))}
            height={180}
            zeroLine
            color="bear"
            yLabel={(v) => `${v.toFixed(1)}%`}
          />
        </Panel>
        <Panel title="Rolling Sharpe (30d)" noPadding>
          <LineChart
            data={bt.equityCurve.map((p, i) => ({ x: p.timestamp, y: 0.5 + Math.sin(i / 10) * 0.8 + (Math.random() - 0.5) * 0.2 }))}
            height={180}
            zeroLine
            yLabel={(v) => v.toFixed(2)}
          />
        </Panel>
      </div>
    </div>
  )
}

function TradesTab({ bt }: { bt: BacktestResult }) {
  const trades = useMemo(() => {
    return Array.from({ length: 30 }).map((_, i) => {
      const isWin = Math.random() > 0.4
      const sym = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'SBIN'][i % 5]
      const qty = 50 + Math.floor(Math.random() * 200)
      const entry = 1000 + Math.random() * 2000
      const exit = entry * (1 + (isWin ? 0.02 : -0.01) * (1 + Math.random()))
      const pnl = (exit - entry) * qty
      return {
        id: `T${i + 1}`,
        symbol: sym,
        side: Math.random() > 0.5 ? 'BUY' : 'SELL' as const,
        qty,
        entry,
        exit,
        pnl,
        pnlPct: ((exit - entry) / entry) * 100,
        entryTime: Date.now() - (30 - i) * 86_400_000,
        exitTime: Date.now() - (29 - i) * 86_400_000,
        duration: 30 + Math.random() * 120,
        reason: ['Target hit', 'SL hit', 'EOD', 'Trail SL'][i % 4],
      }
    })
  }, [bt])

  return (
    <div className="p-3">
      <Panel title={`Trade Log · ${trades.length} trades`} noPadding>
        <div className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 220px)' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Date</th>
                <th>Symbol</th>
                <th>Side</th>
                <th className="text-right">Qty</th>
                <th className="text-right">Entry</th>
                <th className="text-right">Exit</th>
                <th className="text-right">P&L</th>
                <th className="text-right">P&L %</th>
                <th className="text-right">Duration</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr key={t.id}>
                  <td className="font-mono text-2xs text-fg-dim">{t.id}</td>
                  <td className="text-2xs text-fg-muted font-mono">{new Date(t.entryTime).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}</td>
                  <td className="font-semibold">{t.symbol}</td>
                  <td>
                    <Pill variant={t.side === 'BUY' ? 'bull' : 'bear'} className="text-2xs w-10 justify-center">{t.side}</Pill>
                  </td>
                  <td className="text-right font-mono">{t.qty}</td>
                  <td className="text-right font-mono">{formatIN(t.entry)}</td>
                  <td className="text-right font-mono">{formatIN(t.exit)}</td>
                  <td className={cn('text-right font-mono font-semibold', pnlColor(t.pnl))}>
                    {t.pnl >= 0 ? '+' : ''}₹{formatIN(Math.abs(t.pnl))}
                  </td>
                  <td className={cn('text-right font-mono', pnlColor(t.pnlPct))}>
                    {t.pnlPct >= 0 ? '+' : ''}{t.pnlPct.toFixed(2)}%
                  </td>
                  <td className="text-right font-mono text-2xs text-fg-muted">{t.duration.toFixed(0)}m</td>
                  <td className="text-2xs text-fg-muted">{t.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  )
}

function MetricsTab({ bt }: { bt: BacktestResult }) {
  return (
    <div className="p-3 grid grid-cols-3 gap-3">
      <Panel title="Returns" className="col-span-2">
        <table className="data-table">
          <tbody>
            {[
              ['Total Return', formatPercent(bt.totalReturn)],
              ['CAGR', formatPercent(bt.cagr)],
              ['Avg Daily', '0.18%'],
              ['Best Day', '+3.85%'],
              ['Worst Day', '-2.42%'],
              ['Pos Days', '162 (64%)'],
              ['Neg Days', '90 (36%)'],
            ].map(([k, v]) => (
              <tr key={k}>
                <td className="text-fg-muted">{k}</td>
                <td className="text-right font-mono num">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      <Panel title="Risk-Adjusted">
        <table className="data-table">
          <tbody>
            {[
              ['Sharpe', bt.sharpe.toFixed(2)],
              ['Sortino', bt.sortino.toFixed(2)],
              ['Calmar', bt.calmar.toFixed(2)],
              ['Max DD', `${bt.maxDrawdown.toFixed(2)}%`],
              ['Volatility', '14.2%'],
              ['Beta', '0.95'],
              ['Alpha', '+4.8%'],
            ].map(([k, v]) => (
              <tr key={k}>
                <td className="text-fg-muted">{k}</td>
                <td className="text-right font-mono num">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  )
}

function MonteCarloTab({ bt }: { bt: BacktestResult }) {
  return (
    <div className="p-3 space-y-3">
      <Panel title="Monte Carlo Simulation" subtitle="10,000 paths · 252 days" actions={<Pill variant="info" className="text-2xs">95% CI</Pill>} noPadding>
        <LineChart
          data={Array.from({ length: 252 }).map((_, i) => ({ x: i, y: 100 + i * 0.5 + Math.sin(i / 8) * 8 + (Math.random() - 0.5) * 4 }))}
          height={240}
          yLabel={(v) => v.toFixed(0)}
          xLabel={(v) => `D${v + 1}`}
        />
      </Panel>
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: 'P95 (Best)', value: '+485%', color: 'text-bullish' },
          { label: 'P50 (Median)', value: '+185%', color: 'text-fg' },
          { label: 'P5 (Worst)', value: '-42%', color: 'text-bearish' },
          { label: 'P(Profit)', value: '92.4%', color: 'text-bullish' },
        ].map((s, i) => (
          <div key={i} className="p-3 bg-bg-2 rounded border border-line">
            <div className="text-2xs text-fg-dim uppercase tracking-wider">{s.label}</div>
            <div className={cn('text-2xl font-semibold font-mono num mt-1', s.color)}>{s.value}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function NewBacktest({ onClose, onCreate }: { onClose: () => void; onCreate: (b: BacktestResult) => void }) {
  const [strategy, setStrategy] = useState(STRATEGIES[0].name)
  return (
    <Panel
      title="New Backtest"
      subtitle="Configure and run a historical simulation"
      actions={
        <>
          <button onClick={onClose} className="btn btn-ghost">Cancel</button>
          <button
            onClick={() => onCreate(BACKTESTS[0])}
            className="btn btn-primary"
          >
            <Play className="h-3.5 w-3.5" /> Run Backtest
          </button>
        </>
      }
    >
      <div className="p-4 grid grid-cols-2 gap-4">
        <div>
          <label className="text-2xs text-fg-dim uppercase tracking-wider">Strategy</label>
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
            className="w-full h-9 bg-bg-0 border border-line rounded px-2 text-sm mt-1 focus:border-brand focus:outline-none"
          >
            {STRATEGIES.map((s) => <option key={s.id} value={s.name}>{s.name}</option>)}
          </select>
        </div>
        <div>
          <label className="text-2xs text-fg-dim uppercase tracking-wider">Universe</label>
          <select className="w-full h-9 bg-bg-0 border border-line rounded px-2 text-sm mt-1">
            <option>NIFTY 50</option>
            <option>NIFTY 100</option>
            <option>NIFTY 500</option>
            <option>Custom Watchlist</option>
          </select>
        </div>
        <div>
          <label className="text-2xs text-fg-dim uppercase tracking-wider">Start Date</label>
          <input type="date" defaultValue="2020-01-01" className="w-full h-9 bg-bg-0 border border-line rounded px-2 text-sm mt-1" />
        </div>
        <div>
          <label className="text-2xs text-fg-dim uppercase tracking-wider">End Date</label>
          <input type="date" defaultValue="2024-12-31" className="w-full h-9 bg-bg-0 border border-line rounded px-2 text-sm mt-1" />
        </div>
        <div>
          <label className="text-2xs text-fg-dim uppercase tracking-wider">Timeframe</label>
          <select className="w-full h-9 bg-bg-0 border border-line rounded px-2 text-sm mt-1">
            <option>1 minute</option>
            <option>5 minute</option>
            <option>15 minute</option>
            <option>1 hour</option>
            <option>Daily</option>
          </select>
        </div>
        <div>
          <label className="text-2xs text-fg-dim uppercase tracking-wider">Initial Capital (₹)</label>
          <input type="number" defaultValue={1000000} className="w-full h-9 bg-bg-0 border border-line rounded px-2 text-sm num mt-1" />
        </div>
        <div>
          <label className="text-2xs text-fg-dim uppercase tracking-wider">Slippage (%)</label>
          <input type="number" step="0.01" defaultValue={0.05} className="w-full h-9 bg-bg-0 border border-line rounded px-2 text-sm num mt-1" />
        </div>
        <div>
          <label className="text-2xs text-fg-dim uppercase tracking-wider">Brokerage (₹)</label>
          <input type="number" defaultValue={20} className="w-full h-9 bg-bg-0 border border-line rounded px-2 text-sm num mt-1" />
        </div>
        <div className="col-span-2 grid grid-cols-3 gap-2 pt-2">
          <button className="btn btn-secondary"><BarChart3 className="h-3.5 w-3.5" /> Walk-Forward</button>
          <button className="btn btn-secondary"><Activity className="h-3.5 w-3.5" /> Monte Carlo</button>
          <button className="btn btn-secondary"><Settings className="h-3.5 w-3.5" /> Advanced</button>
        </div>
      </div>
    </Panel>
  )
}
