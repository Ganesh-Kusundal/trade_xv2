/**
 * AMTDeepDOM — Canvas-based Deep Order-of-Market in AMT Scalper style.
 *
 * Bid/ask ladder on the right with green/red gradient bars,
 * price ladder on the left, plus bid/ask totals, last price, and
 * spread annotation in the AMT cyan style.
 */

import * as React from 'react'
import { cn, formatCompact, formatIN } from '@/lib/utils'

interface AMTDeepDOMProps {
  symbol?: string
  /** price, bid, ask per level */
  levels: { price: number; bid: number; ask: number }[]
  spread: number
  lastPrice: number
  className?: string
  height?: number
  levelsToShow?: number
}

const AMT = {
  bg: '#000',
  text: '#9ca3af',
  textDim: '#4a4a4a',
  cyan: '#22D3EE',
  bull: '#16a34a',
  bear: '#dc2626',
}

export function AMTDeepDOM({
  symbol = 'NIFTY',
  levels,
  spread,
  lastPrice,
  className,
  height = 360,
  levelsToShow = 16,
}: AMTDeepDOMProps) {
  const canvasRef = React.useRef<HTMLCanvasElement>(null)
  const containerRef = React.useRef<HTMLDivElement>(null)
  const [size, setSize] = React.useState({ w: 320, h: height })

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
    if (!canvas) return
    const dpr = window.devicePixelRatio || 1
    canvas.width = size.w * dpr
    canvas.height = size.h * dpr
    canvas.style.width = `${size.w}px`
    canvas.style.height = `${size.h}px`
    const ctx = canvas.getContext('2d')!
    ctx.scale(dpr, dpr)
    ctx.fillStyle = AMT.bg
    ctx.fillRect(0, 0, size.w, size.h)

    if (levels.length === 0) return
    const padding = { left: 6, right: 6, top: 6, bottom: 4 }
    const headerH = 40
    const footerH = 24
    const innerH = size.h - padding.top - padding.bottom - headerH - footerH
    const half = levelsToShow / 2
    const visibleLevels = levels.slice(0, levelsToShow)
    const rowH = innerH / visibleLevels.length

    const maxSize = Math.max(
      ...visibleLevels.map((l) => Math.max(l.bid, l.ask)),
      1,
    )

    // Column layout: PRICE | BID-SIZE | BID-BAR | MID | ASK-BAR | ASK-SIZE
    const colW = (size.w - padding.left - padding.right) / 5
    const xPrice = padding.left
    const xBidSize = padding.left + colW * 0.8
    const xBidBar = padding.left + colW * 1.4
    const xAskBar = padding.left + colW * 2.6
    const xAskSize = padding.left + colW * 3.6

    // Header
    ctx.fillStyle = AMT.cyan
    ctx.font = 'bold 9px "JetBrains Mono", monospace'
    ctx.textAlign = 'left'
    ctx.textBaseline = 'top'
    ctx.fillText('PRICE', xPrice, padding.top)
    ctx.textAlign = 'right'
    ctx.fillText('BUY', xBidSize, padding.top)
    ctx.textAlign = 'left'
    ctx.fillText('SELL', xAskSize, padding.top)
    ctx.fillStyle = AMT.text
    ctx.font = '9px "JetBrains Mono", monospace'
    ctx.textAlign = 'right'
    ctx.fillText('SPREAD', size.w - padding.right, padding.top)
    ctx.fillStyle = AMT.cyan
    ctx.font = 'bold 11px "JetBrains Mono", monospace'
    ctx.fillText(spread.toFixed(2), size.w - padding.right, padding.top + 12)

    // Header separator
    ctx.strokeStyle = 'rgba(34, 211, 238, 0.2)'
    ctx.beginPath()
    ctx.moveTo(padding.left, padding.top + 28)
    ctx.lineTo(size.w - padding.right, padding.top + 28)
    ctx.stroke()

    // Rows
    visibleLevels.forEach((lvl, i) => {
      const y = padding.top + headerH + i * rowH
      const isAboveMid = lvl.price > lastPrice
      const textColor = isAboveMid ? AMT.bear : AMT.bull

      // Row background (alternating subtle)
      if (i % 2 === 0) {
        ctx.fillStyle = 'rgba(34, 211, 238, 0.02)'
        ctx.fillRect(padding.left, y, size.w - padding.left - padding.right, rowH)
      }

      // Price
      ctx.fillStyle = textColor
      ctx.font = '10px "JetBrains Mono", monospace'
      ctx.textAlign = 'left'
      ctx.textBaseline = 'middle'
      ctx.fillText(formatIN(lvl.price), xPrice, y + rowH / 2)

      // Bid bar (grows rightward)
      const bidW = (lvl.bid / maxSize) * colW * 1.5
      ctx.fillStyle = `rgba(22, 163, 74, ${0.2 + (lvl.bid / maxSize) * 0.6})`
      ctx.fillRect(xBidBar, y + 2, bidW, rowH - 4)
      // Bid size
      ctx.fillStyle = '#fff'
      ctx.font = '9px "JetBrains Mono", monospace'
      ctx.textAlign = 'right'
      ctx.fillText(formatCompact(lvl.bid), xBidSize, y + rowH / 2)

      // Ask bar (grows leftward)
      const askW = (lvl.ask / maxSize) * colW * 1.5
      ctx.fillStyle = `rgba(220, 38, 38, ${0.2 + (lvl.ask / maxSize) * 0.6})`
      ctx.fillRect(xAskBar + (colW * 1.5 - askW), y + 2, askW, rowH - 4)
      // Ask size
      ctx.fillStyle = '#fff'
      ctx.textAlign = 'left'
      ctx.fillText(formatCompact(lvl.ask), xAskSize, y + rowH / 2)

      // Highlight last-price row
      if (Math.abs(lvl.price - lastPrice) < spread * 2) {
        ctx.fillStyle = 'rgba(34, 211, 238, 0.15)'
        ctx.fillRect(padding.left, y, size.w - padding.left - padding.right, rowH)
        ctx.strokeStyle = AMT.cyan
        ctx.lineWidth = 1
        ctx.strokeRect(padding.left + 0.5, y + 0.5, size.w - padding.left - padding.right - 1, rowH - 1)
      }
    })

    // Last price badge
    ctx.fillStyle = AMT.cyan
    ctx.fillRect(padding.left, padding.top + headerH + innerH - rowH / 2 - 8, 80, 16)
    ctx.fillStyle = '#000'
    ctx.font = 'bold 10px "JetBrains Mono", monospace'
    ctx.textAlign = 'left'
    ctx.textBaseline = 'middle'
    ctx.fillText(`LAST ${formatIN(lastPrice)}`, padding.left + 6, padding.top + headerH + innerH - rowH / 2)

    // Footer totals
    const totalBid = visibleLevels.reduce((s, l) => s + l.bid, 0)
    const totalAsk = visibleLevels.reduce((s, l) => s + l.ask, 0)
    const fy = size.h - footerH
    ctx.fillStyle = 'rgba(34, 211, 238, 0.1)'
    ctx.fillRect(padding.left, fy, size.w - padding.left - padding.right, footerH)
    ctx.fillStyle = AMT.bull
    ctx.font = 'bold 10px "JetBrains Mono", monospace'
    ctx.textAlign = 'left'
    ctx.textBaseline = 'middle'
    ctx.fillText(`BUY ${formatCompact(totalBid)}`, padding.left + 4, fy + footerH / 2)
    ctx.fillStyle = AMT.bear
    ctx.textAlign = 'right'
    ctx.fillText(`SELL ${formatCompact(totalAsk)}`, size.w - padding.right - 4, fy + footerH / 2)
  }, [levels, spread, lastPrice, size, levelsToShow])

  return (
    <div ref={containerRef} className={cn('relative w-full bg-black border border-cyan-500/20 rounded', className)} style={{ height }}>
      <div className="absolute top-1 left-2 text-[9px] font-mono uppercase tracking-wider text-cyan-400 pointer-events-none z-10">
        Deep DOM · {symbol}
      </div>
      <canvas ref={canvasRef} className="absolute inset-0" />
    </div>
  )
}
