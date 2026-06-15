import { Panel } from '@/components/ui/Panel'
import { Pill } from '@/components/ui/Pill'
import { Sparkline } from '@/components/ui/Sparkline'
import { LineChart } from '@/components/ui/LineChart'
import { STRATEGIES, BACKTESTS, PORTFOLIO } from '@/services/mockData'
import { cn, formatIN, pnlColor, formatPercent } from '@/lib/utils'
import { FileText, Download, Calendar, TrendingUp, TrendingDown, BarChart3, FileBarChart, Mail, Printer, Share2, FileSpreadsheet, Target, Activity, Award } from 'lucide-react'

const REPORTS = [
  { id: 'r-1', name: 'Daily P&L Report', period: 'Today', generated: Date.now() - 1000 * 60 * 30, size: '24 KB' },
  { id: 'r-2', name: 'Weekly Performance', period: 'This Week', generated: Date.now() - 1000 * 60 * 60 * 4, size: '142 KB' },
  { id: 'r-3', name: 'Monthly Strategy Audit', period: 'June 2025', generated: Date.now() - 1000 * 60 * 60 * 24 * 2, size: '485 KB' },
  { id: 'r-4', name: 'Tax P&L Statement', period: 'FY 2024-25', generated: Date.now() - 1000 * 60 * 60 * 24 * 12, size: '128 KB' },
  { id: 'r-5', name: 'Risk & Compliance', period: 'Q2 2025', generated: Date.now() - 1000 * 60 * 60 * 24 * 22, size: '512 KB' },
  { id: 'r-6', name: 'Backtest Results', period: 'Last 10', generated: Date.now() - 1000 * 60 * 60 * 24 * 3, size: '1.2 MB' },
]

export function Reports() {
  return (
    <div className="h-full p-2 space-y-2 overflow-y-auto">
      {/* Quick stats */}
      <div className="grid grid-cols-4 gap-2">
        {[
          { label: 'Total P&L (YTD)', value: `+₹${formatIN(PORTFOLIO.totalPnl)}`, sub: `${PORTFOLIO.totalPnlPct.toFixed(2)}% return`, icon: TrendingUp, color: 'text-bullish' },
          { label: 'Best Strategy', value: 'HalfTrend Intraday', sub: '₹2.45L · 28.5% CAGR', icon: Award, color: 'text-bullish' },
          { label: 'Win Rate', value: '62.35%', sub: '152W / 93L', icon: Target, color: 'text-fg' },
          { label: 'Sharpe Ratio', value: '1.85', sub: 'Risk-adj return', icon: Activity, color: 'text-bullish' },
        ].map((s, i) => {
          const Icon = s.icon
          return (
            <div key={i} className="p-3 bg-bg-1 border border-line rounded">
              <div className="flex items-center justify-between">
                <div className="text-2xs text-fg-dim uppercase tracking-wider font-medium">{s.label}</div>
                <Icon className="h-3.5 w-3.5 text-fg-dim" />
              </div>
              <div className={cn('text-2xl font-semibold font-mono num mt-1', s.color)}>{s.value}</div>
              <div className="text-2xs text-fg-muted mt-1">{s.sub}</div>
            </div>
          )
        })}
      </div>

      {/* Quick reports */}
      <Panel title="Generate Report" actions={
        <>
          <button className="btn btn-ghost"><Calendar className="h-3.5 w-3.5" /> Custom</button>
          <button className="btn btn-primary"><FileText className="h-3.5 w-3.5" /> Generate</button>
        </>
      }>
        <div className="grid grid-cols-4 gap-2">
          {[
            { icon: FileBarChart, name: 'Performance Report', desc: 'Detailed P&L, returns, attribution' },
            { icon: FileSpreadsheet, name: 'Trade Log', desc: 'All executed trades with analytics' },
            { icon: FileText, name: 'Tax Statement', desc: 'STCG, LTCG, turnover summary' },
            { icon: FileText, name: 'Risk Report', desc: 'VaR, drawdown, stress tests' },
          ].map((t) => {
            const Icon = t.icon
            return (
              <button key={t.name} className="p-3 bg-bg-2 hover:bg-bg-3 rounded border border-line text-left">
                <Icon className="h-5 w-5 text-brand mb-2" />
                <div className="text-sm font-semibold">{t.name}</div>
                <div className="text-2xs text-fg-muted mt-1">{t.desc}</div>
              </button>
            )
          })}
        </div>
      </Panel>

      {/* Recent reports */}
      <Panel title="Recent Reports" noPadding>
        <table className="data-table">
          <thead>
            <tr>
              <th>Report</th>
              <th>Period</th>
              <th>Generated</th>
              <th>Size</th>
              <th className="text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {REPORTS.map((r) => (
              <tr key={r.id} className="cursor-pointer">
                <td>
                  <div className="flex items-center gap-2">
                    <FileText className="h-3.5 w-3.5 text-brand" />
                    <span className="font-semibold">{r.name}</span>
                  </div>
                </td>
                <td className="text-fg-muted">{r.period}</td>
                <td className="text-2xs font-mono text-fg-muted">{new Date(r.generated).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</td>
                <td className="font-mono text-fg-muted text-2xs">{r.size}</td>
                <td className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    <button className="h-6 px-2 text-2xs rounded bg-bg-2 hover:bg-bg-3 text-fg-muted">
                      <Download className="h-3 w-3" />
                    </button>
                    <button className="h-6 px-2 text-2xs rounded bg-bg-2 hover:bg-bg-3 text-fg-muted">
                      <Mail className="h-3 w-3" />
                    </button>
                    <button className="h-6 px-2 text-2xs rounded bg-bg-2 hover:bg-bg-3 text-fg-muted">
                      <Share2 className="h-3 w-3" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      {/* Strategy performance summary */}
      <Panel title="Strategy Performance Summary" noPadding>
        <table className="data-table">
          <thead>
            <tr>
              <th>Strategy</th>
              <th className="text-right">Total P&L</th>
              <th className="text-right">Win Rate</th>
              <th className="text-right">Sharpe</th>
              <th className="text-right">Trades</th>
              <th className="text-right">Avg Win</th>
              <th className="text-right">Avg Loss</th>
              <th>Trend</th>
            </tr>
          </thead>
          <tbody>
            {STRATEGIES.map((s) => (
              <tr key={s.id} className="cursor-pointer">
                <td>
                  <div className="flex items-center gap-2">
                    <Pill variant={s.status === 'LIVE' ? 'bull' : 'info'} dot className="text-2xs">{s.status}</Pill>
                    <span className="font-semibold">{s.name}</span>
                  </div>
                </td>
                <td className={cn('text-right font-mono font-semibold', pnlColor(s.pnl.total))}>
                  {s.pnl.total >= 0 ? '+' : ''}₹{formatIN(Math.abs(s.pnl.total))}
                </td>
                <td className="text-right font-mono num">{s.winRate.toFixed(1)}%</td>
                <td className="text-right font-mono num">{s.sharpe.toFixed(2)}</td>
                <td className="text-right font-mono num">{s.trades.total}</td>
                <td className="text-right font-mono num text-bullish">₹4,520</td>
                <td className="text-right font-mono num text-bearish">-₹2,450</td>
                <td>
                  <Sparkline data={Array.from({ length: 20 }).map(() => 50 + Math.random() * 50)} width={60} height={20} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  )
}
