import { Panel } from '@/components/ui/Panel'
import { Pill } from '@/components/ui/Pill'
import { Sparkline } from '@/components/ui/Sparkline'
import { Distribution, Gauge } from '@/components/ui/Progress'
import { LineChart } from '@/components/ui/LineChart'
import { MARKET_BREADTH, SECTOR_PERFORMANCE, generateOptionChain, INDICES, INDICATORS, PORTFOLIO } from '@/services/mockData'
import { cn, formatIN, formatNumber, pnlColor, formatPercent } from '@/lib/utils'
import { TrendingUp, TrendingDown, Activity, BarChart3, ArrowUpRight, ArrowDownRight, Eye, Layers, Zap, Target, Waves, Hexagon, LineChart as LineIcon, BarChart2 } from 'lucide-react'
import { useMemo, useState } from 'react'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'oi', label: 'OI Analytics' },
  { id: 'volume', label: 'Volume' },
  { id: 'volatility', label: 'Volatility' },
  { id: 'relative', label: 'Relative Strength' },
  { id: 'breadth', label: 'Market Breadth' },
  { id: 'sector', label: 'Sector Rotation' },
] as const

export function Analytics() {
  const [tab, setTab] = useState<typeof TABS[number]['id']>('overview')
  const optionChain = useMemo(() => generateOptionChain('NIFTY', 24_900), [])

  return (
    <div className="h-full flex flex-col p-2 gap-2 min-h-0">
      <Panel
        title="Market Analytics"
        subtitle="Multi-dimensional market intelligence"
        noPadding
        actions={
          <div className="flex items-center gap-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={cn(
                  'h-7 px-2.5 text-2xs font-medium rounded uppercase tracking-wider',
                  tab === t.id ? 'bg-bg-3 text-fg' : 'text-fg-muted hover:bg-bg-2',
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
        }
      >
        {tab === 'overview' && <Overview />}
        {tab === 'oi' && <OIAnalytics chain={optionChain} />}
        {tab === 'volume' && <VolumeAnalytics />}
        {tab === 'volatility' && <VolatilityAnalytics />}
        {tab === 'relative' && <RelativeStrength />}
        {tab === 'breadth' && <BreadthAnalytics />}
        {tab === 'sector' && <SectorRotation />}
      </Panel>
    </div>
  )
}

function Overview() {
  const indices = INDICES
  return (
    <div className="p-3 space-y-3">
      {/* Index strip */}
      <div className="grid grid-cols-6 gap-2">
        {indices.map((idx) => (
          <div key={idx.symbol} className="p-2 bg-bg-2 rounded border border-line">
            <div className="text-2xs text-fg-dim uppercase tracking-wider font-medium">{idx.symbol}</div>
            <div className={cn('text-lg font-semibold font-mono num', pnlColor(idx.change))}>
              {formatIN(idx.ltp, idx.symbol.includes('VIX') ? 2 : 2)}
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <Pill variant={idx.changePct >= 0 ? 'bull' : 'bear'} className="text-2xs">
                {idx.changePct >= 0 ? '+' : ''}{idx.changePct.toFixed(2)}%
              </Pill>
              <span className="text-2xs text-fg-muted font-mono num">
                {idx.change >= 0 ? '+' : ''}{idx.change.toFixed(2)}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Indicators grid */}
      <div className="grid grid-cols-12 gap-3">
        <Panel className="col-span-3" title="Market Breadth" actions={<Pill variant="bull" className="text-2xs">Healthy</Pill>}>
          <div className="flex items-center gap-3">
            <Gauge value={MARKET_BREADTH.advanceDeclineRatio * 33} size={100} thickness={8} label="A/D Ratio" />
            <div className="flex-1 space-y-1.5 text-2xs">
              <div className="flex justify-between">
                <span className="text-fg-dim">Advances</span>
                <span className="font-mono num text-bullish">{MARKET_BREADTH.advances}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-fg-dim">Declines</span>
                <span className="font-mono num text-bearish">{MARKET_BREADTH.declines}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-fg-dim">New Highs</span>
                <span className="font-mono num text-bullish">{MARKET_BREADTH.newHighs}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-fg-dim">New Lows</span>
                <span className="font-mono num text-bearish">{MARKET_BREADTH.newLows}</span>
              </div>
              <div className="pt-1.5 border-t border-line flex justify-between">
                <span className="text-fg-dim">Above 50 DMA</span>
                <span className="font-mono num">{((MARKET_BREADTH.above50DMA / MARKET_BREADTH.total) * 100).toFixed(0)}%</span>
              </div>
            </div>
          </div>
        </Panel>

        <Panel className="col-span-3" title="PCR & OI" actions={<Pill variant="info" className="text-2xs">NIFTY</Pill>}>
          <div className="space-y-2.5">
            <div>
              <div className="flex justify-between text-2xs mb-1">
                <span className="text-fg-dim">Put-Call Ratio</span>
                <span className="font-mono num text-bullish">1.18</span>
              </div>
              <div className="h-1.5 bg-bg-2 rounded">
                <div className="h-full bg-bullish" style={{ width: '59%' }} />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-2xs mb-1">
                <span className="text-fg-dim">Total Call OI</span>
                <span className="font-mono num text-bearish">12.4M</span>
              </div>
              <div className="h-1.5 bg-bg-2 rounded">
                <div className="h-full bg-bearish" style={{ width: '45%' }} />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-2xs mb-1">
                <span className="text-fg-dim">Total Put OI</span>
                <span className="font-mono num text-bullish">14.6M</span>
              </div>
              <div className="h-1.5 bg-bg-2 rounded">
                <div className="h-full bg-bullish" style={{ width: '55%' }} />
              </div>
            </div>
            <div className="pt-2 border-t border-line">
              <div className="flex justify-between text-2xs">
                <span className="text-fg-dim">Max Pain</span>
                <span className="font-mono num">24,800</span>
              </div>
              <div className="flex justify-between text-2xs mt-0.5">
                <span className="text-fg-dim">India VIX</span>
                <span className="font-mono num text-bullish">14.85 (-2.75%)</span>
              </div>
            </div>
          </div>
        </Panel>

        <Panel className="col-span-3" title="FII / DII Flow" actions={<Pill variant="warn" className="text-2xs">Intraday</Pill>}>
          <div className="space-y-2.5">
            <div className="flex items-center justify-between p-2 bg-bg-2 rounded">
              <div className="flex items-center gap-2">
                <div className="h-7 w-7 rounded-full bg-bullish/15 flex items-center justify-center">
                  <TrendingUp className="h-3.5 w-3.5 text-bullish" />
                </div>
                <div>
                  <div className="text-xs font-medium">FII Net</div>
                  <div className="text-2xs text-fg-dim">Cash Market</div>
                </div>
              </div>
              <div className="text-right">
                <div className="font-mono num text-bullish">+₹1,245 Cr</div>
                <div className="text-2xs text-bullish">Net Long</div>
              </div>
            </div>
            <div className="flex items-center justify-between p-2 bg-bg-2 rounded">
              <div className="flex items-center gap-2">
                <div className="h-7 w-7 rounded-full bg-bearish/15 flex items-center justify-center">
                  <TrendingDown className="h-3.5 w-3.5 text-bearish" />
                </div>
                <div>
                  <div className="text-xs font-medium">DII Net</div>
                  <div className="text-2xs text-fg-dim">Cash Market</div>
                </div>
              </div>
              <div className="text-right">
                <div className="font-mono num text-bearish">-₹856 Cr</div>
                <div className="text-2xs text-bearish">Net Sell</div>
              </div>
            </div>
            <div className="flex items-center justify-between p-2 bg-bg-2 rounded">
              <div className="flex items-center gap-2">
                <div className="h-7 w-7 rounded-full bg-brand/15 flex items-center justify-center">
                  <Activity className="h-3.5 w-3.5 text-brand" />
                </div>
                <div>
                  <div className="text-xs font-medium">FII Index Fut</div>
                  <div className="text-2xs text-fg-dim">Long Build-up</div>
                </div>
              </div>
              <div className="text-right">
                <div className="font-mono num text-bullish">+₹2,415 Cr</div>
                <div className="text-2xs text-bullish">OI ↑ 8.2%</div>
              </div>
            </div>
          </div>
        </Panel>

        <Panel className="col-span-3" title="Technical Snapshot" actions={<Pill variant="bull" className="text-2xs">8 Bullish</Pill>}>
          <div className="space-y-1.5">
            {INDICATORS.map((ind) => (
              <div key={ind.name} className="flex items-center justify-between text-xs">
                <span className="text-fg-muted">{ind.name}</span>
                <div className="flex items-center gap-2">
                  <span className={cn('font-mono num', ind.signal === 'BULLISH' ? 'text-bullish' : ind.signal === 'BEARISH' ? 'text-bearish' : 'text-fg-muted')}>
                    {ind.value.toFixed(1)}
                  </span>
                  <Pill variant={ind.signal === 'BULLISH' ? 'bull' : ind.signal === 'BEARISH' ? 'bear' : 'neutral'} className="text-2xs w-12 justify-center">
                    {ind.signal}
                  </Pill>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      {/* RS Rotation heatmap */}
      <Panel
        title="Relative Strength Rotation"
        subtitle="Sector leadership · Last 20 days"
        actions={<Pill variant="info" className="text-2xs">Auto-refresh 5m</Pill>}
        noPadding
      >
        <div className="p-3">
          <div className="grid grid-cols-4 gap-2">
            {SECTOR_PERFORMANCE.map((s) => (
              <div
                key={s.sector}
                className="p-3 rounded border border-line"
                style={{
                  background: s.changePct > 0
                    ? `linear-gradient(135deg, rgba(22,163,74,${Math.min(0.4, s.changePct / 4)}) 0%, transparent 100%)`
                    : `linear-gradient(135deg, rgba(220,38,38,${Math.min(0.4, Math.abs(s.changePct) / 4)}) 0%, transparent 100%)`,
                }}
              >
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold">{s.sector}</div>
                  <Pill variant={s.rs > 70 ? 'bull' : s.rs < 50 ? 'bear' : 'neutral'} className="text-2xs">
                    RS {s.rs}
                  </Pill>
                </div>
                <div className={cn('text-xl font-semibold font-mono num mt-1', pnlColor(s.changePct))}>
                  {formatPercent(s.changePct)}
                </div>
                <div className="text-2xs text-fg-muted mt-1 flex items-center justify-between">
                  <span>{s.advances}A / {s.declines}D</span>
                  <Sparkline data={[40, 45, 42, 48, 52, 50, 55, 60, 58, 62].map((v) => v * (1 + s.changePct / 10))} width={50} height={14} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </Panel>
    </div>
  )
}

function OIAnalytics({ chain }: { chain: ReturnType<typeof generateOptionChain> }) {
  return (
    <div className="p-3 space-y-3">
      <div className="grid grid-cols-4 gap-3">
        <div className="p-3 bg-bg-2 rounded border border-line">
          <div className="text-2xs text-fg-dim uppercase tracking-wider">PCR (OI)</div>
          <div className="text-2xl font-semibold font-mono num mt-1 text-bullish">{chain.pcr}</div>
          <div className="text-2xs text-fg-muted mt-1">Bullish bias</div>
        </div>
        <div className="p-3 bg-bg-2 rounded border border-line">
          <div className="text-2xs text-fg-dim uppercase tracking-wider">Max Pain</div>
          <div className="text-2xl font-semibold font-mono num mt-1">{formatIN(chain.maxPain, 0)}</div>
          <div className="text-2xs text-fg-muted mt-1">Expiry magnet</div>
        </div>
        <div className="p-3 bg-bg-2 rounded border border-line">
          <div className="text-2xs text-fg-dim uppercase tracking-wider">ATM IV</div>
          <div className="text-2xl font-semibold font-mono num mt-1 text-warn">{chain.iv}%</div>
          <div className="text-2xs text-fg-muted mt-1">+{chain.ivChange}% vs prev</div>
        </div>
        <div className="p-3 bg-bg-2 rounded border border-line">
          <div className="text-2xs text-fg-dim uppercase tracking-wider">Total OI</div>
          <div className="text-2xl font-semibold font-mono num mt-1">27.0M</div>
          <div className="text-2xs text-fg-muted mt-1">Call {chain.totalCallOI}M / Put {chain.totalPutOI}M</div>
        </div>
      </div>

      <Panel title="OI Heatmap · Strike-wise" actions={<Pill variant="warn" className="text-2xs">Expiry: 26-Jun</Pill>} noPadding>
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th colSpan={5} className="text-center bg-bearish/10 text-bearish border-r-2 border-line">CALL</th>
                <th className="text-center bg-bg-3 font-bold">STRIKE</th>
                <th colSpan={5} className="text-center bg-bullish/10 text-bullish border-l-2 border-line">PUT</th>
              </tr>
              <tr>
                <th className="text-right text-bearish">OI Chg</th>
                <th className="text-right text-bearish">OI</th>
                <th className="text-right text-bearish">IV</th>
                <th className="text-right text-bearish">LTP</th>
                <th className="text-right text-bearish">Δ</th>
                <th className="text-center">Price</th>
                <th className="text-left text-bullish">Δ</th>
                <th className="text-left text-bullish">LTP</th>
                <th className="text-left text-bullish">IV</th>
                <th className="text-left text-bullish">OI</th>
                <th className="text-left text-bullish">OI Chg</th>
              </tr>
            </thead>
            <tbody>
              {chain.strikes.slice(8, 32).map((s) => (
                <tr key={s.strike}>
                  <td className={cn('text-right', s.callOIChange > 0 ? 'text-bearish bg-bearish/10' : 'text-fg-dim')}>
                    {s.callOIChange > 0 ? '+' : ''}{formatNumber(s.callOIChange / 1000, 0)}K
                  </td>
                  <td className="text-right font-mono">{formatNumber(s.callOI / 1000, 0)}K</td>
                  <td className="text-right font-mono text-fg-muted">{s.callIV.toFixed(1)}</td>
                  <td className="text-right font-mono text-bearish">{s.callLTP.toFixed(2)}</td>
                  <td className="text-right font-mono text-fg-muted">{s.callDelta.toFixed(2)}</td>
                  <td className="text-center font-mono font-bold bg-bg-2">{s.strike}</td>
                  <td className="text-left font-mono text-fg-muted">{s.putDelta.toFixed(2)}</td>
                  <td className="text-left font-mono text-bullish">{s.putLTP.toFixed(2)}</td>
                  <td className="text-left font-mono text-fg-muted">{s.putIV.toFixed(1)}</td>
                  <td className="text-left font-mono">{formatNumber(s.putOI / 1000, 0)}K</td>
                  <td className={cn('text-left', s.putOIChange > 0 ? 'text-bullish bg-bullish/10' : 'text-fg-dim')}>
                    {s.putOIChange > 0 ? '+' : ''}{formatNumber(s.putOIChange / 1000, 0)}K
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  )
}

function VolumeAnalytics() {
  return (
    <div className="p-3 grid grid-cols-3 gap-3">
      <Panel className="col-span-2" title="Volume Heatmap (NIFTY 50)" noPadding>
        <div className="p-3 grid grid-cols-10 gap-1">
          {Array.from({ length: 50 }).map((_, i) => {
            const v = Math.random() * 100
            return (
              <div
                key={i}
                className="aspect-square rounded-sm"
                style={{
                  background: `rgba(59, 130, 246, ${v / 100})`,
                }}
                title={`Stock ${i + 1}: ${v.toFixed(0)}%`}
              />
            )
          })}
        </div>
      </Panel>
      <Panel title="Top Volume Movers">
        <div className="space-y-1.5">
          {['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'SBIN', 'ICICIBANK'].map((s, i) => {
            const v = Math.random() * 10
            return (
              <div key={s} className="flex items-center gap-2 text-xs">
                <span className="font-mono text-fg-dim w-4">{i + 1}</span>
                <span className="font-semibold flex-1">{s}</span>
                <span className="font-mono num">{v.toFixed(2)}M</span>
                <Pill variant={Math.random() > 0.5 ? 'bull' : 'bear'} className="text-2xs">
                  {Math.random() > 0.5 ? '+' : '-'}{(Math.random() * 8).toFixed(1)}%
                </Pill>
              </div>
            )
          })}
        </div>
      </Panel>
    </div>
  )
}

function VolatilityAnalytics() {
  return (
    <div className="p-3 grid grid-cols-2 gap-3">
      <Panel title="India VIX" actions={<Pill variant="bull" className="text-2xs">-2.75%</Pill>}>
        <div className="text-3xl font-semibold font-mono num">14.85</div>
        <LineChart
          data={Array.from({ length: 60 }).map((_, i) => ({ x: i, y: 15 + Math.sin(i / 3) * 1.5 + (Math.random() - 0.5) * 0.5 }))}
          height={120}
          yLabel={(v) => v.toFixed(1)}
        />
      </Panel>
      <Panel title="IV Term Structure">
        <div className="space-y-1.5">
          {['Weekly', 'Monthly', 'Quarterly', 'Half-Yearly'].map((t, i) => {
            const v = 14 + i * 1.2 + Math.random() * 0.5
            return (
              <div key={t} className="flex items-center gap-2">
                <span className="text-xs w-20">{t}</span>
                <div className="flex-1 h-3 bg-bg-2 rounded overflow-hidden">
                  <div className="h-full bg-brand" style={{ width: `${(v / 25) * 100}%` }} />
                </div>
                <span className="text-2xs font-mono num w-12 text-right">{v.toFixed(1)}%</span>
              </div>
            )
          })}
        </div>
      </Panel>
    </div>
  )
}

function RelativeStrength() {
  return (
    <div className="p-3">
      <Panel title="RS Ranking · NIFTY 500" noPadding>
        <div className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 200px)' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Symbol</th>
                <th>Sector</th>
                <th className="text-right">LTP</th>
                <th className="text-right">RS</th>
                <th className="text-right">1W</th>
                <th className="text-right">1M</th>
                <th className="text-right">3M</th>
                <th>Trend</th>
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 30 }).map((_, i) => {
                const rs = 100 - i * 3
                const sym = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'SBIN', 'ITC', 'LT', 'AXISBANK', 'BHARTIARTL'][i % 10]
                return (
                  <tr key={i}>
                    <td className="text-fg-dim font-mono">{i + 1}</td>
                    <td className="font-semibold">{sym}</td>
                    <td className="text-fg-muted text-2xs">{['IT', 'Bank', 'Auto', 'Pharma'][i % 4]}</td>
                    <td className="text-right font-mono">2,{100 + i * 10}.{i * 3}</td>
                    <td className="text-right">
                      <div className="flex items-center gap-1.5 justify-end">
                        <div className="w-12 h-1.5 bg-bg-2 rounded">
                          <div className={cn('h-full', rs > 70 ? 'bg-bullish' : rs > 40 ? 'bg-warning' : 'bg-bearish')} style={{ width: `${rs}%` }} />
                        </div>
                        <span className="font-mono num w-8">{rs}</span>
                      </div>
                    </td>
                    <td className={cn('text-right font-mono', pnlColor(Math.random() - 0.4))}>+{(Math.random() * 5).toFixed(1)}%</td>
                    <td className={cn('text-right font-mono', pnlColor(Math.random() - 0.3))}>{Math.random() > 0.5 ? '+' : '-'}{(Math.random() * 12).toFixed(1)}%</td>
                    <td className={cn('text-right font-mono', pnlColor(Math.random() - 0.3))}>{Math.random() > 0.5 ? '+' : '-'}{(Math.random() * 25).toFixed(1)}%</td>
                    <td>
                      <Sparkline data={Array.from({ length: 20 }).map(() => 50 + Math.random() * 50)} width={60} height={20} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  )
}

function BreadthAnalytics() {
  return (
    <div className="p-3 grid grid-cols-3 gap-3">
      <Panel title="Advances vs Declines">
        <div className="flex items-center gap-2 mb-3">
          <Distribution
            data={[
              { label: 'Advances', value: MARKET_BREADTH.advances },
              { label: 'Declines', value: MARKET_BREADTH.declines },
              { label: 'Unchanged', value: MARKET_BREADTH.unchanged },
            ]}
            size={140}
            thickness={18}
            centerValue={MARKET_BREADTH.advanceDeclineRatio.toFixed(2)}
            centerLabel="A/D RATIO"
          />
        </div>
        <div className="space-y-1.5 text-xs">
          <div className="flex justify-between"><span className="text-fg-dim">Advances</span><span className="font-mono num text-bullish">{MARKET_BREADTH.advances}</span></div>
          <div className="flex justify-between"><span className="text-fg-dim">Declines</span><span className="font-mono num text-bearish">{MARKET_BREADTH.declines}</span></div>
          <div className="flex justify-between"><span className="text-fg-dim">Unchanged</span><span className="font-mono num">{MARKET_BREADTH.unchanged}</span></div>
        </div>
      </Panel>
      <Panel title="52-Week Highs/Lows">
        <div className="space-y-3">
          <div>
            <div className="text-2xs text-fg-dim">New Highs</div>
            <div className="text-2xl font-semibold font-mono num text-bullish">{MARKET_BREADTH.newHighs}</div>
            <div className="h-1.5 bg-bg-2 rounded mt-1">
              <div className="h-full bg-bullish" style={{ width: '60%' }} />
            </div>
          </div>
          <div>
            <div className="text-2xs text-fg-dim">New Lows</div>
            <div className="text-2xl font-semibold font-mono num text-bearish">{MARKET_BREADTH.newLows}</div>
            <div className="h-1.5 bg-bg-2 rounded mt-1">
              <div className="h-full bg-bearish" style={{ width: '25%' }} />
            </div>
          </div>
        </div>
      </Panel>
      <Panel title="Moving Average Breadth">
        <div className="space-y-2.5">
          <div>
            <div className="flex justify-between text-2xs mb-1">
              <span className="text-fg-dim">Above 50 DMA</span>
              <span className="font-mono num">{((MARKET_BREADTH.above50DMA / MARKET_BREADTH.total) * 100).toFixed(0)}%</span>
            </div>
            <div className="h-2 bg-bg-2 rounded">
              <div className="h-full bg-bullish" style={{ width: `${(MARKET_BREADTH.above50DMA / MARKET_BREADTH.total) * 100}%` }} />
            </div>
          </div>
          <div>
            <div className="flex justify-between text-2xs mb-1">
              <span className="text-fg-dim">Above 200 DMA</span>
              <span className="font-mono num">{((MARKET_BREADTH.above200DMA / MARKET_BREADTH.total) * 100).toFixed(0)}%</span>
            </div>
            <div className="h-2 bg-bg-2 rounded">
              <div className="h-full bg-brand" style={{ width: `${(MARKET_BREADTH.above200DMA / MARKET_BREADTH.total) * 100}%` }} />
            </div>
          </div>
        </div>
      </Panel>
    </div>
  )
}

function SectorRotation() {
  return (
    <div className="p-3">
      <Panel title="Sector Heatmap" noPadding>
        <div className="p-3 grid grid-cols-4 gap-2">
          {SECTOR_PERFORMANCE.map((s) => (
            <div key={s.sector} className="p-4 rounded border border-line" style={{ background: `rgba(${s.changePct > 0 ? '22, 163, 74' : '220, 38, 38'}, ${Math.min(0.3, Math.abs(s.changePct) / 5)})` }}>
              <div className="font-semibold">{s.sector}</div>
              <div className={cn('text-2xl font-mono num font-semibold', pnlColor(s.changePct))}>{formatPercent(s.changePct)}</div>
              <div className="text-2xs text-fg-muted mt-2">RS {s.rs} · {s.advances}A / {s.declines}D</div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  )
}
