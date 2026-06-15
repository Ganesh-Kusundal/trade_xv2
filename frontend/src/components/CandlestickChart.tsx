/**
 * CandlestickChart — a fast, canvas-based OHLCV chart with:
 *   - Candles coloured by direction
 *   - Volume sub-pane
 *   - Crosshair + price/time axis
 *   - Auto-fit price range
 *   - Optional EMA / SMA overlays
 *
 * Single HTML5 canvas, no external charting library.
 */

import { useEffect, useRef, useState, useMemo } from 'react'
import type { Candle, Timeframe } from '@/types'
import { formatIN, formatDateShort, formatTime, formatCompact } from '@/lib/utils'

interface CandlestickChartProps {
  candles: Candle[]
  symbol: string
  timeframe: Timeframe
  /** Optional progressive reveal (replay): number of bars to show. */
  visibleCount?: number
  height?: number
  showVolume?: boolean
  showMA?: boolean
  /** For live ticking — animate last candle. */
  liveLtp?: number
}

const PAD = { top: 12, right: 64, bottom: 24, left: 8 }

export function CandlestickChart({
  candles,
  symbol,
  timeframe,
  visibleCount,
  height = 480,
  showVolume = true,
  showMA = true,
  liveLtp,
}: CandlestickChartProps) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [w, setW] = useState(800)
  const [hover, setHover] = useState<{ x: number; y: number; idx: number } | null>(null)

  const data = useMemo(() => {
    const arr = visibleCount ? candles.slice(0, visibleCount) : candles
    return arr
  }, [candles, visibleCount])

  // Resize observer
  useEffect(() => {
    if (!wrapRef.current) return
    const ro = new ResizeObserver(([entry]) => {
      setW(Math.max(200, Math.floor(entry.contentRect.width)))
    })
    ro.observe(wrapRef.current)
    return () => ro.disconnect()
  }, [])

  // Compute indicators.
  const mas = useMemo(() => {
    if (!showMA) return { ma9: [], ma20: [], ma50: [] }
    const closes = data.map((c) => c.c)
    return {
      ma9: ema(closes, 9),
      ma20: ema(closes, 20),
      ma50: ema(closes, 50),
    }
  }, [data, showMA])

  // Draw
  useEffect(() => {
    const cv = canvasRef.current
    if (!cv) return
    const dpr = window.devicePixelRatio || 1
    cv.width = w * dpr
    cv.height = height * dpr
    cv.style.width = w + 'px'
    cv.style.height = height + 'px'
    const ctx = cv.getContext('2d')!
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    draw(ctx, w, height, data, mas, hover, liveLtp, showVolume, showMA)
  }, [w, height, data, mas, hover, liveLtp])

  const onMove = (e: React.MouseEvent) => {
    const cv = canvasRef.current
    if (!cv || data.length === 0) return
    const rect = cv.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    const idx = xToIndex(x, w, data.length)
    setHover({ x, y, idx })
  }
  const onLeave = () => setHover(null)

  const last = data[data.length - 1]
  const lastLive = liveLtp ?? last?.c

  return (
    <div ref={wrapRef} className="relative w-full h-full select-none">
      <canvas
        ref={canvasRef}
        onMouseMove={onMove}
        onMouseLeave={onLeave}
        className="block w-full"
        style={{ height }}
      />
      {/* HUD overlay */}
      <div className="absolute top-1.5 left-2 text-2xs font-mono num text-bfgm pointer-events-none">
        <span className="text-bfg font-semibold">{symbol}</span>
        <span className="ml-2 text-bfgd">{timeframeLabel(timeframe)}</span>
        {last && (
          <span className="ml-3">
            O <span className="text-bfg">{formatIN(last.o)}</span>{' '}
            H <span className="text-bull">{formatIN(last.h)}</span>{' '}
            L <span className="text-bear">{formatIN(last.l)}</span>{' '}
            C{' '}
            <span className={last.c >= last.o ? 'text-bull' : 'text-bear'}>
              {formatIN(last.c)}
            </span>
            {lastLive && Math.abs(lastLive - last.c) > 0.005 && (
              <span className="ml-2 text-bcy">LTP {formatIN(lastLive)}</span>
            )}
          </span>
        )}
      </div>
      {hover && data[hover.idx] && (
        <div
          className="absolute top-1.5 right-2 px-2 py-1 b-panel rounded text-2xs font-mono num pointer-events-none"
          style={{ background: 'rgb(var(--bbg-1) / 0.92)' }}
        >
          <div className="text-bfgm">{formatDateShort(data[hover.idx].t)} {formatTime(data[hover.idx].t)}</div>
          <div className="flex gap-3">
            <span>O <span className="text-bfg">{formatIN(data[hover.idx].o)}</span></span>
            <span>H <span className="text-bull">{formatIN(data[hover.idx].h)}</span></span>
            <span>L <span className="text-bear">{formatIN(data[hover.idx].l)}</span></span>
            <span>C <span className={data[hover.idx].c >= data[hover.idx].o ? 'text-bull' : 'text-bear'}>{formatIN(data[hover.idx].c)}</span></span>
            <span className="text-bfgd">V {formatCompact(data[hover.idx].v)}</span>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Drawing helpers ───────────────────────────────────────────────────

function xToIndex(x: number, w: number, n: number): number {
  if (n === 0) return 0
  const plotW = w - PAD.left - PAD.right
  if (plotW <= 0) return 0
  const slot = plotW / n
  const i = Math.floor((x - PAD.left) / slot)
  return Math.max(0, Math.min(n - 1, i))
}

function timeframeLabel(tf: Timeframe): string {
  return tf.toUpperCase()
}

function ema(values: number[], period: number): number[] {
  const out: number[] = []
  if (values.length === 0) return out
  const k = 2 / (period + 1)
  let prev = values[0]
  out.push(prev)
  for (let i = 1; i < values.length; i++) {
    prev = values[i] * k + prev * (1 - k)
    out.push(prev)
  }
  return out
}

function draw(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  data: Candle[],
  mas: { ma9: number[]; ma20: number[]; ma50: number[] },
  hover: { x: number; y: number; idx: number } | null,
  liveLtp: number | undefined,
  showVolume: boolean,
  showMA: boolean,
) {
  ctx.clearRect(0, 0, w, h)

  // Background
  ctx.fillStyle = 'rgb(13, 16, 22)'
  ctx.fillRect(0, 0, w, h)

  if (data.length === 0) {
    ctx.fillStyle = 'rgb(102, 115, 140)'
    ctx.font = '12px JetBrains Mono, monospace'
    ctx.textAlign = 'center'
    ctx.fillText('Loading…', w / 2, h / 2)
    return
  }

  const volH = Math.floor((h - PAD.top - PAD.bottom) * 0.18)
  const priceH = h - PAD.top - PAD.bottom - (showVolume ? volH + 8 : 0)
  const plotL = PAD.left
  const plotR = w - PAD.right
  const plotT = PAD.top
  const plotB = PAD.top + priceH
  const plotW = plotR - plotL

  const n = data.length
  const slot = plotW / n
  const cw = Math.max(1, Math.floor(slot * 0.65))

  // Y range (price)
  let lo = Infinity, hi = -Infinity
  for (const c of data) { if (c.l < lo) lo = c.l; if (c.h > hi) hi = c.h }
  if (liveLtp && Math.abs(liveLtp - data[data.length - 1].c) > 0.005) {
    if (liveLtp < lo) lo = liveLtp
    if (liveLtp > hi) hi = liveLtp
  }
  const pad = (hi - lo) * 0.08 || 1
  lo -= pad
  hi += pad
  const yScale = (p: number) => plotB - ((p - lo) / (hi - lo)) * priceH

  // Grid (horizontal)
  ctx.strokeStyle = 'rgb(34, 42, 56)'
  ctx.lineWidth = 1
  ctx.font = '10px JetBrains Mono, monospace'
  ctx.fillStyle = 'rgb(102, 115, 140)'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  const gridLines = 6
  for (let i = 0; i <= gridLines; i++) {
    const y = plotT + (i / gridLines) * priceH
    const p = hi - (i / gridLines) * (hi - lo)
    ctx.beginPath()
    ctx.moveTo(plotL, y)
    ctx.lineTo(plotR, y)
    ctx.stroke()
    ctx.fillText(formatIN(p), plotR + 4, y)
  }

  // Grid (vertical) — sparse
  const vLines = 6
  for (let i = 0; i <= vLines; i++) {
    const x = plotL + (i / vLines) * plotW
    ctx.beginPath()
    ctx.strokeStyle = 'rgb(24, 31, 48)'
    ctx.moveTo(x, plotT)
    ctx.lineTo(x, plotB)
    ctx.stroke()
  }

  // Candles
  for (let i = 0; i < n; i++) {
    const c = data[i]
    const x = plotL + i * slot + slot / 2
    const yo = yScale(c.o)
    const yc = yScale(c.c)
    const yh = yScale(c.h)
    const yl = yScale(c.l)
    const up = c.c >= c.o
    ctx.strokeStyle = up ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)'
    ctx.fillStyle   = up ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)'
    // Wick
    ctx.beginPath()
    ctx.moveTo(x, yh)
    ctx.lineTo(x, yl)
    ctx.stroke()
    // Body
    const top = Math.min(yo, yc)
    const bh = Math.max(1, Math.abs(yc - yo))
    ctx.fillRect(x - cw / 2, top, cw, bh)
  }
  if (showMA && mas.ma9.length) {
    drawLine(ctx, mas.ma9, slot, plotL, yScale, 'rgb(34, 211, 238)', 1)   // cyan
    drawLine(ctx, mas.ma20, slot, plotL, yScale, 'rgb(255, 168, 38)', 1)  // amber
    drawLine(ctx, mas.ma50, slot, plotL, yScale, 'rgb(217, 70, 239)', 1)  // magenta
  }

  // Volume sub-pane
  if (showVolume) {
    const vt = plotB + 8
    const vb = h - PAD.bottom
    let maxV = 0
    for (const c of data) if (c.v > maxV) maxV = c.v
    for (let i = 0; i < n; i++) {
      const c = data[i]
      const x = plotL + i * slot + slot / 2
      const bh = Math.max(1, (c.v / maxV) * (vb - vt - 2))
      const up = c.c >= c.o
      ctx.fillStyle = up ? 'rgba(34,197,94,0.55)' : 'rgba(239,68,68,0.55)'
      ctx.fillRect(x - cw / 2, vb - bh, cw, bh)
    }
    // Volume axis label
    ctx.fillStyle = 'rgb(102, 115, 140)'
    ctx.textAlign = 'left'
    ctx.font = '9px JetBrains Mono, monospace'
    ctx.fillText('VOL', plotL + 2, vt + 8)
  }

  // X-axis time labels
  ctx.fillStyle = 'rgb(102, 115, 140)'
  ctx.font = '9px JetBrains Mono, monospace'
  ctx.textAlign = 'center'
  const xLines = 5
  for (let i = 0; i <= xLines; i++) {
    const x = plotL + (i / xLines) * plotW
    const idx = Math.min(n - 1, Math.floor((i / xLines) * n))
    const c = data[idx]
    if (!c) continue
    const label = i === 0 || i === xLines
      ? formatDateShort(c.t)
      : formatTime(c.t, false)
    ctx.fillText(label, x, h - 6)
  }

  // Last-price tag
  if (liveLtp && Math.abs(liveLtp - data[data.length - 1].c) > 0.005) {
    const y = yScale(liveLtp)
    ctx.strokeStyle = 'rgb(34, 211, 238)'
    ctx.setLineDash([3, 3])
    ctx.beginPath()
    ctx.moveTo(plotL, y)
    ctx.lineTo(plotR, y)
    ctx.stroke()
    ctx.setLineDash([])
    ctx.fillStyle = 'rgb(34, 211, 238)'
    ctx.fillRect(plotR, y - 8, PAD.right - 2, 16)
    ctx.fillStyle = 'rgb(8, 10, 14)'
    ctx.textAlign = 'left'
    ctx.textBaseline = 'middle'
    ctx.font = '10px JetBrains Mono, monospace'
    ctx.fillText(formatIN(liveLtp), plotR + 4, y)
  }

  // Crosshair
  if (hover) {
    const x = plotL + hover.idx * slot + slot / 2
    ctx.strokeStyle = 'rgb(102, 115, 140)'
    ctx.setLineDash([2, 3])
    ctx.beginPath()
    ctx.moveTo(x, plotT)
    ctx.lineTo(x, h - PAD.bottom)
    ctx.stroke()
    ctx.beginPath()
    ctx.moveTo(plotL, hover.y)
    ctx.lineTo(plotR, hover.y)
    ctx.stroke()
    ctx.setLineDash([])
  }
}

function drawLine(
  ctx: CanvasRenderingContext2D,
  values: number[],
  slot: number,
  plotL: number,
  yScale: (p: number) => number,
  color: string,
  width: number,
) {
  if (values.length < 2) return
  ctx.strokeStyle = color
  ctx.lineWidth = width
  ctx.beginPath()
  for (let i = 0; i < values.length; i++) {
    const x = plotL + i * slot + slot / 2
    const y = yScale(values[i])
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  }
  ctx.stroke()
}
