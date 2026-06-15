import { Panel } from '@/components/ui/Panel'
import { Pill } from '@/components/ui/Pill'
import { Sparkline } from '@/components/ui/Sparkline'
import { Distribution, Gauge } from '@/components/ui/Progress'
import { LineChart } from '@/components/ui/LineChart'
import { PORTFOLIO, HOLDINGS, POSITIONS, SECTOR_PERFORMANCE, RISK_METRICS } from '@/services/mockData'
import { cn, formatIN, formatNumber, pnlColor, formatPercent } from '@/lib/utils'
import { TrendingUp, TrendingDown, Briefcase, Wallet, CreditCard, PieChart, Activity, BarChart3, ArrowUpRight, ArrowDownRight, Building2, Target, Shield, AlertCircle } from 'lucide-react'

export function Portfolio() {
  return (
    <div className="h-full p-2 space-y-2 overflow-y-auto">
      {/* Hero KPIs */}
      <div className="grid grid-cols-5 gap-2">
        {[
          { label: 'Total Value', value: `₹${formatIN(PORTFOLIO.totalValue)}`, sub: 'all accounts', icon: Briefcase, color: 'text-fg' },
          { label: 'Invested', value: `₹${formatIN(PORTFOLIO.investedValue)}`, sub: '79.1% of portfolio', icon: PieChart, color: 'text-fg' },
          { label: 'Available Cash', value: `₹${formatIN(PORTFOLIO.availableCash)}`, sub: `${((PORTFOLIO.availableCash / PORTFOLIO.totalValue) * 100).toFixed(1)}% idle`, icon: Wallet, color: 'text-fg' },
          { label: 'Margin Used', value: `₹${formatIN(PORTFOLIO.marginUsed)}`, sub: `${((PORTFOLIO.marginUsed / PORTFOLIO.totalValue) * 100).toFixed(1)}% deployed`, icon: CreditCard, color: 'text-warn' },
          { label: 'Total P&L', value: `+₹${formatIN(PORTFOLIO.totalPnl)}`, sub: `+${PORTFOLIO.totalPnlPct.toFixed(2)}% all-time`, icon: TrendingUp, color: 'text-bullish' },
        ].map((k, i) => {
          const Icon = k.icon
          return (
            <div key={i} className="p-3 bg-bg-1 border border-line rounded">
              <div className="flex items-center justify-between">
                <div className="text-2xs text-fg-dim uppercase tracking-wider font-medium">{k.label}</div>
                <Icon className="h-3.5 w-3.5 text-fg-dim" />
              </div>
              <div className={cn('text-2xl font-semibold font-mono num mt-1', k.color)}>{k.value}</div>
              <div className="text-2xs text-fg-muted mt-1">{k.sub}</div>
            </div>
          )
        })}
      </div>

      {/* Equity + Allocation */}
      <div className="grid grid-cols-12 gap-2">
        <Panel className="col-span-8" title="Portfolio Value · 1Y" noPadding>
          <div className="p-3">
            <LineChart
              data={Array.from({ length: 90 }).map((_, i) => ({ x: i, y: 1_200_000 + i * 2000 + Math.sin(i / 5) * 30000 }))}
              height={180}
              yLabel={(v) => `₹${(v / 100000).toFixed(0)}L`}
            />
            <div className="grid grid-cols-5 gap-2 mt-3 pt-3 border-t border-line text-2xs">
              <div><div className="text-fg-dim">Day</div><div className="font-mono num text-bullish">+₹14.2K</div></div>
              <div><div className="text-fg-dim">Week</div><div className="font-mono num text-bullish">+₹32.4K</div></div>
              <div><div className="text-fg-dim">Month</div><div className="font-mono num text-bullish">+₹78.3K</div></div>
              <div><div className="text-fg-dim">3M</div><div className="font-mono num text-bullish">+₹142.1K</div></div>
              <div><div className="text-fg-dim">YTD</div><div className="font-mono num text-bullish">+₹283.4K</div></div>
            </div>
          </div>
        </Panel>

        <Panel className="col-span-4" title="Sector Allocation" noPadding>
          <div className="p-3">
            <Distribution
              data={SECTOR_PERFORMANCE.map((s) => ({ label: s.sector, value: s.volume }))}
              size={140}
              thickness={20}
              centerLabel="ALLOCATION"
              centerValue="100%"
            />
            <div className="mt-3 space-y-1 text-2xs">
              {SECTOR_PERFORMANCE.slice(0, 5).map((s, i) => (
                <div key={s.sector} className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded" style={{ background: ['#3b82f6', '#10b981', '#f59e0b', '#a855f7', '#ef4444'][i] }} />
                  <span className="flex-1">{s.sector}</span>
                  <span className="font-mono num text-fg-muted">{((s.volume / SECTOR_PERFORMANCE.reduce((a, b) => a + b.volume, 0)) * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          </div>
        </Panel>
      </div>

      {/* Holdings */}
      <Panel
        title="Long-term Holdings"
        subtitle={`${HOLDINGS.length} stocks · Delivery`}
        actions={<Pill variant="info" className="text-2xs">Demat</Pill>}
        noPadding
      >
        <table className="data-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th className="text-right">Qty</th>
              <th className="text-right">Avg Price</th>
              <th className="text-right">LTP</th>
              <th className="text-right">Value</th>
              <th className="text-right">P&L</th>
              <th className="text-right">P&L %</th>
              <th>Sparkline</th>
            </tr>
          </thead>
          <tbody>
            {HOLDINGS.map((h) => (
              <tr key={h.symbol} className="cursor-pointer">
                <td>
                  <div className="flex items-center gap-1.5">
                    <Building2 className="h-3 w-3 text-fg-dim" />
                    <span className="font-semibold">{h.symbol}</span>
                    <Pill variant="neutral" className="text-2xs">CNC</Pill>
                  </div>
                </td>
                <td className="text-right font-mono">{h.quantity}</td>
                <td className="text-right font-mono">{formatIN(h.avgPrice)}</td>
                <td className="text-right font-mono font-semibold">{formatIN(h.ltp)}</td>
                <td className="text-right font-mono">₹{formatIN(h.ltp * h.quantity)}</td>
                <td className={cn('text-right font-mono font-semibold', pnlColor(h.pnl))}>
                  {h.pnl >= 0 ? '+' : ''}₹{formatIN(Math.abs(h.pnl))}
                </td>
                <td className={cn('text-right font-mono', pnlColor(h.pnlPct))}>
                  {formatPercent(h.pnlPct)}
                </td>
                <td>
                  <Sparkline data={Array.from({ length: 20 }).map((_, i) => h.ltp * (1 + Math.sin(i / 3) * 0.02))} width={60} height={20} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      {/* Intraday positions */}
      <Panel
        title="Intraday Positions"
        subtitle={`${POSITIONS.length} active · ${PORTFOLIO.openOrdersCount} open orders`}
        actions={<Pill variant="warn" className="text-2xs">Auto-square 15:15</Pill>}
        noPadding
      >
        <table className="data-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th className="text-right">Qty</th>
              <th className="text-right">Avg</th>
              <th className="text-right">LTP</th>
              <th className="text-right">Day Chg</th>
              <th className="text-right">P&L</th>
              <th className="text-right">P&L %</th>
              <th>Product</th>
            </tr>
          </thead>
          <tbody>
            {POSITIONS.map((p) => (
              <tr key={p.symbol}>
                <td className="font-semibold">{p.symbol}</td>
                <td className="text-right font-mono">{p.quantity}</td>
                <td className="text-right font-mono">{formatIN(p.avgPrice)}</td>
                <td className="text-right font-mono font-semibold">{formatIN(p.ltp)}</td>
                <td className={cn('text-right font-mono', pnlColor(p.dayChangePct))}>
                  {formatPercent(p.dayChangePct)}
                </td>
                <td className={cn('text-right font-mono font-semibold', pnlColor(p.pnl))}>
                  {p.pnl >= 0 ? '+' : ''}₹{formatIN(Math.abs(p.pnl))}
                </td>
                <td className={cn('text-right font-mono', pnlColor(p.pnlPct))}>{formatPercent(p.pnlPct)}</td>
                <td><Pill variant="neutral" className="text-2xs">{p.product}</Pill></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  )
}
