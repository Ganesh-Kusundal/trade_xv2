/**
 * Lightweight canvas-based candlestick chart.
 * Designed for quant use: dense, fast, supports indicators, crosshair, zoom.
 * No external dependencies (no Chart.js / Recharts) — fully owned.
 */

import * as React from 'react'
import type { Candle } from '@/types/trading'
import { cn, pnlColor } from '@/lib/utils'

export interface IndicatorOverlay {
  name: string
  type: 'line' | 'histogram' | 'band'
  data: number[]             /* aligned with candles */
  color: string
  secondary?: number[]       /* for band/area fills */
  secondaryColor?: string
  lineWidth?: number
  opacity?: number
  paneIndex?: number         /* 0 = main, 1+ = sub-panes */
}

export interface ChartMarker {
  timestamp: number
  price: number
  type: 'BUY' | 'SELL' | 'INFO' | 'WARN' | 'EXIT'
  label?: string
  text?: string
}

export interface VolumeProfileBin {
  price: number
  volume: number
  isPOC?: boolean
  isValueArea?: boolean
}

interface CandlestickChartProps {
  candles: Candle[]
  height?: number
  showVolume?: boolean
  showGrid?: boolean
  indicators?: IndicatorOverlay[]
  markers?: ChartMarker[]
  volumeProfile?: VolumeProfileBin[]
  crosshair?: boolean
  livePrice?: number
  className?: string
  onCrosshairMove?: (idx: number | null, candle: Candle | null) => void
}

const FONT = '11px "JetBrains Mono", ui-monospace, monospace'
const AXIS_FONT = '10px "Inter", sans-serif'

export function CandlestickChart({
  candles,
  height = 360,
  showVolume = true,
  showGrid = true,
  indicators = [],
  markers = [],
  volumeProfile,
  crosshair = true,
  livePrice,
  className,
  onCrosshairMove,
}: CandlestickChartProps) {
  const containerRef = React.useRef<HTMLDivElement>(null)
  const canvasRef = React.useRef<HTMLCanvasElement>(null)
  const [size, setSize] = React.useState({ w: 600, h: height })
  const [hover, setHover] = React.useState<{ x: number; y: number; idx: number } | null>(null)

  // Resize observer
  React.useEffect(() => {
    if (!containerRef.current) return
    const ro = new ResizeObserver(() => {
      const r = containerRef.current!.getBoundingClientRect()
      setSize({ w: r.width, h: height })
    })
    ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [height])

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
    ctx.clearRect(0, 0, size.w, size.h)

    const padding = { left: 8, right: 64, top: 12, bottom: showVolume ? 80 : 28 }
    const mainH = size.h - padding.top - padding.bottom
    const volH = showVolume ? padding.bottom - 24 : 0
    const mainPlotH = mainH - volH

    const plotW = size.w - padding.left - padding.right
    const barW = Math.max(1, plotW / candles.length)
    const candleW = Math.max(1, barW * 0.7)

    // Find ranges
    const allHigh = Math.max(...candles.map((c) => c.high), livePrice ?? -Infinity)
    const allLow = Math.min(...candles.map((c) => c.low), livePrice ?? Infinity)
    const range = allHigh - allLow || 1
    const yScale = (p: number) => padding.top + ((allHigh - p) / range) * mainPlotH

    // Grid + Y axis
    if (showGrid) {
      ctx.strokeStyle = 'rgb(33 41 62 / 0.4)'
      ctx.lineWidth = 1
      ctx.font = AXIS_FONT
      ctx.fillStyle = 'rgb(102 115 140)'
      ctx.textAlign = 'left'
      ctx.textBaseline = 'middle'
      const ticks = 6
      for (let i = 0; i <= ticks; i++) {
        const y = padding.top + (mainPlotH / ticks) * i
        const v = allHigh - (range / ticks) * i
        ctx.beginPath()
        ctx.moveTo(padding.left, y)
        ctx.lineTo(padding.left + plotW, y)
        ctx.stroke()
        ctx.fillText(v.toFixed(2), padding.left + plotW + 6, y)
      }
    }

    // Volume profile (background)
    if (volumeProfile && volumeProfile.length) {
      const maxVol = Math.max(...volumeProfile.map((b) => b.volume))
      const xStart = padding.left
      const profileW = 50
      ctx.fillStyle = 'rgb(33 41 62 / 0.5)'
      ctx.fillRect(xStart, padding.top, plotW - profileW, mainPlotH)
      volumeProfile.forEach((bin) => {
        const y = yScale(bin.price)
        const w = (bin.volume / maxVol) * (plotW - profileW) * 0.4
        if (bin.isPOC) {
          ctx.fillStyle = 'rgb(245 158 11 / 0.5)'
        } else if (bin.isValueArea) {
          ctx.fillStyle = 'rgb(59 130 246 / 0.3)'
        } else {
          ctx.fillStyle = 'rgb(99 110 140 / 0.25)'
        }
        ctx.fillRect(xStart, y - 1, w, 2)
      })
    }

    // Indicators (lines on main pane)
    indicators
      .filter((ind) => ind.paneIndex === 0)
      .forEach((ind) => {
        if (ind.type === 'band' && ind.secondary) {
          ctx.beginPath()
          ctx.fillStyle = ind.secondaryColor || 'rgb(59 130 246 / 0.1)'
          for (let i = 0; i < ind.data.length; i++) {
            const x = padding.left + i * barW + barW / 2
            const y = yScale(ind.data[i])
            if (i === 0) ctx.moveTo(x, y)
            else ctx.lineTo(x, y)
          }
          for (let i = ind.secondary.length - 1; i >= 0; i--) {
            const x = padding.left + i * barW + barW / 2
            const y = yScale(ind.secondary[i])
            ctx.lineTo(x, y)
          }
          ctx.closePath()
          ctx.fill()
        }
        ctx.beginPath()
        ctx.strokeStyle = ind.color
        ctx.lineWidth = ind.lineWidth || 1.2
        for (let i = 0; i < ind.data.length; i++) {
          if (isNaN(ind.data[i])) continue
          const x = padding.left + i * barW + barW / 2
          const y = yScale(ind.data[i])
          if (i === 0) ctx.moveTo(x, y)
          else ctx.lineTo(x, y)
        }
        ctx.stroke()
      })

    // Candles
    candles.forEach((c, i) => {
      const x = padding.left + i * barW + (barW - candleW) / 2
      const isUp = c.close >= c.open
      const color = isUp ? 'rgb(22 163 74)' : 'rgb(220 38 38)'
      // Wick
      ctx.strokeStyle = color
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(x + candleW / 2, yScale(c.high))
      ctx.lineTo(x + candleW / 2, yScale(c.low))
      ctx.stroke()
      // Body
      const y1 = yScale(c.open)
      const y2 = yScale(c.close)
      const bodyH = Math.max(1, Math.abs(y2 - y1))
      const bodyY = Math.min(y1, y2)
      ctx.fillStyle = color
      if (isUp) {
        ctx.fillRect(x, bodyY, candleW, bodyH)
      } else {
        ctx.fillRect(x, bodyY, candleW, bodyH)
      }
    })

    // Live price line
    if (livePrice != null) {
      const y = yScale(livePrice)
      const isUp = candles[candles.length - 1]?.close <= livePrice
      const color = isUp ? 'rgb(22 163 74)' : 'rgb(220 38 38)'
      ctx.strokeStyle = color
      ctx.lineWidth = 1
      ctx.setLineDash([4, 3])
      ctx.beginPath()
      ctx.moveTo(padding.left, y)
      ctx.lineTo(padding.left + plotW, y)
      ctx.stroke()
      ctx.setLineDash([])
      // Price tag
      ctx.fillStyle = color
      const tag = livePrice.toFixed(2)
      const w = ctx.measureText(tag).width + 8
      ctx.fillRect(padding.left + plotW, y - 8, w, 16)
      ctx.fillStyle = '#fff'
      ctx.font = FONT
      ctx.textBaseline = 'middle'
      ctx.fillText(tag, padding.left + plotW + 4, y)
    }

    // X axis (time)
    ctx.font = AXIS_FONT
    ctx.fillStyle = 'rgb(102 115 140)'
    ctx.textBaseline = 'top'
    ctx.textAlign = 'center'
    const xTicks = 6
    for (let i = 0; i <= xTicks; i++) {
      const idx = Math.floor((candles.length - 1) * (i / xTicks))
      const c = candles[idx]
      if (!c) continue
      const x = padding.left + idx * barW + barW / 2
      const d = new Date(c.timestamp)
      const label = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
      ctx.fillText(label, x, size.h - 14)
    }

    // Volume bars
    if (showVolume) {
      const maxVol = Math.max(...candles.map((c) => c.volume)) || 1
      const volY = padding.top + mainPlotH + 20
      const volPlotH = volH - 20
      candles.forEach((c, i) => {
        const x = padding.left + i * barW + (barW - candleW) / 2
        const h = (c.volume / maxVol) * volPlotH
        const isUp = c.close >= c.open
        ctx.fillStyle = isUp ? 'rgb(22 163 74 / 0.4)' : 'rgb(220 38 38 / 0.4)'
        ctx.fillRect(x, volY + (volPlotH - h), candleW, h)
      })
      // VOL label
      ctx.fillStyle = 'rgb(102 115 140)'
      ctx.font = AXIS_FONT
      ctx.textAlign = 'left'
      ctx.textBaseline = 'top'
      ctx.fillText('VOL', padding.left, padding.top + mainPlotH + 6)
    }

    // Markers (buy/sell signals)
    markers.forEach((m) => {
      const idx = candles.findIndex((c) => c.timestamp >= m.timestamp)
      if (idx === -1) return
      const c = candles[idx]
      const x = padding.left + idx * barW + barW / 2
      const y = m.type === 'BUY' ? yScale(c.low) - 8 : yScale(c.high) + 16
      const color = m.type === 'BUY' ? '#16a34a' : m.type === 'SELL' ? '#dc2626' : m.type === 'EXIT' ? '#f59e0b' : '#3b82f6'
      ctx.fillStyle = color
      ctx.beginPath()
      if (m.type === 'BUY') {
        ctx.moveTo(x, y + 8)
        ctx.lineTo(x - 5, y + 16)
        ctx.lineTo(x + 5, y + 16)
      } else {
        ctx.moveTo(x, y - 8)
        ctx.lineTo(x - 5, y - 16)
        ctx.lineTo(x + 5, y - 16)
      }
      ctx.closePath()
      ctx.fill()
      if (m.text) {
        ctx.font = '9px JetBrains Mono'
        ctx.fillStyle = '#fff'
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.fillText(m.text, x, y + (m.type === 'BUY' ? 22 : -22))
      }
    })

    // Crosshair
    if (crosshair && hover) {
      ctx.strokeStyle = 'rgb(99 115 140 / 0.5)'
      ctx.lineWidth = 1
      ctx.setLineDash([3, 3])
      // Vertical
      ctx.beginPath()
      ctx.moveTo(hover.x, padding.top)
      ctx.lineTo(hover.x, padding.top + mainPlotH)
      ctx.stroke()
      // Horizontal
      ctx.beginPath()
      ctx.moveTo(padding.left, hover.y)
      ctx.lineTo(padding.left + plotW, hover.y)
      ctx.stroke()
      ctx.setLineDash([])

      // Crosshair price tag
      if (hover.y >= padding.top && hover.y <= padding.top + mainPlotH) {
        const v = allHigh - ((hover.y - padding.top) / mainPlotH) * range
        ctx.fillStyle = 'rgb(33 41 62)'
        const tag = v.toFixed(2)
        const w = ctx.measureText(tag).width + 8
        ctx.fillRect(padding.left + plotW, hover.y - 8, w, 16)
        ctx.fillStyle = '#fff'
        ctx.font = FONT
        ctx.textBaseline = 'middle'
        ctx.textAlign = 'left'
        ctx.fillText(tag, padding.left + plotW + 4, hover.y)
      }
    }
  }, [candles, size, indicators, markers, showVolume, showGrid, livePrice, hover, volumeProfile, crosshair])

  const handleMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    const padding = { left: 8, right: 64 }
    const plotW = size.w - padding.left - padding.right
    const barW = plotW / candles.length
    const idx = Math.floor((x - padding.left) / barW)
    if (idx >= 0 && idx < candles.length) {
      setHover({ x, y, idx })
      onCrosshairMove?.(idx, candles[idx])
    } else {
      setHover(null)
      onCrosshairMove?.(null, null)
    }
  }

  return (
    <div ref={containerRef} className={cn('relative w-full', className)} style={{ height }}>
      <canvas
        ref={canvasRef}
        onMouseMove={handleMove}
        onMouseLeave={() => {
          setHover(null)
          onCrosshairMove?.(null, null)
        }}
        className="block"
      />
      {hover && candles[hover.idx] && (
        <div className="absolute top-2 left-2 px-2 py-1 rounded bg-bg-2/95 border border-line text-2xs font-mono num backdrop-blur-sm pointer-events-none">
          <div className="text-fg-muted">{new Date(candles[hover.idx].timestamp).toLocaleString('en-IN')}</div>
          <div className="flex gap-3 mt-0.5">
            <span>O <span className="text-fg">{candles[hover.idx].open.toFixed(2)}</span></span>
            <span>H <span className="text-bullish">{candles[hover.idx].high.toFixed(2)}</span></span>
            <span>L <span className="text-bearish">{candles[hover.idx].low.toFixed(2)}</span></span>
            <span>C <span className="text-fg">{candles[hover.idx].close.toFixed(2)}</span></span>
            <span className="text-fg-dim">V {candles[hover.idx].volume.toLocaleString('en-IN')}</span>
          </div>
        </div>
      )}
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Indicator helpers
// ───────────────────────────────────────────────────────────────────────────

export function calcSMA(data: number[], period: number): number[] {
  const out: number[] = new Array(data.length).fill(NaN)
  let sum = 0
  for (let i = 0; i < data.length; i++) {
    sum += data[i]
    if (i >= period) sum -= data[i - period]
    if (i >= period - 1) out[i] = sum / period
  }
  return out
}

export function calcEMA(data: number[], period: number): number[] {
  const out: number[] = new Array(data.length).fill(NaN)
  const k = 2 / (period + 1)
  let ema = data[0] || 0
  for (let i = 0; i < data.length; i++) {
    ema = i === 0 ? data[i] : data[i] * k + ema * (1 - k)
    if (i >= period - 1) out[i] = ema
  }
  return out
}

export function calcRSI(data: number[], period = 14): number[] {
  const out: number[] = new Array(data.length).fill(NaN)
  let gains = 0
  let losses = 0
  for (let i = 1; i < data.length; i++) {
    const change = data[i] - data[i - 1]
    const gain = Math.max(0, change)
    const loss = Math.max(0, -change)
    if (i <= period) {
      gains += gain
      losses += loss
      if (i === period) {
        const avgG = gains / period
        const avgL = losses / period
        const rs = avgL === 0 ? 100 : avgG / avgL
        out[i] = 100 - 100 / (1 + rs)
      }
    } else {
      gains = (gains * (period - 1) + gain) / period
      losses = (losses * (period - 1) + loss) / period
      const rs = losses === 0 ? 100 : gains / losses
      out[i] = 100 - 100 / (1 + rs)
    }
  }
  return out
}

export function calcBollingerBands(data: number[], period = 20, mult = 2): { upper: number[]; middle: number[]; lower: number[] } {
  const middle = calcSMA(data, period)
  const upper: number[] = new Array(data.length).fill(NaN)
  const lower: number[] = new Array(data.length).fill(NaN)
  for (let i = period - 1; i < data.length; i++) {
    let sum = 0
    for (let j = i - period + 1; j <= i; j++) sum += (data[j] - middle[i]) ** 2
    const std = Math.sqrt(sum / period)
    upper[i] = middle[i] + mult * std
    lower[i] = middle[i] - mult * std
  }
  return { upper, middle, lower }
}

export function calcVWAP(candles: Candle[]): number[] {
  const out: number[] = new Array(candles.length).fill(NaN)
  let cumPV = 0
  let cumV = 0
  for (let i = 0; i < candles.length; i++) {
    const typical = (candles[i].high + candles[i].low + candles[i].close) / 3
    cumPV += typical * candles[i].volume
    cumV += candles[i].volume
    out[i] = cumPV / cumV
  }
  return out
}

export function calcATR(candles: Candle[], period = 14): number[] {
  const out: number[] = new Array(candles.length).fill(NaN)
  const trs: number[] = []
  for (let i = 0; i < candles.length; i++) {
    if (i === 0) {
      trs.push(candles[i].high - candles[i].low)
    } else {
      const tr = Math.max(
        candles[i].high - candles[i].low,
        Math.abs(candles[i].high - candles[i - 1].close),
        Math.abs(candles[i].low - candles[i - 1].close),
      )
      trs.push(tr)
    }
  }
  let atr = 0
  for (let i = 0; i < candles.length; i++) {
    if (i < period - 1) continue
    if (i === period - 1) {
      atr = trs.slice(0, period).reduce((s, t) => s + t, 0) / period
    } else {
      atr = (atr * (period - 1) + trs[i]) / period
    }
    out[i] = atr
  }
  return out
}
