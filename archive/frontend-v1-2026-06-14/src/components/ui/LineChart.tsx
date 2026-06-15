/**
 * Generic line/area chart for equity curves, indicators, distribution etc.
 */

import * as React from 'react'
import { cn, pnlColor } from '@/lib/utils'

export interface LinePoint {
  x: number           /* timestamp or numeric x */
  y: number
}

interface LineChartProps {
  data: LinePoint[]
  height?: number
  width?: number
  className?: string
  color?: 'auto' | 'brand' | 'bull' | 'bear'
  fill?: boolean
  showGrid?: boolean
  showAxis?: boolean
  benchmark?: LinePoint[]
  benchmarkColor?: string
  zeroLine?: boolean
  area?: boolean
  yLabel?: (v: number) => string
  xLabel?: (v: number) => string
}

export function LineChart({
  data,
  height = 200,
  width = 600,
  className,
  color = 'auto',
  fill = true,
  showGrid = true,
  showAxis = true,
  benchmark,
  benchmarkColor = 'rgb(99 110 140)',
  zeroLine,
  area = true,
  yLabel = (v) => v.toFixed(2),
  xLabel = (v) => new Date(v).toLocaleDateString(),
}: LineChartProps) {
  const ref = React.useRef<HTMLDivElement>(null)
  const canvasRef = React.useRef<HTMLCanvasElement>(null)
  const [size, setSize] = React.useState({ w: width, h: height })

  React.useEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(() => {
      const r = ref.current!.getBoundingClientRect()
      setSize({ w: r.width, h: height })
    })
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [height])

  React.useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || data.length < 2) return
    const dpr = window.devicePixelRatio || 1
    canvas.width = size.w * dpr
    canvas.height = size.h * dpr
    canvas.style.width = `${size.w}px`
    canvas.style.height = `${size.h}px`
    const ctx = canvas.getContext('2d')!
    ctx.scale(dpr, dpr)
    ctx.clearRect(0, 0, size.w, size.h)

    const pad = { l: 12, r: 12, t: 12, b: 18 }
    const plotW = size.w - pad.l - pad.r
    const plotH = size.h - pad.t - pad.b

    const all = benchmark ? [...data, ...benchmark] : data
    const ys = all.map((d) => d.y)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)
    const range = maxY - minY || 1
    const xs = data.map((d) => d.x)
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const xRange = maxX - minX || 1
    const xScale = (x: number) => pad.l + ((x - minX) / xRange) * plotW
    const yScale = (y: number) => pad.t + plotH - ((y - minY) / range) * plotH

    // Grid
    if (showGrid) {
      ctx.strokeStyle = 'rgb(33 41 62 / 0.4)'
      ctx.lineWidth = 1
      const ticks = 4
      ctx.font = '9px Inter'
      ctx.fillStyle = 'rgb(102 115 140)'
      for (let i = 0; i <= ticks; i++) {
        const y = pad.t + (plotH / ticks) * i
        ctx.beginPath()
        ctx.moveTo(pad.l, y)
        ctx.lineTo(pad.l + plotW, y)
        ctx.stroke()
        if (showAxis) {
          const v = maxY - (range / ticks) * i
          ctx.textAlign = 'left'
          ctx.textBaseline = 'middle'
          ctx.fillText(yLabel(v), pad.l + 4, y)
        }
      }
      // X axis labels
      if (showAxis) {
        const xTicks = 4
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        for (let i = 0; i <= xTicks; i++) {
          const x = pad.l + (plotW / xTicks) * i
          const v = minX + (xRange / xTicks) * i
          ctx.fillText(xLabel(v).slice(0, 8), x, pad.t + plotH + 4)
        }
      }
    }

    // Zero line
    if (zeroLine && minY < 0 && maxY > 0) {
      const y = yScale(0)
      ctx.strokeStyle = 'rgb(99 110 140 / 0.5)'
      ctx.lineWidth = 1
      ctx.setLineDash([3, 3])
      ctx.beginPath()
      ctx.moveTo(pad.l, y)
      ctx.lineTo(pad.l + plotW, y)
      ctx.stroke()
      ctx.setLineDash([])
    }

    // Benchmark
    if (benchmark && benchmark.length > 1) {
      ctx.beginPath()
      ctx.strokeStyle = benchmarkColor
      ctx.lineWidth = 1
      ctx.setLineDash([3, 3])
      benchmark.forEach((p, i) => {
        const x = xScale(p.x)
        const y = yScale(p.y)
        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      })
      ctx.stroke()
      ctx.setLineDash([])
    }

    // Trend
    const trendUp = data[data.length - 1].y >= data[0].y
    const stroke = color === 'brand' ? '#3b82f6' : color === 'bull' ? '#16a34a' : color === 'bear' ? '#dc2626' : trendUp ? '#16a34a' : '#dc2626'
    const fillC = trendUp ? 'rgb(22 163 74 / 0.12)' : 'rgb(220 38 38 / 0.12)'

    // Area
    if (area && fill) {
      ctx.beginPath()
      data.forEach((p, i) => {
        const x = xScale(p.x)
        const y = yScale(p.y)
        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      })
      ctx.lineTo(xScale(data[data.length - 1].x), pad.t + plotH)
      ctx.lineTo(xScale(data[0].x), pad.t + plotH)
      ctx.closePath()
      ctx.fillStyle = fillC
      ctx.fill()
    }

    // Line
    ctx.beginPath()
    ctx.strokeStyle = stroke
    ctx.lineWidth = 1.5
    data.forEach((p, i) => {
      const x = xScale(p.x)
      const y = yScale(p.y)
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.stroke()
  }, [data, size, color, fill, showGrid, showAxis, benchmark, benchmarkColor, zeroLine, area, yLabel, xLabel])

  return (
    <div ref={ref} className={cn('relative w-full', className)} style={{ height }}>
      <canvas ref={canvasRef} className="block" />
    </div>
  )
}
