/**
 * AMTVolumeProfile — Canvas-based Volume Profile in the AMT Scalper style.
 *
 * Horizontal histogram (purple POC, cyan VAH/VAL, orange value area fill)
 * with price axis and cumulative volume total.
 */

import * as React from 'react'
import { cn, formatCompact, formatIN } from '@/lib/utils'

interface AMTVolumeProfileProps {
  symbol?: string
  /** pre-binned volume profile data */
  bins: { price: number; volume: number }[]
  poc: number
  vah: number
  val: number
  height?: number
  className?: string
}

const AMT = {
  bg: '#000',
  text: '#9ca3af',
  textDim: '#4a4a4a',
  cyan: '#22D3EE',
  poc: '#a855f7',
  va: 'rgba(168, 85, 247, 0.4)',
  val: 'rgba(168, 85, 247, 0.15)',
}

export function AMTVolumeProfile({
  symbol = 'NIFTY',
  bins,
  poc,
  vah,
  val,
  height = 320,
  className,
}: AMTVolumeProfileProps) {
  const canvasRef = React.useRef<HTMLCanvasElement>(null)
  const containerRef = React.useRef<HTMLDivElement>(null)
  const [size, setSize] = React.useState({ w: 200, h: height })

  React.useEffect(() => {
    if (!containerRef.current) return
    const ro = new ResizeObserver(() => {
      const r = containerRef.current!.getBoundingClientRect()
      setSize({ w: r.width, h: height })
    })
    ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [height])

  React.useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || bins.length === 0) return
    const dpr = window.devicePixelRatio || 1
    canvas.width = size.w * dpr
    canvas.height = size.h * dpr
    canvas.style.width = `${size.w}px`
    canvas.style.height = `${size.h}px`
    const ctx = canvas.getContext('2d')!
    ctx.scale(dpr, dpr)
    ctx.fillStyle = AMT.bg
    ctx.fillRect(0, 0, size.w, size.h)

    const padding = { left: 6, right: 50, top: 12, bottom: 16 }
    const plotW = size.w - padding.left - padding.right
    const plotH = size.h - padding.top - padding.bottom
    const maxVol = Math.max(...bins.map((b) => b.volume), 1)
    const minP = Math.min(...bins.map((b) => b.price))
    const maxP = Math.max(...bins.map((b) => b.price))
    const range = maxP - minP || 1
    const yScale = (p: number) => padding.top + ((maxP - p) / range) * plotH

    // Y axis ticks
    ctx.font = '9px "JetBrains Mono", monospace'
    ctx.fillStyle = AMT.text
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'
    const yTicks = 8
    for (let i = 0; i <= yTicks; i++) {
      const y = padding.top + (plotH / yTicks) * i
      const v = maxP - (range / yTicks) * i
      ctx.fillText(formatIN(v, 2), padding.left + plotW + 46, y)
    }

    // Value area (VAH to VAL) shaded region
    const vahY = yScale(vah)
    const valY = yScale(val)
    ctx.fillStyle = AMT.val
    ctx.fillRect(padding.left, Math.min(vahY, valY), plotW, Math.abs(valY - vahY))

    // Volume bars
    bins.forEach((bin) => {
      const y = yScale(bin.price)
      const barH = Math.max(1, plotH / bins.length - 1)
      const w = (bin.volume / maxVol) * plotW
      const inVA = bin.price <= vah && bin.price >= val
      const isPOC = Math.abs(bin.price - poc) < (range / bins.length) / 2
      if (isPOC) {
        ctx.fillStyle = AMT.poc
      } else if (inVA) {
        ctx.fillStyle = AMT.va
      } else {
        ctx.fillStyle = 'rgba(168, 85, 247, 0.2)'
      }
      ctx.fillRect(padding.left, y - barH / 2, w, barH)
    })

    // POC line
    const pocY = yScale(poc)
    ctx.strokeStyle = AMT.cyan
    ctx.lineWidth = 1
    ctx.setLineDash([4, 3])
    ctx.beginPath()
    ctx.moveTo(padding.left, pocY)
    ctx.lineTo(padding.left + plotW, pocY)
    ctx.stroke()
    ctx.setLineDash([])

    // POC label
    ctx.fillStyle = AMT.cyan
    ctx.font = 'bold 9px "JetBrains Mono", monospace'
    ctx.textAlign = 'left'
    ctx.textBaseline = 'middle'
    ctx.fillText(`POC ${formatIN(poc)}`, padding.left + 4, pocY - 1)

    // VAH/VAL labels
    ctx.fillStyle = AMT.poc
    ctx.fillText(`VAH ${formatIN(vah)}`, padding.left + 4, vahY - 1)
    ctx.fillText(`VAL ${formatIN(val)}`, padding.left + 4, valY + 9)

    // POC/VAH/VAL badges
    ctx.fillStyle = AMT.cyan
    ctx.fillRect(padding.left + plotW + 1, pocY - 6, 44, 12)
    ctx.fillStyle = '#000'
    ctx.fillText('POC', padding.left + plotW + 4, pocY)
  }, [bins, poc, vah, val, size])

  const total = bins.reduce((s, b) => s + b.volume, 0)

  return (
    <div ref={containerRef} className={cn('relative w-full bg-black border border-cyan-500/20 rounded', className)} style={{ height }}>
      <div className="absolute top-1 left-2 text-[9px] font-mono uppercase tracking-wider text-cyan-400 pointer-events-none">
        Volume Profile · {symbol}
      </div>
      <div className="absolute top-1 right-2 text-[9px] font-mono text-cyan-400 pointer-events-none">
        Total: {formatCompact(total)}
      </div>
      <canvas ref={canvasRef} className="absolute inset-0" />
    </div>
  )
}
