import { Panel } from '@/components/ui/Panel'
import { Pill } from '@/components/ui/Pill'
import { useMemo, useState } from 'react'
import { generateOptionChain } from '@/services/mockData'
import { cn, formatIN, formatNumber, pnlColor } from '@/lib/utils'
import { Activity, BarChart3, Calendar, ChevronDown, Filter, Search, Settings, Target, TrendingUp, TrendingDown, Zap, Eye, EyeOff, Calculator, Layers, BookOpen, LineChart as LineIcon, Flame, Snowflake } from 'lucide-react'

const UNDERLYINGS = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'SBIN']
const EXPIRIES = ['26-Jun-2025', '03-Jul-2025', '10-Jul-2025', '31-Jul-2025', '28-Aug-2025']

export function Options() {
  const [underlying, setUnderlying] = useState('NIFTY')
  const [expiry, setExpiry] = useState(EXPIRIES[0])
  const [activeTab, setActiveTab] = useState<'chain' | 'oi' | 'iv' | 'flow' | 'strategies' | 'calc'>('chain')

  const chain = useMemo(() => generateOptionChain(underlying, underlying === 'NIFTY' ? 24_900 : underlying === 'BANKNIFTY' ? 53_250 : 2_900), [underlying])

  // Find strikes sorted by distance from ATM
  const displayStrikes = chain.strikes

  return (
    <div className="h-full grid grid-cols-12 gap-2 p-2">
      {/* Top header: underlying + expiry */}
      <Panel className="col-span-12" noPadding>
        <div className="px-3 py-2 flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-2xs text-fg-dim uppercase tracking-wider">Underlying</span>
            <select
              value={underlying}
              onChange={(e) => setUnderlying(e.target.value)}
              className="h-7 bg-bg-0 border border-line rounded px-2 text-sm font-semibold"
            >
              {UNDERLYINGS.map((u) => <option key={u} value={u}>{u}</option>)}
            </select>
          </div>
          <div className="h-5 w-px bg-line" />
          <div className="flex items-center gap-2">
            <span className="text-2xs text-fg-dim uppercase tracking-wider">Expiry</span>
            <select
              value={expiry}
              onChange={(e) => setExpiry(e.target.value)}
              className="h-7 bg-bg-0 border border-line rounded px-2 text-sm"
            >
              {EXPIRIES.map((e) => <option key={e} value={e}>{e}</option>)}
            </select>
          </div>
          <div className="h-5 w-px bg-line" />
          <div className="flex items-center gap-3">
            <Pill variant="info" dot>SPOT {formatIN(chain.spot, 0)}</Pill>
            <Pill variant="neutral">ATM {chain.atm}</Pill>
            <Pill variant="bull">PCR {chain.pcr}</Pill>
            <Pill variant="warn">MAX PAIN {formatIN(chain.maxPain, 0)}</Pill>
            <Pill variant="brand">IV {chain.iv}%</Pill>
          </div>
          <div className="ml-auto flex items-center gap-1">
            {(['chain', 'oi', 'iv', 'flow', 'strategies', 'calc'] as const).map((t) => (
              <button
                key={t}
                onClick={() => setActiveTab(t)}
                className={cn(
                  'h-7 px-2.5 text-2xs font-medium rounded uppercase tracking-wider',
                  activeTab === t ? 'bg-bg-3 text-fg' : 'text-fg-muted hover:bg-bg-2',
                )}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      </Panel>

      {/* Main chain table */}
      <Panel
        className="col-span-9"
        title={`Option Chain · ${underlying} ${expiry}`}
        actions={
          <>
            <button className="btn btn-ghost text-2xs"><Filter className="h-3 w-3" /> Filter</button>
            <button className="btn btn-ghost text-2xs"><Settings className="h-3 w-3" /></button>
          </>
        }
        noPadding
      >
        {activeTab === 'chain' && (
          <div className="overflow-auto" style={{ maxHeight: 'calc(100vh - 220px)' }}>
            <table className="data-table text-2xs">
              <thead>
                <tr>
                  <th colSpan={7} className="text-center bg-bearish/10 text-bearish border-r-2 border-line">CALL</th>
                  <th className="text-center bg-bg-3 font-bold">STRIKE</th>
                  <th colSpan={7} className="text-center bg-bullish/10 text-bullish border-l-2 border-line">PUT</th>
                </tr>
                <tr className="text-2xs">
                  <th>OI Chg</th>
                  <th>OI</th>
                  <th>Vol</th>
                  <th>IV</th>
                  <th>LTP</th>
                  <th>Bid</th>
                  <th className="border-r-2 border-line">Ask</th>
                  <th className="text-center">Price</th>
                  <th className="border-l-2 border-line">Bid</th>
                  <th>Ask</th>
                  <th>LTP</th>
                  <th>IV</th>
                  <th>Vol</th>
                  <th>OI</th>
                  <th>OI Chg</th>
                </tr>
              </thead>
              <tbody>
                {displayStrikes.map((s) => (
                  <tr key={s.strike} className={cn(s.strike === chain.atm && 'bg-bg-3 font-semibold')}>
                    <td className={cn('text-right', s.callOIChange > 0 ? 'text-bearish bg-bearish/10' : 'text-fg-dim')}>
                      {s.callOIChange > 0 ? '+' : ''}{formatNumber(s.callOIChange / 1000, 0)}K
                    </td>
                    <td className="text-right font-mono">{formatNumber(s.callOI / 1000, 0)}K</td>
                    <td className="text-right font-mono text-fg-muted">{formatNumber(s.callVolume / 1000, 0)}K</td>
                    <td className="text-right font-mono text-fg-muted">{s.callIV.toFixed(1)}</td>
                    <td className="text-right font-mono text-bearish">{s.callLTP.toFixed(2)}</td>
                    <td className="text-right font-mono text-fg-muted">{s.callBid.toFixed(2)}</td>
                    <td className="text-right font-mono text-fg-muted border-r-2 border-line">{s.callAsk.toFixed(2)}</td>
                    <td className="text-center font-mono font-bold bg-bg-2">{s.strike}</td>
                    <td className="text-right font-mono text-fg-muted border-l-2 border-line">{s.putBid.toFixed(2)}</td>
                    <td className="text-right font-mono text-fg-muted">{s.putAsk.toFixed(2)}</td>
                    <td className="text-right font-mono text-bullish">{s.putLTP.toFixed(2)}</td>
                    <td className="text-right font-mono text-fg-muted">{s.putIV.toFixed(1)}</td>
                    <td className="text-right font-mono text-fg-muted">{formatNumber(s.putVolume / 1000, 0)}K</td>
                    <td className="text-right font-mono">{formatNumber(s.putOI / 1000, 0)}K</td>
                    <td className={cn('text-right', s.putOIChange > 0 ? 'text-bullish bg-bullish/10' : 'text-fg-dim')}>
                      {s.putOIChange > 0 ? '+' : ''}{formatNumber(s.putOIChange / 1000, 0)}K
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {activeTab === 'oi' && (
          <div className="p-3">
            <div className="text-center text-fg-muted text-sm py-8">OI build-up heatmap visualization</div>
            <div className="grid grid-cols-2 gap-3">
              <Panel title="Top Call OI Build">
                <div className="space-y-1">
                  {[...chain.strikes].sort((a, b) => b.callOIChange - a.callOIChange).slice(0, 8).map((s) => (
                    <div key={s.strike} className="flex items-center gap-2 text-xs">
                      <span className="font-mono w-12">{s.strike}</span>
                      <div className="flex-1 h-2 bg-bg-2 rounded">
                        <div className="h-full bg-bearish rounded" style={{ width: `${Math.min(100, s.callOIChange / 5000)}%` }} />
                      </div>
                      <span className="font-mono num text-bearish">+{formatNumber(s.callOIChange / 1000, 0)}K</span>
                    </div>
                  ))}
                </div>
              </Panel>
              <Panel title="Top Put OI Build">
                <div className="space-y-1">
                  {[...chain.strikes].sort((a, b) => b.putOIChange - a.putOIChange).slice(0, 8).map((s) => (
                    <div key={s.strike} className="flex items-center gap-2 text-xs">
                      <span className="font-mono w-12">{s.strike}</span>
                      <div className="flex-1 h-2 bg-bg-2 rounded">
                        <div className="h-full bg-bullish rounded" style={{ width: `${Math.min(100, s.putOIChange / 5000)}%` }} />
                      </div>
                      <span className="font-mono num text-bullish">+{formatNumber(s.putOIChange / 1000, 0)}K</span>
                    </div>
                  ))}
                </div>
              </Panel>
            </div>
          </div>
        )}
        {activeTab === 'iv' && <div className="p-6 text-center text-fg-muted">IV Surface · 3D Volatility Visualization</div>}
        {activeTab === 'flow' && <div className="p-6 text-center text-fg-muted">Option Flow · Live Trade Tape</div>}
        {activeTab === 'strategies' && <StrategyBuilder chain={chain} />}
        {activeTab === 'calc' && <OptionCalculator />}
      </Panel>

      {/* Right: Greeks + Analysis */}
      <div className="col-span-3 flex flex-col gap-2 min-h-0">
        <Panel title="Greeks Summary" actions={<Pill variant="info" className="text-2xs">ATM</Pill>}>
          <div className="space-y-2">
            {[
              { greek: 'Delta', value: '0.52', desc: 'directional' },
              { greek: 'Gamma', value: '0.0035', desc: 'convexity' },
              { greek: 'Theta', value: '-4.85', desc: 'time decay' },
              { greek: 'Vega', value: '12.4', desc: 'vol sensitivity' },
              { greek: 'Rho', value: '0.18', desc: 'rate' },
            ].map((g) => (
              <div key={g.greek} className="flex items-center justify-between p-2 bg-bg-2 rounded">
                <div>
                  <div className="text-xs font-semibold">{g.greek}</div>
                  <div className="text-2xs text-fg-dim">{g.desc}</div>
                </div>
                <div className="font-mono num text-sm">{g.value}</div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="PCR Trend" noPadding>
          <div className="p-3">
            <div className="text-2xl font-semibold font-mono num text-bullish">{chain.pcr}</div>
            <div className="text-2xs text-fg-muted mb-2">Bullish bias</div>
            <div className="text-2xs space-y-1">
              <div className="flex justify-between"><span className="text-fg-dim">5min ago</span><span className="font-mono num">1.15</span></div>
              <div className="flex justify-between"><span className="text-fg-dim">15min ago</span><span className="font-mono num">1.08</span></div>
              <div className="flex justify-between"><span className="text-fg-dim">1hr ago</span><span className="font-mono num">0.92</span></div>
            </div>
          </div>
        </Panel>

        <Panel title="Max Pain" noPadding>
          <div className="p-3">
            <div className="text-2xl font-semibold font-mono num">{formatIN(chain.maxPain, 0)}</div>
            <div className="text-2xs text-fg-muted mb-2">Expiry magnet level</div>
            <div className="text-2xs space-y-1">
              <div className="flex justify-between"><span className="text-fg-dim">Distance from spot</span><span className="font-mono num">{(((chain.maxPain - chain.spot) / chain.spot) * 100).toFixed(2)}%</span></div>
              <div className="flex justify-between"><span className="text-fg-dim">Direction</span><Pill variant={chain.maxPain < chain.spot ? 'bull' : 'bear'} className="text-2xs">{chain.maxPain < chain.spot ? '↑ Up' : '↓ Down'}</Pill></div>
            </div>
          </div>
        </Panel>

        <Panel title="OI Walls" noPadding>
          <div className="p-3 space-y-2 text-2xs">
            <div>
              <div className="flex justify-between">
                <span className="text-bearish">Call Wall</span>
                <span className="font-mono num">25,000</span>
              </div>
              <div className="h-1.5 bg-bg-2 rounded mt-1">
                <div className="h-full bg-bearish" style={{ width: '85%' }} />
              </div>
              <div className="text-fg-muted mt-0.5">OI: 1.2M</div>
            </div>
            <div>
              <div className="flex justify-between">
                <span className="text-bullish">Put Wall</span>
                <span className="font-mono num">24,700</span>
              </div>
              <div className="h-1.5 bg-bg-2 rounded mt-1">
                <div className="h-full bg-bullish" style={{ width: '92%' }} />
              </div>
              <div className="text-fg-muted mt-0.5">OI: 1.4M</div>
            </div>
            <div className="pt-2 border-t border-line flex justify-between">
              <span className="text-fg-dim">Expected Range</span>
              <span className="font-mono num">24,700 - 25,000</span>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  )
}

function StrategyBuilder({ chain }: { chain: ReturnType<typeof generateOptionChain> }) {
  return (
    <div className="p-3 space-y-3">
      <div className="grid grid-cols-4 gap-2">
        {[
          { name: 'Long Call', legs: 1, risk: 'Limited', reward: 'Unlimited', color: 'bull' },
          { name: 'Long Put', legs: 1, risk: 'Limited', reward: 'Substantial', color: 'bear' },
          { name: 'Bull Call Spread', legs: 2, risk: 'Limited', reward: 'Limited', color: 'info' },
          { name: 'Bear Put Spread', legs: 2, risk: 'Limited', reward: 'Limited', color: 'warn' },
          { name: 'Straddle', legs: 2, risk: 'Limited', reward: 'Unlimited', color: 'brand' },
          { name: 'Strangle', legs: 2, risk: 'Limited', reward: 'Unlimited', color: 'brand' },
          { name: 'Iron Condor', legs: 4, risk: 'Limited', reward: 'Limited', color: 'neutral' },
          { name: 'Butterfly', legs: 3, risk: 'Limited', reward: 'Limited', color: 'info' },
        ].map((s, i) => (
          <button key={i} className="p-3 bg-bg-2 rounded border border-line text-left hover:border-brand transition-colors">
            <div className="flex items-center gap-1.5">
              <Pill variant={s.color as any} className="text-2xs">{s.legs} leg</Pill>
            </div>
            <div className="text-sm font-semibold mt-1.5">{s.name}</div>
            <div className="text-2xs text-fg-muted mt-1">Risk: {s.risk}</div>
            <div className="text-2xs text-fg-muted">Reward: {s.reward}</div>
          </button>
        ))}
      </div>
    </div>
  )
}

function OptionCalculator() {
  return (
    <div className="p-3 max-w-2xl mx-auto">
      <Panel title="Black-Scholes Calculator">
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-2xs text-fg-dim uppercase tracking-wider">Spot Price</label>
              <input type="number" defaultValue={24900} className="w-full h-9 bg-bg-0 border border-line rounded px-2 text-sm num mt-1" />
            </div>
            <div>
              <label className="text-2xs text-fg-dim uppercase tracking-wider">Strike Price</label>
              <input type="number" defaultValue={25000} className="w-full h-9 bg-bg-0 border border-line rounded px-2 text-sm num mt-1" />
            </div>
            <div>
              <label className="text-2xs text-fg-dim uppercase tracking-wider">Days to Expiry</label>
              <input type="number" defaultValue={7} className="w-full h-9 bg-bg-0 border border-line rounded px-2 text-sm num mt-1" />
            </div>
            <div>
              <label className="text-2xs text-fg-dim uppercase tracking-wider">Implied Vol (%)</label>
              <input type="number" step="0.1" defaultValue={14.5} className="w-full h-9 bg-bg-0 border border-line rounded px-2 text-sm num mt-1" />
            </div>
            <div>
              <label className="text-2xs text-fg-dim uppercase tracking-wider">Risk-free Rate (%)</label>
              <input type="number" step="0.1" defaultValue={6.5} className="w-full h-9 bg-bg-0 border border-line rounded px-2 text-sm num mt-1" />
            </div>
            <div>
              <label className="text-2xs text-fg-dim uppercase tracking-wider">Type</label>
              <select className="w-full h-9 bg-bg-0 border border-line rounded px-2 text-sm mt-1">
                <option>Call (CE)</option>
                <option>Put (PE)</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-5 gap-2 pt-3 border-t border-line">
            {[
              { label: 'Premium', value: '142.50', color: 'text-fg' },
              { label: 'Delta', value: '0.485', color: 'text-info' },
              { label: 'Gamma', value: '0.0024', color: 'text-info' },
              { label: 'Theta', value: '-12.45', color: 'text-bearish' },
              { label: 'Vega', value: '8.65', color: 'text-info' },
            ].map((g, i) => (
              <div key={i} className="p-2 bg-bg-2 rounded border border-line text-center">
                <div className="text-2xs text-fg-dim uppercase tracking-wider">{g.label}</div>
                <div className={cn('text-lg font-semibold font-mono num', g.color)}>{g.value}</div>
              </div>
            ))}
          </div>
        </div>
      </Panel>
    </div>
  )
}
