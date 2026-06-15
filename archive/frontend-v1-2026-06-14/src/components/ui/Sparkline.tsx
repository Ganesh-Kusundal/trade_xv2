import * as React from 'react'
import { cn, formatIN, pnlColor } from '@/lib/utils'

interface SparklineProps {
  data: number[]
  width?: number
  height?: number
  className?: string
  color?: 'auto' | 'bull' | 'bear' | 'brand'
  showArea?: boolean
  showDot?: boolean
  strokeWidth?: number
}

export function Sparkline({
  data,
  width = 80,
  height = 24,
  className,
  color = 'auto',
  showArea = true,
  showDot = false,
  strokeWidth = 1.5,
}: SparklineProps) {
  if (!data || data.length < 2) return null
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const stepX = width / (data.length - 1)
  const points = data.map((v, i) => {
    const x = i * stepX
    const y = height - ((v - min) / range) * height
    return [x, y] as const
  })
  const linePath = points.map(([x, y], i) => (i === 0 ? `M${x},${y}` : `L${x},${y}`)).join(' ')
  const areaPath = `${linePath} L${width},${height} L0,${height} Z`
  const trendUp = data[data.length - 1] >= data[0]
  const stroke =
    color === 'brand'
      ? 'rgb(var(--brand))'
      : color === 'bull'
        ? 'rgb(var(--bullish))'
        : color === 'bear'
          ? 'rgb(var(--bearish))'
          : trendUp ? 'rgb(var(--bullish))' : 'rgb(var(--bearish))'
  const fill = trendUp ? 'rgb(var(--bullish) / 0.12)' : 'rgb(var(--bearish) / 0.12)'

  return (
    <svg width={width} height={height} className={cn('inline-block', className)}>
      {showArea && <path d={areaPath} fill={fill} />}
      <path d={linePath} stroke={stroke} fill="none" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
      {showDot && (
        <circle cx={points[points.length - 1][0]} cy={points[points.length - 1][1]} r={2} fill={stroke} />
      )}
    </svg>
  )
}

interface MiniBarsProps {
  data: number[]
  width?: number
  height?: number
  className?: string
  positiveColor?: string
  negativeColor?: string
}

export function MiniBars({ data, width = 80, height = 24, className, positiveColor, negativeColor }: MiniBarsProps) {
  if (!data || data.length < 2) return null
  const max = Math.max(...data.map(Math.abs))
  const stepX = width / data.length
  return (
    <svg width={width} height={height} className={cn('inline-block', className)}>
      {data.map((v, i) => {
        const h = (Math.abs(v) / max) * height
        const y = v >= 0 ? height - h : height / 2
        const x = i * stepX + 1
        return <rect key={i} x={x} y={y} width={stepX - 2} height={h} fill={v >= 0 ? positiveColor || 'rgb(var(--bullish))' : negativeColor || 'rgb(var(--bearish))'} rx={0.5} />
      })}
    </svg>
  )
}
