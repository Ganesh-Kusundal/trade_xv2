import { Panel } from '@/components/ui/Panel'
import { Pill } from '@/components/ui/Pill'
import { useState, useMemo } from 'react'
import { SCANNERS, generateScanResults } from '@/services/mockData'
import { useLiveQuotes } from '@/services/liveSimulator'
import { cn, formatIN, pnlColor, formatNumber, formatTime } from '@/lib/utils'
import { Play, Save, Plus, Filter, BarChart3, Settings, History, Star, ChevronDown, ChevronRight, ArrowUpDown, TrendingUp, Activity, Sparkles, Target, Zap, RefreshCw } from 'lucide-react'
import type { Universe, ScanType } from '@/types/trading'

const SCAN_TYPES: { id: ScanType; label: string }[] = [
  { id: 'MOMENTUM', label: 'Momentum' },
  { id: 'BREAKOUT', label: 'Breakout' },
  { id: 'REVERSAL', label: 'Reversal' },
  { id: 'VOLUME', label: 'Volume' },
  { id: 'OI_BUILDER', label: 'OI Build-up' },
  { id: 'VWAP', label: 'VWAP' },
  { id: 'RS', label: 'RS Rank' },
  { id: 'CUSTOM', label: 'Custom' },
]

const UNIVERSES: Universe[] = ['NIFTY50', 'NIFTY100', 'NIFTY200', 'NIFTY500', 'BANKNIFTY', 'FINNIFTY', 'CUSTOM']

const DEFAULT_FILTERS = [
  { id: 'price', field: 'Price', op: '>', value: 50 },
  { id: 'volume', field: 'Volume', op: '>', value: 100000 },
  { id: 'rsi', field: 'RSI(14)', op: 'BETWEEN', value: [40, 70] },
  { id: 'roc', field: 'ROC(5)', op: '>', value: 0 },
]

export function Scanner() {
  const [selectedScanner, setSelectedScanner] = useState(SCANNERS[0])
  const [universe, setUniverse] = useState<Universe>(SCANNERS[0].universe)
  const [scanType, setScanType] = useState<ScanType>(SCANNERS[0].type)
  const [tab, setTab] = useState<'market' | 'mine' | 'history'>('market')
  const [running, setRunning] = useState(false)

  const result = useMemo(() => generateScanResults(selectedScanner), [selectedScanner])
  const watchlistSymbols = result.candidates.slice(0, 50).map((c) => c.symbol)
  const quotes = useLiveQuotes({ symbols: watchlistSymbols, intervalMs: 2000 })

  const runScan = () => {
    setRunning(true)
    setTimeout(() => setRunning(false), 1500)
  }

  return (
    <div className="h-full grid grid-cols-12 gap-2 p-2">
      {/* Sidebar: Scanners list */}
      <Panel
        className="col-span-2"
        title="Scanners"
        actions={
          <button className="h-6 w-6 rounded hover:bg-bg-3 text-fg-muted flex items-center justify-center"><Plus className="h-3.5 w-3.5" /></button>
        }
        noPadding
      >
        <div className="px-2 py-1.5 border-b border-line flex gap-1">
          {(['market', 'mine', 'history'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                'flex-1 h-6 text-2xs rounded font-medium',
                tab === t ? 'bg-bg-3 text-fg' : 'text-fg-muted hover:bg-bg-2',
              )}
            >
              {t === 'market' ? 'Market' : t === 'mine' ? 'My' : 'History'}
            </button>
          ))}
        </div>
        <div className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 160px)' }}>
          {SCANNERS.map((s) => (
            <button
              key={s.id}
              onClick={() => {
                setSelectedScanner(s)
                setUniverse(s.universe)
                setScanType(s.type)
              }}
              className={cn(
                'w-full text-left px-2 py-2 hover:bg-bg-2 border-b border-line-subtle',
                selectedScanner.id === s.id && 'bg-brand/10 border-l-2 border-brand',
              )}
            >
              <div className="flex items-center gap-1.5">
                <Pill
                  variant={
                    s.type === 'MOMENTUM' ? 'bull' :
                    s.type === 'BREAKOUT' ? 'info' :
                    s.type === 'REVERSAL' ? 'warn' :
                    s.type === 'OI_BUILDER' ? 'brand' :
                    'neutral'
                  }
                  className="text-2xs"
                >
                  {s.type}
                </Pill>
                {s.enabled && <span className="h-1.5 w-1.5 rounded-full bg-bullish pulse-dot" />}
              </div>
              <div className="text-xs font-medium mt-1 truncate">{s.name}</div>
              <div className="text-2xs text-fg-dim flex items-center justify-between mt-0.5">
                <span>{s.universe}</span>
                <span>{s.resultCount} results</span>
              </div>
            </button>
          ))}
        </div>
      </Panel>

      {/* Builder + Filters */}
      <div className="col-span-3 flex flex-col gap-2 min-h-0">
        <Panel
          title="Scanner Builder"
          actions={
            <>
              <Pill variant="neutral" className="text-2xs">Draft</Pill>
              <button className="h-6 w-6 rounded hover:bg-bg-3 text-fg-muted flex items-center justify-center"><Settings className="h-3.5 w-3.5" /></button>
            </>
          }
        >
          <div className="space-y-2">
            <div>
              <label className="text-2xs text-fg-dim uppercase tracking-wider">Name</label>
              <input
                value={selectedScanner.name}
                onChange={(e) => setSelectedScanner((s) => ({ ...s, name: e.target.value }))}
                className="w-full h-8 bg-bg-0 border border-line rounded px-2 text-sm mt-1 focus:border-brand focus:outline-none"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-2xs text-fg-dim uppercase tracking-wider">Universe</label>
                <select
                  value={universe}
                  onChange={(e) => setUniverse(e.target.value as Universe)}
                  className="w-full h-8 bg-bg-0 border border-line rounded px-2 text-xs mt-1 focus:border-brand focus:outline-none"
                >
                  {UNIVERSES.map((u) => (
                    <option key={u} value={u}>{u}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-2xs text-fg-dim uppercase tracking-wider">Type</label>
                <select
                  value={scanType}
                  onChange={(e) => setScanType(e.target.value as ScanType)}
                  className="w-full h-8 bg-bg-0 border border-line rounded px-2 text-xs mt-1 focus:border-brand focus:outline-none"
                >
                  {SCAN_TYPES.map((s) => (
                    <option key={s.id} value={s.id}>{s.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <label className="text-2xs text-fg-dim uppercase tracking-wider flex items-center gap-1">
                <Filter className="h-3 w-3" /> Filters ({DEFAULT_FILTERS.length})
              </label>
              <div className="space-y-1.5 mt-1.5">
                {DEFAULT_FILTERS.map((f) => (
                  <div key={f.id} className="flex items-center gap-1.5 px-2 py-1.5 bg-bg-0 border border-line rounded text-xs">
                    <span className="font-medium flex-1">{f.field}</span>
                    <span className="text-fg-dim font-mono">{f.op}</span>
                    <span className="font-mono num text-bullish">
                      {Array.isArray(f.value) ? `${f.value[0]}-${f.value[1]}` : f.value}
                    </span>
                  </div>
                ))}
                <button className="w-full h-7 bg-bg-2 hover:bg-bg-3 rounded text-2xs text-fg-muted flex items-center justify-center gap-1">
                  <Plus className="h-3 w-3" /> Add filter
                </button>
              </div>
            </div>
            <div>
              <label className="text-2xs text-fg-dim uppercase tracking-wider">Schedule</label>
              <select className="w-full h-8 bg-bg-0 border border-line rounded px-2 text-xs mt-1 focus:border-brand focus:outline-none">
                <option>Every 1 minute</option>
                <option>Every 5 minutes</option>
                <option>Every 15 minutes</option>
                <option>Daily at 9:30 AM</option>
                <option>Manual only</option>
              </select>
            </div>
            <div className="grid grid-cols-2 gap-2 pt-2">
              <button className="h-9 rounded bg-bg-2 hover:bg-bg-3 text-xs font-medium flex items-center justify-center gap-1">
                <Save className="h-3.5 w-3.5" /> Save
              </button>
              <button
                onClick={runScan}
                disabled={running}
                className="h-9 rounded bg-brand text-white text-xs font-semibold flex items-center justify-center gap-1 hover:bg-brand-600 disabled:opacity-60"
              >
                {running ? (
                  <>
                    <RefreshCw className="h-3.5 w-3.5 animate-spin" /> Running
                  </>
                ) : (
                  <>
                    <Play className="h-3.5 w-3.5" /> Run Scan
                  </>
                )}
              </button>
            </div>
            <div className="pt-2 border-t border-line space-y-1 text-2xs">
              <div className="flex justify-between">
                <span className="text-fg-dim">Universe size</span>
                <span className="font-mono num">{result.universeSize}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-fg-dim">Last run</span>
                <span className="font-mono">{formatTime(result.executedAt)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-fg-dim">Duration</span>
                <span className="font-mono">{result.duration}ms</span>
              </div>
              <div className="flex justify-between">
                <span className="text-fg-dim">Results</span>
                <span className="font-mono text-bullish">{result.count}</span>
              </div>
            </div>
          </div>
        </Panel>
      </div>

      {/* Results */}
      <Panel
        className="col-span-7"
        title={
          <div className="flex items-center gap-2">
            <span>Scan Results</span>
            <Pill variant="info" className="text-2xs">{selectedScanner.name}</Pill>
            <Pill variant="neutral" className="text-2xs">{universe}</Pill>
          </div>
        }
        subtitle={`${result.count} candidates · ${result.universeSize} scanned`}
        actions={
          <>
            <button className="btn btn-ghost"><BarChart3 className="h-3.5 w-3.5" /> Analyze</button>
            <button className="btn btn-secondary"><Save className="h-3.5 w-3.5" /> Save</button>
          </>
        }
        noPadding
      >
        <div className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 180px)' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th className="w-8">#</th>
                <th>Symbol</th>
                <th className="text-right">Score</th>
                <th className="text-right">LTP</th>
                <th className="text-right">Chg%</th>
                <th className="text-right">Vol</th>
                <th className="text-right">RSI</th>
                <th className="text-right">ROC</th>
                <th>Reasons</th>
                <th>RS</th>
              </tr>
            </thead>
            <tbody>
              {result.candidates.map((c) => {
                const q = quotes[c.symbol]
                return (
                  <tr key={c.symbol}>
                    <td className="text-fg-dim font-mono text-2xs">{c.rank}</td>
                    <td>
                      <div className="flex items-center gap-1.5">
                        <button className="text-fg-dim hover:text-warning"><Star className="h-3 w-3" /></button>
                        <span className="font-semibold">{c.symbol}</span>
                      </div>
                    </td>
                    <td className="text-right">
                      <div className="flex items-center gap-1.5 justify-end">
                        <div className="w-12 h-1.5 bg-bg-2 rounded overflow-hidden">
                          <div className={cn('h-full', c.score > 70 ? 'bg-bullish' : c.score > 40 ? 'bg-warning' : 'bg-bearish')} style={{ width: `${c.score}%` }} />
                        </div>
                        <span className="font-mono num w-8">{c.score.toFixed(0)}</span>
                      </div>
                    </td>
                    <td className="text-right font-mono">{formatIN(q?.ltp || 0)}</td>
                    <td className={cn('text-right font-mono', pnlColor(q?.changePct || 0))}>
                      {q && `${(q.changePct >= 0 ? '+' : '')}${q.changePct.toFixed(2)}%`}
                    </td>
                    <td className="text-right font-mono text-fg-muted">
                      {q ? formatNumber(q.volume / 1000, 0) + 'K' : '-'}
                    </td>
                    <td className="text-right font-mono">
                      <span className={cn(c.metrics.rsi > 70 ? 'text-bearish' : c.metrics.rsi < 30 ? 'text-bullish' : 'text-fg')}>
                        {c.metrics.rsi?.toFixed(0)}
                      </span>
                    </td>
                    <td className={cn('text-right font-mono', pnlColor(c.metrics.roc || 0))}>
                      {c.metrics.roc?.toFixed(1)}%
                    </td>
                    <td>
                      <div className="flex flex-wrap gap-1">
                        {c.reasons.slice(0, 2).map((r, i) => (
                          <Pill key={i} variant="neutral" className="text-2xs">{r}</Pill>
                        ))}
                      </div>
                    </td>
                    <td>
                      <Pill variant={c.metrics.roc && c.metrics.roc > 3 ? 'bull' : c.metrics.roc && c.metrics.roc < 0 ? 'bear' : 'neutral'} className="text-2xs">
                        {c.metrics.roc && c.metrics.roc > 3 ? '↑' : c.metrics.roc && c.metrics.roc < 0 ? '↓' : '→'}
                      </Pill>
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
