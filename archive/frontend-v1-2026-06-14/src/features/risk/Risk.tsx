import { Panel } from '@/components/ui/Panel'
import { Pill } from '@/components/ui/Pill'
import { Distribution, Gauge } from '@/components/ui/Progress'
import { RISK_METRICS, POSITIONS, PORTFOLIO } from '@/services/mockData'
import { cn, formatIN, formatPercent, pnlColor } from '@/lib/utils'
import { Shield, AlertTriangle, TrendingUp, TrendingDown, Activity, Target, BarChart3, Crosshair, AlertCircle, CheckCircle2, Zap, Eye } from 'lucide-react'

export function Risk() {
  return (
    <div className="h-full p-2 space-y-2 overflow-y-auto">
      {/* Risk KPIs */}
      <div className="grid grid-cols-6 gap-2">
        {[
          { label: 'Portfolio VaR (1D)', value: `${RISK_METRICS.portfolioVar.toFixed(2)}%`, sub: '₹23,043 at risk', color: 'text-warn', icon: AlertTriangle },
          { label: 'Expected Shortfall', value: `${RISK_METRICS.expectedShortfall.toFixed(2)}%`, sub: 'Tail risk (95%)', color: 'text-bearish', icon: TrendingDown },
          { label: 'Sharpe Ratio', value: RISK_METRICS.sharpe.toFixed(2), sub: 'Risk-adj return', color: 'text-bullish', icon: Activity },
          { label: 'Sortino Ratio', value: RISK_METRICS.sortino.toFixed(2), sub: 'Downside-adj', color: 'text-bullish', icon: Target },
          { label: 'Beta', value: RISK_METRICS.beta.toFixed(2), sub: 'vs NIFTY 50', color: 'text-fg', icon: BarChart3 },
          { label: 'Alpha', value: `+${RISK_METRICS.alpha.toFixed(1)}%`, sub: 'Excess return', color: 'text-bullish', icon: TrendingUp },
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

      <div className="grid grid-cols-12 gap-2">
        {/* Exposure */}
        <Panel className="col-span-4" title="Exposure" actions={<Pill variant="info" className="text-2xs">Net: {RISK_METRICS.exposure.net.toFixed(1)}%</Pill>}>
          <div className="space-y-3">
            <Distribution
              data={[
                { label: 'Long', value: RISK_METRICS.exposure.long },
                { label: 'Short', value: RISK_METRICS.exposure.short },
                { label: 'Cash', value: 100 - RISK_METRICS.exposure.long - RISK_METRICS.exposure.short },
              ]}
              size={140}
              thickness={18}
              centerValue={`${RISK_METRICS.exposure.gross.toFixed(0)}%`}
              centerLabel="GROSS EXPOSURE"
            />
            <div className="space-y-1.5 text-2xs">
              <div className="flex justify-between">
                <span className="text-fg-dim">Long</span>
                <span className="font-mono num text-bullish">{RISK_METRICS.exposure.long.toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-fg-dim">Short</span>
                <span className="font-mono num text-bearish">{RISK_METRICS.exposure.short.toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-fg-dim">Net</span>
                <span className="font-mono num">{RISK_METRICS.exposure.net.toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-fg-dim">Gross</span>
                <span className="font-mono num">{RISK_METRICS.exposure.gross.toFixed(1)}%</span>
              </div>
            </div>
          </div>
        </Panel>

        {/* Concentration */}
        <Panel className="col-span-4" title="Concentration Risk">
          <div className="space-y-2.5 text-2xs">
            {[
              { label: 'Top Position', value: RISK_METRICS.concentration.topPosition, max: 30, label_: 'TCS' },
              { label: 'Top 5', value: RISK_METRICS.concentration.top5, max: 80, label_: 'Combined' },
              { label: 'Top 10', value: RISK_METRICS.concentration.top10, max: 100, label_: 'Combined' },
              { label: 'Max Sector', value: RISK_METRICS.concentration.sectorMax, max: 40, label_: 'IT' },
            ].map((c, i) => (
              <div key={i}>
                <div className="flex justify-between mb-1">
                  <span className="text-fg-muted">{c.label} <span className="text-fg-dim">({c.label_})</span></span>
                  <span className="font-mono num">{c.value.toFixed(1)}%</span>
                </div>
                <div className="h-2 bg-bg-2 rounded">
                  <div
                    className={cn('h-full rounded', c.value / c.max > 0.8 ? 'bg-bearish' : c.value / c.max > 0.5 ? 'bg-warning' : 'bg-bullish')}
                    style={{ width: `${(c.value / c.max) * 100}%` }}
                  />
                </div>
              </div>
            ))}
            <div className="pt-2 border-t border-line">
              <div className="flex justify-between"><span className="text-fg-dim">Herfindahl Index</span><span className="font-mono num">0.085</span></div>
              <div className="flex justify-between mt-0.5"><span className="text-fg-dim">Effective # positions</span><span className="font-mono num">11.7</span></div>
            </div>
          </div>
        </Panel>

        {/* Margin */}
        <Panel className="col-span-4" title="Margin Utilization">
          <div className="space-y-3">
            <Gauge value={RISK_METRICS.margin.utilization} size={120} label="UTILIZATION" thickness={10} />
            <div className="space-y-1.5 text-2xs">
              <div className="flex justify-between">
                <span className="text-fg-dim">Used</span>
                <span className="font-mono num text-warn">₹{formatIN(RISK_METRICS.margin.used)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-fg-dim">Available</span>
                <span className="font-mono num text-bullish">₹{formatIN(RISK_METRICS.margin.available)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-fg-dim">Total</span>
                <span className="font-mono num">₹{formatIN(RISK_METRICS.margin.used + RISK_METRICS.margin.available)}</span>
              </div>
              <div className="pt-2 border-t border-line flex justify-between">
                <span className="text-fg-dim">Buying Power</span>
                <span className="font-mono num text-bullish">₹{formatIN(PORTFOLIO.buyingPower)}</span>
              </div>
            </div>
          </div>
        </Panel>
      </div>

      {/* Risk metrics */}
      <div className="grid grid-cols-12 gap-2">
        <Panel className="col-span-6" title="Drawdown Analysis" noPadding>
          <table className="data-table">
            <thead>
              <tr><th>Period</th><th className="text-right">Max DD</th><th className="text-right">Current DD</th><th className="text-right">Recovery Days</th></tr>
            </thead>
            <tbody>
              {[
                ['Today', '-0.45%', '-0.21%', '-'],
                ['1 Week', '-2.85%', '-0.21%', '-'],
                ['1 Month', '-4.20%', '-0.21%', '12d'],
                ['3 Months', '-6.85%', '-0.21%', '28d'],
                ['6 Months', '-8.35%', '-0.21%', '45d'],
                ['1 Year', '-8.35%', '-0.21%', '182d'],
                ['All-Time', '-8.35%', '-0.21%', '182d'],
              ].map(([p, mx, cur, rec]) => (
                <tr key={p}>
                  <td className="text-fg-muted">{p}</td>
                  <td className="text-right font-mono text-bearish">{mx}</td>
                  <td className="text-right font-mono text-bearish">{cur}</td>
                  <td className="text-right font-mono text-fg-muted">{rec}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel className="col-span-6" title="Risk Violations & Alerts" actions={<Pill variant="warn" dot className="text-2xs">2 Active</Pill>}>
          <div className="space-y-2">
            {[
              { level: 'HIGH', type: 'Daily Loss Limit', message: 'Daily loss approaching -2% limit (currently -1.85%)', time: '5m ago', icon: AlertTriangle },
              { level: 'MED', type: 'Position Concentration', message: 'TCS position exceeds 18% of portfolio', time: '15m ago', icon: AlertCircle },
              { level: 'INFO', type: 'Margin Check', message: 'Available margin is healthy (>₹8L)', time: '1h ago', icon: CheckCircle2, status: 'OK' },
              { level: 'INFO', type: 'Risk Score', message: 'Portfolio risk within acceptable range', time: '2h ago', icon: CheckCircle2, status: 'OK' },
            ].map((a, i) => {
              const Icon = a.icon
              return (
                <div key={i} className={cn('p-2.5 rounded border flex items-start gap-2',
                  a.level === 'HIGH' ? 'border-bearish/40 bg-bearish/10' :
                  a.level === 'MED' ? 'border-warning/40 bg-warning/10' :
                  'border-line bg-bg-2',
                )}>
                  <Icon className={cn('h-4 w-4 mt-0.5',
                    a.level === 'HIGH' ? 'text-bearish' :
                    a.level === 'MED' ? 'text-warning' :
                    'text-bullish',
                  )} />
                  <div className="flex-1">
                    <div className="flex items-center gap-1.5">
                      <Pill variant={a.level === 'HIGH' ? 'bear' : a.level === 'MED' ? 'warn' : 'bull'} className="text-2xs">
                        {a.level}
                      </Pill>
                      <span className="text-xs font-semibold">{a.type}</span>
                      <span className="ml-auto text-2xs text-fg-dim font-mono">{a.time}</span>
                    </div>
                    <div className="text-2xs text-fg-muted mt-1">{a.message}</div>
                  </div>
                </div>
              )
            })}
          </div>
        </Panel>
      </div>

      {/* Stress test */}
      <Panel title="Stress Test Scenarios" noPadding>
        <table className="data-table">
          <thead>
            <tr>
              <th>Scenario</th>
              <th className="text-right">Market Shock</th>
              <th className="text-right">Portfolio Impact</th>
              <th className="text-right">₹ Loss</th>
              <th className="text-right">Recovery (est.)</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['Market Crash -10%', '-10%', '-8.5%', '₹1,05,872', '45 days', 'survive'],
              ['Flash Crash -5%', '-5%', '-4.2%', '₹52,318', '18 days', 'survive'],
              ['Gap Down Open -3%', '-3%', '-2.8%', '₹34,879', '7 days', 'survive'],
              ['Vol Spike (VIX +50%)', '-', '-1.8%', '₹22,422', '12 days', 'survive'],
              ['Sector Crash (IT -15%)', '-', '-3.2%', '₹39,861', '14 days', 'survive'],
              ['Black Swan -20%', '-20%', '-18.5%', '₹2,30,452', '120 days', 'critical'],
            ].map((row) => (
              <tr key={row[0]} className="cursor-pointer">
                <td className="font-medium">{row[0]}</td>
                <td className="text-right font-mono text-bearish">{row[1]}</td>
                <td className="text-right font-mono text-bearish">{row[2]}</td>
                <td className="text-right font-mono text-bearish">{row[3]}</td>
                <td className="text-right font-mono text-fg-muted">{row[4]}</td>
                <td>
                  <Pill variant={row[5] === 'survive' ? 'bull' : 'bear'} className="text-2xs">
                    {row[5] === 'survive' ? '✓ Survives' : '⚠ Critical'}
                  </Pill>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  )
}
