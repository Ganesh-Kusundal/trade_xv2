/**
 * AMTChart — Canvas-based Deep Chart for the AMT Scalper System.
 *
 * Renders candlesticks on a black/cyan canvas with the AMT-style
 * indicator strip (VWAP, POC, PVG, IB, LIQ), live crosshair, and
 * volume histogram. Style is tightly coupled to the AMT Scalper look
 * shown in the reference screenshots (cyan accent on near-black).
 *
 * No external charting libs — pure Canvas 2D for performance.
 */

import * as React from 'react'
import type { Candle } from '@/types/trading'
import { cn, formatIN, pnlColor } from '@/lib/utils'

interface AMTChartProps {
  candles: Candle[]
  height?: number
  livePrice?: number
  symbol?: string
  className?: string
  /** show indicator strip (VWAP, POC, PVG, IB, LIQ) */
  showIndicators?: boolean
  /** render volume histogram below candles */
  showVolume?: boolean
  /** render delta/footprint histogram (right-side mini bars) */
  showDelta?: boolean
}

const AMT_COLORS = {
  bg: '#000000',
  panel: '#0a0a0a',
  grid: 'rgba(34, 211, 238, 0.08)',
  axis: '#3a3a3a',
  text: '#9ca3af',
  textDim: '#4a4a4a',
  cyan: '#22D3EE',
  cyanGlow: 'rgba(34, 211, 238, 0.25)',
  bull: '#16a34a',
  bear: '#dc2626',
  vwap: '#f59e0b',
  poc: '#a855f7',
  pvg: '#22D3EE',
  ib: '#ec4899',
  liq: '#eab308',
}

export function AMTChart({
  candles,
  height = 360,
  livePrice,
  symbol = 'NIFTY',
  className,
  showIndicators = true,
  showVolume = true,
  showDelta = true,
}: AMTChartProps) {
  const containerRef = React.useRef<HTMLDivElement>(null)
  const canvasRef = React.useRef<HTMLCanvasElement>(null)
  const [size, setSize] = React.useState({ w: 600, h: height })
  const [hover, setHover] = React.useState<{ x: number; y: number; idx: number } | null>(null)

  React.useEffect(() => {
    if (!containerRef.current) return
    const ro = new ResizeObserver(() => {
      const r = containerRef.current!.getBoundingClientRect()
      setSize({ w: r.width, h: height })
    })
    ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [height])

  // Compute indicators
  const indicators = React.useMemo(() => {
    if (!candles.length) return null
    const vwap: number[] = []
    const ib: number[] = []
    const pvg: number[] = []
    const poc: number[] = []
    const liq: number[] = []
    let cumPV = 0
    let cumV = 0
    // IB (first 6 bars = 30 min)
    const ibCandles = candles.slice(0, Math.min(6, candles.length))
    const ibH = Math.max(...ibCandles.map((c) => c.high))
    const ibL = Math.min(...ibCandles.map((c) => c.low))
    const ibM = (ibH + ibL) / 2
    // POC (price with max volume)
    const volMap = new Map<number, number>()
    for (const c of candles) {
      const p = Math.round(c.close / 0.5) * 0.5
      volMap.set(p, (volMap.get(p) || 0) + c.volume)
    }
    let pocPrice = 0
    let maxV = 0
    for (const [p, v] of volMap) {
      if (v > maxV) {
        maxV = v
        pocPrice = p
      }
    }
    for (const c of candles) {
      const typical = (c.high + c.low + c.close) / 3
      cumPV += typical * c.volume
      cumV += c.volume
      vwap.push(cumPV / cumV)
      // IB extends horizontally from the start
      ib.push(ibM)
      pvg.push(typical) // Poor man's PVG = rolling typical
      poc.push(pocPrice)
      // Liquidity zones (mock: wick extremes of recent bars)
      const recent = candles.slice(Math.max(0, candles.indexOf(c) - 5), candles.indexOf(c) + 1)
      const recentH = recent.length ? Math.max(...recent.map((r) => r.high)) : c.high
      const recentL = recent.length ? Math.min(...recent.map((r) => r.low)) : c.low
      liq.push(Math.random() > 0.5 ? recentH : recentL)
    }
    return { vwap, ib, pvg, poc, liq, ibH, ibL, ibM }
  }, [candles])

  // Draw
  React.useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || candles.length === 0) return
    const dpr = window.devicePixelRatio || 1
    canvas.width = size.w * dpr
    canvas.height = size.h * dpr
    canvas.style.width = `${size.w}px`
    canvas.style.height = `${size.h}px`
    const ctx = canvas.getContext('2d')!
    ctx.scale(dpr, dpr)
    ctx.fillStyle = AMT_COLORS.bg
    ctx.fillRect(0, 0, size.w, size.h)

    const padding = { left: 12, right: 70, top: 20, bottom: 28 }
    const innerW = size.w - padding.left - padding.right
    const volH = showVolume ? 50 : 0
    const deltaW = showDelta ? 60 : 0
    const mainH = size.h - padding.top - padding.bottom - volH - 4
    const mainPlotW = innerW - deltaW

    const barW = mainPlotW / candles.length
    const candleW = Math.max(1, barW * 0.7)

    const allHigh = Math.max(...candles.map((c) => c.high), livePrice ?? -Infinity)
    const allLow = Math.min(...candles.map((c) => c.low), livePrice ?? Infinity)
    const range = allHigh - allLow || 1
    const yScale = (p: number) => padding.top + ((allHigh - p) / range) * mainH

    // Grid
    ctx.strokeStyle = AMT_COLORS.grid
    ctx.lineWidth = 1
    ctx.font = '9px "JetBrains Mono", monospace'
    ctx.fillStyle = AMT_COLORS.text
    ctx.textAlign = 'left'
    ctx.textBaseline = 'middle'
    const ticks = 8
    for (let i = 0; i <= ticks; i++) {
      const y = padding.top + (mainH / ticks) * i
      ctx.beginPath()
      ctx.moveTo(padding.left, y)
      ctx.lineTo(padding.left + mainPlotW, y)
      ctx.stroke()
      const v = allHigh - (range / ticks) * i
      ctx.fillText(v.toFixed(2), padding.left + mainPlotW + 4, y)
    }

    // Time axis (X)
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.fillStyle = AMT_COLORS.textDim
    const xTicks = 6
    for (let i = 0; i <= xTicks; i++) {
      const idx = Math.floor((candles.length - 1) * (i / xTicks))
      const c = candles[idx]
      const x = padding.left + idx * barW + barW / 2
      const d = new Date(c.timestamp)
      const t = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
      ctx.fillText(t, x, size.h - 16)
    }

    // Indicators (lines on main pane)
    if (showIndicators && indicators) {
      const drawLine = (data: number[], color: string, lw = 1, dashed = false) => {
        ctx.beginPath()
        ctx.strokeStyle = color
        ctx.lineWidth = lw
        if (dashed) ctx.setLineDash([4, 3])
        else ctx.setLineDash([])
        for (let i = 0; i < data.length; i++) {
          if (isNaN(data[i])) continue
          const x = padding.left + i * barW + barW / 2
          const y = yScale(data[i])
          if (i === 0) ctx.moveTo(x, y)
          else ctx.lineTo(x, y)
        }
        ctx.stroke()
        ctx.setLineDash([])
      }
      drawLine(indicators.vwap, AMT_COLORS.vwap, 1.5)
      drawLine(indicators.ib, AMT_COLORS.ib, 1, true)
      drawLine(indicators.pvg, AMT_COLORS.pvg, 1, true)
      drawLine(indicators.poc, AMT_COLORS.poc, 1.5)
      drawLine(indicators.liq, AMT_COLORS.liq, 0.8, true)
    }

    // Candles
    candles.forEach((c, i) => {
      const x = padding.left + i * barW + (barW - candleW) / 2
      const isUp = c.close >= c.open
      const color = isUp ? AMT_COLORS.bull : AMT_COLORS.bear
      ctx.strokeStyle = color
      ctx.fillStyle = color
      ctx.lineWidth = 1
      // Wick
      ctx.beginPath()
      ctx.moveTo(x + candleW / 2, yScale(c.high))
      ctx.lineTo(x + candleW / 2, yScale(c.low))
      ctx.stroke()
      // Body
      const y1 = yScale(c.open)
      const y2 = yScale(c.close)
      const bodyTop = Math.min(y1, y2)
      const bodyH = Math.max(1, Math.abs(y2 - y1))
      if (isUp) {
        ctx.fillRect(x, bodyTop, candleW, bodyH)
      } else {
        ctx.fillRect(x, bodyTop, candleW, bodyH)
      }
    })

    // Live price line
    if (livePrice) {
      const y = yScale(livePrice)
      ctx.strokeStyle = AMT_COLORS.cyan
      ctx.lineWidth = 1
      ctx.setLineDash([4, 4])
      ctx.beginPath()
      ctx.moveTo(padding.left, y)
      ctx.lineTo(padding.left + mainPlotW, y)
      ctx.stroke()
      ctx.setLineDash([])
      // Price tag
      ctx.fillStyle = AMT_COLORS.cyan
      ctx.fillRect(padding.left + mainPlotW + 1, y - 8, 64, 16)
      ctx.fillStyle = '#000'
      ctx.font = 'bold 10px "JetBrains Mono", monospace'
      ctx.textAlign = 'left'
      ctx.textBaseline = 'middle'
      ctx.fillText(formatIN(livePrice), padding.left + mainPlotW + 4, y)
    }

    // Volume histogram
    if (showVolume) {
      const volY0 = padding.top + mainH + 4
      const maxVol = Math.max(...candles.map((c) => c.volume), 1)
      const volBarH = volH - 4
      candles.forEach((c, i) => {
        const x = padding.left + i * barW + (barW - candleW) / 2
        const isUp = c.close >= c.open
        const h = (c.volume / maxVol) * volBarH
        ctx.fillStyle = isUp ? 'rgba(22, 163, 74, 0.5)' : 'rgba(220, 38, 38, 0.5)'
        ctx.fillRect(x, volY0 + (volBarH - h), candleW, h)
      })
      // Volume label
      ctx.fillStyle = AMT_COLORS.textDim
      ctx.font = '9px "JetBrains Mono", monospace'
      ctx.textAlign = 'left'
      ctx.textBaseline = 'top'
      ctx.fillText('VOL', padding.left, volY0 + 2)
    }

    // Delta/footprint histogram (right rail)
    if (showDelta) {
      const dx0 = padding.left + mainPlotW + 2
      candles.forEach((c, i) => {
        const x = padding.left + i * barW + (barW - candleW) / 2
        const delta = c.close - c.open
        const barH = Math.max(2, Math.abs(delta) * 100)
        ctx.fillStyle = delta >= 0 ? 'rgba(22, 163, 74, 0.4)' : 'rgba(220, 38, 38, 0.4)'
        const by = padding.top + mainH - (delta > 0 ? barH : 0)
        ctx.fillRect(x, by, candleW, barH)
      })
    }

    // Crosshair
    if (hover && hover.idx >= 0 && hover.idx < candles.length) {
      const c = candles[hover.idx]
      const x = padding.left + hover.idx * barW + barW / 2
      ctx.strokeStyle = AMT_COLORS.cyan
      ctx.setLineDash([2, 2])
      ctx.lineWidth = 0.5
      ctx.beginPath()
      ctx.moveTo(x, padding.top)
      ctx.lineTo(x, padding.top + mainH)
      ctx.stroke()
      ctx.beginPath()
      ctx.moveTo(padding.left, hover.y)
      ctx.lineTo(padding.left + mainPlotW, hover.y)
      ctx.stroke()
      ctx.setLineDash([])
      // OHLC tag
      const txt = `O ${formatIN(c.open)}  H ${formatIN(c.high)}  L ${formatIN(c.low)}  C ${formatIN(c.close)}  V ${c.volume.toLocaleString()}`
      ctx.fillStyle = AMT_COLORS.cyan
      ctx.fillRect(padding.left, padding.top - 14, ctx.measureText(txt).width + 12, 12)
      ctx.fillStyle = '#000'
      ctx.font = '9px "JetBrains Mono", monospace'
      ctx.textAlign = 'left'
      ctx.textBaseline = 'middle'
      ctx.fillText(txt, padding.left + 6, padding.top - 8)
    }
  }, [candles, size, livePrice, hover, indicators, showIndicators, showVolume, showDelta])

  const onMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    const padding = { left: 12, right: 70, top: 20, bottom: 28 }
    const innerW = size.w - padding.left - padding.right
    const showDelta = true
    const deltaW = showDelta ? 60 : 0
    const mainPlotW = innerW - deltaW
    const barW = mainPlotW / candles.length
    const idx = Math.floor((x - padding.left) / barW)
    if (idx >= 0 && idx < candles.length) setHover({ x, y, idx })
  }

  return (
    <div
      ref={containerRef}
      className={cn(
        'relative w-full bg-black border border-cyan-500/20 rounded',
        className,
      )}
      style={{ height }}
    >
      {/* Top indicator strip */}
      {showIndicators && (
        <div className="absolute top-1 left-2 right-2 flex items-center gap-3 z-10 text-[9px] font-mono pointer-events-none">
          {indicators && (
            <>
              <span className="flex items-center gap-1">
                <span className="h-1 w-2 rounded-sm" style={{ background: AMT_COLORS.vwap }} />
                <span style={{ color: AMT_COLORS.vwap }}>VWAP {formatIN(indicators.vwap[indicators.vwap.length - 1])}</span>
              </span>
              <span className="flex items-center gap-1">
                <span className="h-1 w-2 rounded-sm" style={{ background: AMT_COLORS.poc }} />
                <span style={{ color: AMT_COLORS.poc }}>POC {formatIN(indicators.poc[indicators.poc.length - 1])}</span>
              </span>
              <span className="flex items-center gap-1">
                <span className="h-1 w-2 rounded-sm" style={{ background: AMT_COLORS.pvg }} />
                <span style={{ color: AMT_COLORS.pvg }}>PVG {formatIN(indicators.pvg[indicators.pvg.length - 1])}</span>
              </span>
              <span className="flex items-center gap-1">
                <span className="h-1 w-2 rounded-sm" style={{ background: AMT_COLORS.ib }} />
                <span style={{ color: AMT_COLORS.ib }}>IB {formatIN(indicators.ibM)} ({formatIN(indicators.ibL)}-{formatIN(indicators.ibH)})</span>
              </span>
              <span className="flex items-center gap-1">
                <span className="h-1 w-2 rounded-sm" style={{ background: AMT_COLORS.liq }} />
                <span style={{ color: AMT_COLORS.liq }}>LIQ</span>
              </span>
            </>
          )}
        </div>
      )}
      <canvas
        ref={canvasRef}
        onMouseMove={onMouseMove}
        onMouseLeave={() => setHover(null)}
        className="absolute inset-0 cursor-crosshair"
      />
      {/* Symbol badge */}
      <div className="absolute top-1 right-2 px-1.5 py-0.5 bg-cyan-500/20 border border-cyan-500/40 rounded text-[10px] font-mono font-bold text-cyan-400 pointer-events-none">
        {symbol}
      </div>
    </div>
  )
}
