/**
 * AMT Scalper System — Full Dashboard
 *
 * Faithful reproduction of the AMT Scalper System trading UI:
 *   - Vertical sidebar with AMT logo and nav (Dashboard, Live Chart, Deep Chart, ...)
 *   - Top status bar: SYSTEM STATUS / AUTO TRADING / BROKER / ACCOUNT / TIME
 *   - KPI strip: Balance, Equity, Daily P/L, Total P/L, Win Rate, Active Pairs
 *   - Main 3-column area: Deep Chart (canvas) | Volume Profile (canvas) | Deep DOM (canvas)
 *   - Bottom 4-column: Active Positions | Performance | Watchlist | System Logs
 *   - Footer status bar: version, license, broker time, ping, uptime
 *
 * All charts are canvas-rendered. The colour palette is the cyan/black
 * AMT Scalper look from the reference screenshots.
 */

import { useState, useEffect, useMemo, useRef } from 'react'
import { useLiveQuotes } from '@/services/liveSimulator'
import { AMTChart } from '@/components/ui/AMTChart'
import { AMTVolumeProfile } from '@/components/ui/AMTVolumeProfile'
import { AMTDeepDOM } from '@/components/ui/AMTDeepDOM'
import { generateCandles } from '@/services/mockData'
import { generateVolumeProfile } from '@/services/deepchartsData'
import { cn, formatCompact, formatIN, formatNumber, formatTime, pnlColor } from '@/lib/utils'
import {
  LayoutDashboard, BarChart3, CandlestickChart as CandlestickIcon, Layers,
  Activity, Briefcase, History, FileText, Shield, Settings, Zap, Bell,
  Key, HelpCircle, Cpu, Power, PowerOff, ChevronDown, Settings as Gear,
  TrendingUp, TrendingDown, Wifi,
} from 'lucide-react'
import { useUIStore } from '@/store/uiStore'

// ── Sidebar nav items (matches AMT reference) ────────────────────────────
const NAV_ITEMS = [
  { id: 'dashboard', label: 'DASHBOARD', icon: LayoutDashboard, badge: undefined as string | undefined, active: false },
  { id: 'live-chart', label: 'LIVE CHART', icon: BarChart3, badge: undefined, active: false },
  { id: 'deep-chart', label: 'DEEP CHART', icon: CandlestickIcon, badge: 'NEW', active: true },
  { id: 'deep-dom', label: 'DEEP DOM', icon: Layers, badge: 'NEW', active: false },
  { id: 'volume-profile', label: 'VOLUME PROFILE', icon: BarChart3, badge: 'NEW', active: false },
  { id: 'performance', label: 'PERFORMANCE', icon: Activity, badge: undefined, active: false },
  { id: 'positions', label: 'POSITIONS (AUTOMATED)', icon: Briefcase, badge: undefined, active: false },
  { id: 'trades', label: 'TRADES HISTORY', icon: History, badge: undefined, active: false },
  { id: 'logs', label: 'SYSTEM LOGS', icon: FileText, badge: undefined, active: false },
  { id: 'risk', label: 'RISK MANAGEMENT', icon: Shield, badge: undefined, active: false },
  { id: 'settings', label: 'SETTINGS', icon: Settings, badge: undefined, active: false },
  { id: 'strategy', label: 'STRATEGY', icon: Zap, badge: undefined, active: false },
  { id: 'alerts', label: 'ALERTS', icon: Bell, badge: undefined, active: false },
  { id: 'license', label: 'LICENSE', icon: Key, badge: undefined, active: false },
  { id: 'support', label: 'SUPPORT', icon: HelpCircle, badge: undefined, active: false },
]

// ── Seed data (in real usage these come from the broker) ──────────────────
const SYMBOLS = ['XAUUSDm', 'EURUSDm', 'GBPUSDm', 'USDJPYm', 'AUDUSDm', 'USDCADm']
const SEED_POSITIONS = [
  { symbol: 'XAUUSDm', type: 'BUY', volume: 0.50, entry: 2345.12, current: 2348.65, sl: 2342.00, tp: 2352.00, profit: 176.50 },
  { symbol: 'EURUSDm', type: 'BUY', volume: 0.30, entry: 1.08421, current: 1.08567, sl: 1.08200, tp: 1.08850, profit: 43.80 },
  { symbol: 'GBPUSDm', type: 'SELL', volume: 0.30, entry: 1.27145, current: 1.27012, sl: 1.27450, tp: 1.26800, profit: 39.90 },
  { symbol: 'USDJPYm', type: 'BUY', volume: 0.30, entry: 156.245, current: 156.512, sl: 155.900, tp: 156.900, profit: 51.80 },
  { symbol: 'AUDUSDm', type: 'BUY', volume: 0.30, entry: 0.66541, current: 0.66678, sl: 0.66350, tp: 0.66850, profit: 41.10 },
  { symbol: 'USDCADm', type: 'SELL', volume: 0.30, entry: 1.36402, current: 1.36402, sl: 1.36800, tp: 1.36000, profit: 32.70 },
]
const WATCHLIST = [
  { symbol: 'XAUUSDm', price: 2348.65, change: 0.42, vol: 'High' },
  { symbol: 'EURUSDm', price: 1.08567, change: 0.15, vol: 'Medium' },
  { symbol: 'GBPUSDm', price: 1.27012, change: -0.12, vol: 'High' },
  { symbol: 'USDJPYm', price: 156.512, change: 0.25, vol: 'Medium' },
  { symbol: 'AUDUSDm', price: 0.66678, change: 0.18, vol: 'Medium' },
  { symbol: 'USDCADm', price: 1.36402, change: -0.10, vol: 'Low' },
]
const SYS_LOGS = [
  { time: '10:24:33 AM', msg: 'Trade closed: XAUUSDm BUY +$176.50', ok: true },
  { time: '10:24:28 AM', msg: 'New signal: EURUSDm BUY', ok: true },
  { time: '10:24:27 AM', msg: 'Order executed: EURUSDm BUY 0.30', ok: true },
  { time: '10:24:21 AM', msg: 'Take profit hit: GBPUSDm SELL +$39.90', ok: true },
  { time: '10:24:15 AM', msg: 'New signal: XAUUSDm BUY', ok: true },
  { time: '10:24:14 AM', msg: 'Order executed: XAUUSDm BUY 0.50', ok: true },
  { time: '10:24:07 AM', msg: 'System scan completed (28 pairs)', ok: true },
  { time: '10:24:05 AM', msg: 'Risk check passed', ok: true },
  { time: '10:24:01 AM', msg: 'News filter: No high impact news', ok: true },
  { time: '10:24:00 AM', msg: 'AMT Scalper System Started', ok: true },
]

// ── Sidebar component ──────────────────────────────────────────────────────
function AMTSidebar() {
  return (
    <aside className="w-56 bg-black border-r border-cyan-500/20 flex flex-col h-full text-cyan-400 flex-shrink-0">
      {/* Logo */}
      <div className="px-3 py-3 border-b border-cyan-500/20 flex items-center gap-2">
        <div className="h-9 w-9 rounded bg-gradient-to-br from-cyan-400 via-cyan-500 to-cyan-700 flex items-center justify-center shadow-lg shadow-cyan-500/20">
          <Cpu className="h-5 w-5 text-black" />
        </div>
        <div>
          <div className="text-cyan-300 font-bold text-sm tracking-wider">AMT SCALPER</div>
          <div className="text-cyan-500/60 text-[9px] uppercase tracking-widest">Fully Automated</div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-2">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon
          return (
            <button
              key={item.id}
              className={cn(
                'w-full flex items-center justify-between px-3 py-2 text-[11px] font-mono uppercase tracking-wider transition-colors',
                item.active
                  ? 'bg-cyan-500/10 text-cyan-300 border-l-2 border-cyan-400'
                  : 'text-cyan-500/70 hover:text-cyan-300 hover:bg-cyan-500/5 border-l-2 border-transparent',
              )}
            >
              <span className="flex items-center gap-2">
                <Icon className="h-3.5 w-3.5" />
                {item.label}
              </span>
              {item.badge && (
                <span className="text-[8px] bg-cyan-500/30 text-cyan-200 px-1 rounded font-bold">
                  {item.badge}
                </span>
              )}
            </button>
          )
        })}
      </nav>

      {/* Bottom AI badge */}
      <div className="px-3 py-3 border-t border-cyan-500/20">
        <div className="bg-cyan-500/10 border border-cyan-500/30 rounded p-2 text-center">
          <div className="h-12 w-12 mx-auto rounded-full bg-gradient-to-br from-cyan-400 to-cyan-700 flex items-center justify-center mb-1">
            <Cpu className="h-6 w-6 text-black" />
          </div>
          <div className="text-cyan-300 font-bold text-[10px] tracking-wider">AMT SCALPER</div>
          <div className="text-bullish text-[9px] mt-0.5">FULLY AUTOMATED</div>
          <div className="text-cyan-500/60 text-[9px]">NO MANUAL ORDERS</div>
        </div>
      </div>
    </aside>
  )
}

// ── Top status bar ─────────────────────────────────────────────────────────
function AMTTopBar({ broker, account, onBack }: { broker: string; account: string; onBack: () => void }) {
  const [now, setNow] = useState(new Date())
  const [autoTrading, setAutoTrading] = useState(true)

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const time = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true })
  const date = now.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' })

  return (
    <div className="h-12 bg-black border-b border-cyan-500/20 flex items-center justify-between px-3 text-cyan-400 text-[10px] font-mono">
      <div className="flex items-center gap-3">
        <button
          onClick={onBack}
          className="text-cyan-500/60 hover:text-cyan-300 text-[9px] uppercase tracking-wider"
        >
          ← BACK
        </button>
        <div className="h-6 w-px bg-cyan-500/20" />
        <div>
          <div className="text-cyan-300 font-bold tracking-widest text-sm">AMT SCALPER SYSTEM</div>
          <div className="text-cyan-500/70 text-[9px] tracking-wider">AUTOMATED TRADING SYSTEM</div>
        </div>
      </div>

      <div className="flex items-center gap-6">
        <div>
          <div className="text-cyan-500/60 text-[8px] uppercase">SYSTEM STATUS</div>
          <div className="text-bullish font-bold flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-bullish animate-pulse" />
            LIVE &amp; AUTOMATED
          </div>
        </div>
        <div>
          <div className="text-cyan-500/60 text-[8px] uppercase">AUTO TRADING</div>
          <button
            onClick={() => setAutoTrading((v) => !v)}
            className="flex items-center gap-1.5 font-bold"
          >
            <div
              className={cn(
                'h-3.5 w-7 rounded-full p-0.5 flex items-center transition-all',
                autoTrading ? 'bg-bullish/40 justify-end' : 'bg-fg-dim/30 justify-start',
              )}
            >
              <div className={cn('h-2.5 w-2.5 rounded-full bg-bullish shadow-[0_0_6px_rgb(34,197,94,0.8)]')} />
            </div>
            <span className={autoTrading ? 'text-bullish' : 'text-fg-dim'}>{autoTrading ? 'ON' : 'OFF'}</span>
          </button>
        </div>
        <div>
          <div className="text-cyan-500/60 text-[8px] uppercase">BROKER</div>
          <div className="flex items-center gap-1.5 font-bold text-cyan-300">
            <span className="h-1.5 w-1.5 rounded-full bg-bullish" />
            {broker} <ChevronDown className="h-3 w-3" />
          </div>
        </div>
        <div>
          <div className="text-cyan-500/60 text-[8px] uppercase">ACCOUNT</div>
          <div className="text-cyan-300 font-bold">{account} <ChevronDown className="inline h-3 w-3" /></div>
        </div>
        <div>
          <div className="text-cyan-500/60 text-[8px] uppercase">TIME (SERVER)</div>
          <div className="text-cyan-300 font-bold text-[11px]">{time}</div>
          <div className="text-cyan-500/60 text-[8px]">{date}</div>
        </div>
        <button className="text-cyan-500/60 hover:text-cyan-300">
          <Gear className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}

// ── KPI strip ──────────────────────────────────────────────────────────────
function AMTKPIStrip() {
  const data = {
    balance: 10456.78,
    equity: 10789.32,
    dailyPnl: 332.54,
    dailyPnlPct: 3.28,
    totalPnl: 2456.78,
    totalPnlPct: 31.07,
    winRate: 87.42,
    activePairs: 6,
    scanning: 28,
  }
  return (
    <div className="grid grid-cols-6 border-b border-cyan-500/20 bg-black">
      <KPI label="BALANCE" value={`$${formatIN(data.balance)}`} icon={Layers} />
      <KPI label="EQUITY" value={`$${formatIN(data.equity)}`} icon={Activity} trend={{ value: 3.28, positive: true }} />
      <KPI
        label="DAILY P/L"
        value={`+$${formatIN(data.dailyPnl)}`}
        sub={`+${data.dailyPnlPct.toFixed(2)}%`}
        valueClass="text-bullish"
      />
      <KPI
        label="TOTAL P/L"
        value={`+$${formatIN(data.totalPnl)}`}
        sub={`+${data.totalPnlPct.toFixed(2)}%`}
        valueClass="text-bullish"
      />
      <KPI label="WIN RATE" value={`${data.winRate.toFixed(2)}%`} sub="(Today)" valueClass="text-bullish" />
      <KPI label="ACTIVE PAIRS" value={`${data.activePairs}`} sub={`(Scanning ${data.scanning})`} />
    </div>
  )
}

function KPI({
  label,
  value,
  sub,
  icon: Icon,
  valueClass,
  trend,
}: {
  label: string
  value: string
  sub?: string
  icon?: any
  valueClass?: string
  trend?: { value: number; positive: boolean }
}) {
  return (
    <div className="px-3 py-2 border-r border-cyan-500/20 flex items-center justify-between">
      <div>
        <div className="text-cyan-500/60 text-[8px] uppercase tracking-wider font-mono">{label}</div>
        <div className={cn('text-cyan-300 font-bold text-base num font-mono mt-0.5', valueClass)}>{value}</div>
        {sub && <div className={cn('text-[10px] font-mono', valueClass)}>{sub}</div>}
      </div>
      {Icon && <Icon className="h-5 w-5 text-cyan-500/40" />}
    </div>
  )
}

// ── Active positions ──────────────────────────────────────────────────────
function PositionsTable() {
  return (
    <div className="bg-black border border-cyan-500/20 rounded h-full flex flex-col">
      <div className="px-3 py-1.5 border-b border-cyan-500/20 flex items-center justify-between">
        <span className="text-cyan-400 font-bold text-[10px] uppercase tracking-wider">
          ACTIVE POSITIONS <span className="text-cyan-500/60">(AUTOMATED)</span>
        </span>
      </div>
      <div className="flex-1 overflow-auto">
        <table className="w-full text-[10px] font-mono">
          <thead className="sticky top-0 bg-black/90">
            <tr className="text-cyan-500/70 text-[9px] uppercase">
              <th className="px-2 py-1 text-left">SYMBOL</th>
              <th className="px-2 py-1 text-left">TYPE</th>
              <th className="px-2 py-1 text-right">VOLUME</th>
              <th className="px-2 py-1 text-right">ENTRY</th>
              <th className="px-2 py-1 text-right">CURRENT</th>
              <th className="px-2 py-1 text-right">SL</th>
              <th className="px-2 py-1 text-right">TP</th>
              <th className="px-2 py-1 text-right">PROFIT</th>
            </tr>
          </thead>
          <tbody>
            {SEED_POSITIONS.map((p) => (
              <tr key={p.symbol} className="border-b border-cyan-500/10 hover:bg-cyan-500/5">
                <td className="px-2 py-1 text-cyan-300 font-semibold">{p.symbol}</td>
                <td className={cn('px-2 py-1 font-bold', p.type === 'BUY' ? 'text-bullish' : 'text-bearish')}>
                  {p.type}
                </td>
                <td className="px-2 py-1 text-right text-cyan-300 num">{p.volume.toFixed(2)}</td>
                <td className="px-2 py-1 text-right text-cyan-300/80 num">{p.entry.toFixed(5)}</td>
                <td className="px-2 py-1 text-right text-cyan-300 num">{p.current.toFixed(5)}</td>
                <td className="px-2 py-1 text-right text-bearish num">{p.sl.toFixed(5)}</td>
                <td className="px-2 py-1 text-right text-bullish num">{p.tp.toFixed(5)}</td>
                <td className={cn('px-2 py-1 text-right font-bold num', pnlColor(p.profit))}>
                  {p.profit >= 0 ? '+' : ''}${p.profit.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Performance (today) ───────────────────────────────────────────────────
function PerformancePanel() {
  const stats = [
    { label: 'TOTAL TRADES', value: '46', color: 'text-cyan-300' },
    { label: 'PROFITABLE TRADES', value: '40', color: 'text-bullish' },
    { label: 'LOSING TRADES', value: '6', color: 'text-fg-muted' },
    { label: 'WIN RATE', value: '87.42%', color: 'text-bullish' },
    { label: 'BEST TRADE', value: '+$86.40', color: 'text-bullish' },
    { label: 'WORST TRADE', value: '-$24.30', color: 'text-bearish' },
    { label: 'AVERAGE WINN', value: '+$45.12', color: 'text-bullish' },
    { label: 'AVERAGE LOSS', value: '-$19.43', color: 'text-bearish' },
    { label: 'PROFIT FACTOR', value: '3.12', color: 'text-bullish' },
    { label: 'EXPECTED VALUE', value: '+$22.34', color: 'text-bullish' },
  ]
  const curve = useMemo(() => {
    const arr = []
    let eq = 10000
    for (let i = 0; i < 50; i++) {
      eq *= 1 + (Math.sin(i / 3) * 0.005 + 0.0028)
      arr.push({ x: i, y: eq })
    }
    return arr
  }, [])

  return (
    <div className="bg-black border border-cyan-500/20 rounded h-full flex flex-col">
      <div className="px-3 py-1.5 border-b border-cyan-500/20 flex items-center justify-between">
        <span className="text-cyan-400 font-bold text-[10px] uppercase tracking-wider">PERFORMANCE (TODAY)</span>
        <div className="text-[9px] text-cyan-500/70">EQUITY CURVE <span className="text-cyan-300">TODAY ▼</span></div>
      </div>
      <div className="flex-1 flex min-h-0">
        <div className="flex-1 p-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[10px] font-mono overflow-auto">
          {stats.map((s) => (
            <div key={s.label} className="flex justify-between">
              <span className="text-cyan-500/70 uppercase tracking-wider text-[9px]">{s.label}</span>
              <span className={cn('font-bold num', s.color)}>{s.value}</span>
            </div>
          ))}
        </div>
        <div className="w-1/2 p-2 border-l border-cyan-500/20">
          <EquityCurveMini data={curve} />
        </div>
      </div>
    </div>
  )
}

function EquityCurveMini({ data }: { data: { x: number; y: number }[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()
    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr
    canvas.style.width = `${rect.width}px`
    canvas.style.height = `${rect.height}px`
    const ctx = canvas.getContext('2d')!
    ctx.scale(dpr, dpr)
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, rect.width, rect.height)
    if (data.length === 0) return
    const min = Math.min(...data.map((d) => d.y))
    const max = Math.max(...data.map((d) => d.y))
    const range = max - min || 1
    const pad = 4
    const x = (i: number) => pad + (i / (data.length - 1)) * (rect.width - 2 * pad)
    const y = (v: number) => pad + ((max - v) / range) * (rect.height - 2 * pad)
    // Fill
    ctx.beginPath()
    ctx.moveTo(x(0), rect.height)
    data.forEach((d, i) => ctx.lineTo(x(i), y(d.y)))
    ctx.lineTo(x(data.length - 1), rect.height)
    ctx.closePath()
    const grad = ctx.createLinearGradient(0, 0, 0, rect.height)
    grad.addColorStop(0, 'rgba(34, 197, 94, 0.4)')
    grad.addColorStop(1, 'rgba(34, 197, 94, 0)')
    ctx.fillStyle = grad
    ctx.fill()
    // Line
    ctx.beginPath()
    ctx.strokeStyle = '#16a34a'
    ctx.lineWidth = 1.5
    data.forEach((d, i) => {
      if (i === 0) ctx.moveTo(x(i), y(d.y))
      else ctx.lineTo(x(i), y(d.y))
    })
    ctx.stroke()
    // Time axis
    ctx.fillStyle = '#4a4a4a'
    ctx.font = '8px monospace'
    ctx.textAlign = 'left'
    ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', '24:00'].forEach((t, i) => {
      const tx = pad + (i / 6) * (rect.width - 2 * pad)
      ctx.fillText(t, tx - 12, rect.height - 1)
    })
  }, [data])
  return <canvas ref={canvasRef} className="w-full h-full" />
}

// ── Watchlist ─────────────────────────────────────────────────────────────
function WatchlistPanel() {
  return (
    <div className="bg-black border border-cyan-500/20 rounded h-full flex flex-col">
      <div className="px-3 py-1.5 border-b border-cyan-500/20">
        <span className="text-cyan-400 font-bold text-[10px] uppercase tracking-wider">WATCHLIST</span>
      </div>
      <div className="flex-1 overflow-auto">
        <table className="w-full text-[10px] font-mono">
          <thead className="sticky top-0 bg-black/90">
            <tr className="text-cyan-500/70 text-[9px] uppercase">
              <th className="px-2 py-1 text-left">SYMBOL</th>
              <th className="px-2 py-1 text-right">PRICE</th>
              <th className="px-2 py-1 text-right">CHANGE</th>
              <th className="px-2 py-1 text-right">VOLATILITY</th>
            </tr>
          </thead>
          <tbody>
            {WATCHLIST.map((w) => (
              <tr key={w.symbol} className="border-b border-cyan-500/10 hover:bg-cyan-500/5">
                <td className="px-2 py-1 text-cyan-300 font-semibold">{w.symbol}</td>
                <td className="px-2 py-1 text-right text-cyan-300 num">{w.price.toFixed(5)}</td>
                <td className={cn('px-2 py-1 text-right font-bold num', pnlColor(w.change))}>
                  {w.change >= 0 ? '+' : ''}
                  {w.change.toFixed(2)}%
                </td>
                <td className="px-2 py-1 text-right text-cyan-500/80">{w.vol}</td>
              </tr>
            ))}
            <tr>
              <td colSpan={4} className="px-2 py-1 text-cyan-500/60">
                + Add Symbol
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── System logs ───────────────────────────────────────────────────────────
function SystemLogsPanel() {
  return (
    <div className="bg-black border border-cyan-500/20 rounded h-full flex flex-col">
      <div className="px-3 py-1.5 border-b border-cyan-500/20">
        <span className="text-cyan-400 font-bold text-[10px] uppercase tracking-wider">RECENT SYSTEM LOGS</span>
      </div>
      <div className="flex-1 overflow-auto p-2 space-y-0.5">
        {SYS_LOGS.map((log, i) => (
          <div key={i} className="flex items-start gap-1.5 text-[10px] font-mono">
            <div className="h-1.5 w-1.5 rounded-full bg-bullish flex-shrink-0 mt-1" />
            <span className="text-cyan-500/60 flex-shrink-0">{log.time}</span>
            <span className="text-cyan-300/90">{log.msg}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────

export function AMTScalper() {
  const { setWorkspace } = useUIStore()
  const [symbol, setSymbol] = useState('XAUUSDm')
  const candles = useMemo(() => generateCandles(symbol, '1m', 200), [symbol])
  const liveQuotes = useLiveQuotes({ symbols: [symbol], intervalMs: 1000 })
  const live = liveQuotes[symbol]
  const lastPrice = live?.ltp ?? candles[candles.length - 1]?.close ?? 0

  // Volume profile
  const profile = useMemo(() => generateVolumeProfile(symbol, 24), [symbol])

  // Deep DOM levels
  const domLevels = useMemo(() => {
    const mid = lastPrice || 100
    const tick = 0.05
    const arr: { price: number; bid: number; ask: number }[] = []
    for (let i = 8; i > 0; i--) {
      const p = Number((mid - i * tick).toFixed(2))
      arr.push({ price: p, bid: Math.floor(1_000_000 + Math.random() * 1_500_000), ask: 0 })
    }
    for (let i = 1; i <= 8; i++) {
      const p = Number((mid + i * tick).toFixed(2))
      arr.push({ price: p, bid: 0, ask: Math.floor(1_000_000 + Math.random() * 1_500_000) })
    }
    return arr
  }, [lastPrice])

  return (
    <div className="flex h-screen w-screen bg-black text-cyan-300 overflow-hidden font-mono">
      <AMTSidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <AMTTopBar
          broker="Exness"
          account="AMT-LIVE-01"
          onBack={() => setWorkspace('dashboard')}
        />
        <AMTKPIStrip />

        {/* Main chart area */}
        <div className="flex-1 min-h-0 p-2 grid grid-cols-12 gap-2 overflow-hidden">
          {/* Deep Chart */}
          <div className="col-span-7 flex flex-col">
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2 text-[10px]">
                <span className="text-cyan-400 font-bold tracking-wider">DEEP CHART</span>
                <select
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  className="bg-black border border-cyan-500/30 text-cyan-300 text-[10px] px-1.5 py-0.5 rounded font-mono"
                >
                  {SYMBOLS.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
                <span className="text-cyan-500/60">M1</span>
              </div>
              {live && (
                <div className="text-[10px] text-cyan-300 num">
                  O {formatIN(live.open, 2)} H {formatIN(live.high, 2)} L {formatIN(live.low, 2)} C{' '}
                  <span className={pnlColor(live.changePct)}>{formatIN(live.ltp, 2)}</span>{' '}
                  <span className={pnlColor(live.changePct)}>
                    {live.change >= 0 ? '+' : ''}
                    {live.changePct.toFixed(2)}%
                  </span>
                </div>
              )}
            </div>
            <div className="flex-1 min-h-0">
              <AMTChart
                candles={candles}
                livePrice={lastPrice}
                symbol={symbol}
                height={undefined}
              />
            </div>
          </div>

          {/* Volume Profile */}
          <div className="col-span-2 flex flex-col">
            <div className="text-[10px] text-cyan-400 font-bold tracking-wider mb-1">VOLUME PROFILE</div>
            <div className="flex-1 min-h-0">
              <AMTVolumeProfile
                symbol={symbol}
                bins={profile.levels}
                poc={profile.poc}
                vah={profile.vah}
                val={profile.val}
                height={undefined}
              />
            </div>
          </div>

          {/* Deep DOM */}
          <div className="col-span-3 flex flex-col">
            <div className="text-[10px] text-cyan-400 font-bold tracking-wider mb-1">DEEP DOM ({symbol})</div>
            <div className="flex-1 min-h-0">
              <AMTDeepDOM
                symbol={symbol}
                levels={domLevels}
                spread={0.05}
                lastPrice={lastPrice}
                levelsToShow={8}
                height={undefined}
              />
            </div>
          </div>
        </div>

        {/* Bottom 4-column */}
        <div className="h-56 px-2 pb-2 grid grid-cols-4 gap-2">
          <PositionsTable />
          <PerformancePanel />
          <WatchlistPanel />
          <SystemLogsPanel />
        </div>

        {/* Footer status bar */}
        <div className="h-6 bg-black border-t border-cyan-500/20 flex items-center justify-between px-3 text-cyan-500/70 text-[9px] font-mono">
          <div className="flex items-center gap-4">
            <span>AMT Scalper System v2.3.0</span>
            <span>LICENSED TO: AMT TRADER</span>
          </div>
          <div className="flex items-center gap-4">
            <span>BROKER TIME: 10:24:35 AM</span>
            <span>
              PING: <span className="text-bullish font-bold">18ms</span>
            </span>
            <span className="flex items-center gap-1">
              UPTIME: <span className="text-bullish font-bold">2D 14H 32M 18S</span>{' '}
              <span className="h-1 w-1 rounded-full bg-bullish animate-pulse" />
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default AMTScalper
