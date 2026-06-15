import * as React from 'react'
import { cn, formatIN } from '@/lib/utils'

interface ProgressBarProps {
  value: number              /* 0..100 */
  size?: 'xs' | 'sm' | 'md'
  variant?: 'default' | 'bull' | 'bear' | 'warning' | 'info' | 'auto'
  showLabel?: boolean
  className?: string
}

export function ProgressBar({ value, size = 'sm', variant = 'default', showLabel, className }: ProgressBarProps) {
  const v = Math.max(0, Math.min(100, value))
  const heights = { xs: 'h-1', sm: 'h-1.5', md: 'h-2.5' }
  const colorMap: Record<string, string> = {
    default: 'bg-brand',
    bull: 'bg-bullish',
    bear: 'bg-bearish',
    warning: 'bg-warning',
    info: 'bg-info',
  }
  const color = variant === 'auto' ? (v > 70 ? 'bg-bullish' : v > 30 ? 'bg-warning' : 'bg-bearish') : colorMap[variant]
  return (
    <div className={cn('flex items-center gap-2 w-full', className)}>
      <div className={cn('flex-1 bg-bg-2 rounded overflow-hidden', heights[size])}>
        <div className={cn('h-full transition-all', color)} style={{ width: `${v}%` }} />
      </div>
      {showLabel && <span className="text-2xs num text-fg-muted min-w-[3ch] text-right">{v.toFixed(0)}%</span>}
    </div>
  )
}

interface GaugeProps {
  value: number          /* 0..100 */
  label?: string
  size?: number
  thickness?: number
  className?: string
  variant?: 'auto' | 'bull' | 'bear' | 'brand'
}

export function Gauge({ value, label, size = 80, thickness = 6, className, variant = 'auto' }: GaugeProps) {
  const v = Math.max(0, Math.min(100, value))
  const radius = (size - thickness) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (v / 100) * circumference
  let color = '#3b82f6'
  if (variant === 'bull') color = '#16a34a'
  else if (variant === 'bear') color = '#dc2626'
  else if (variant === 'auto') {
    color = v > 70 ? '#16a34a' : v > 40 ? '#f59e0b' : '#dc2626'
  }
  return (
    <div className={cn('inline-flex flex-col items-center justify-center', className)}>
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="rgb(var(--bg-2))" strokeWidth={thickness} />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={thickness}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            className="transition-all"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center text-xs font-semibold num" style={{ color }}>
          {v.toFixed(0)}
        </div>
      </div>
      {label && <div className="text-2xs text-fg-dim mt-1 uppercase tracking-wider">{label}</div>}
    </div>
  )
}

interface DistributionProps {
  data: { label: string; value: number; color?: string }[]
  size?: number
  thickness?: number
  centerLabel?: string
  centerValue?: string
  className?: string
}

export function Distribution({ data, size = 120, thickness = 14, centerLabel, centerValue, className }: DistributionProps) {
  const total = data.reduce((s, d) => s + d.value, 0) || 1
  const radius = (size - thickness) / 2
  const circumference = 2 * Math.PI * radius
  let offset = 0
  const palette = ['#3b82f6', '#10b981', '#f59e0b', '#a855f7', '#ef4444', '#06b6d4', '#ec4899', '#8b5cf6']
  return (
    <div className={cn('relative inline-flex flex-col items-center justify-center', className)}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="rgb(var(--bg-2))" strokeWidth={thickness} />
        {data.map((d, i) => {
          const fraction = d.value / total
          const dash = fraction * circumference
          const seg = (
            <circle
              key={i}
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={d.color || palette[i % palette.length]}
              strokeWidth={thickness}
              strokeDasharray={`${dash} ${circumference - dash}`}
              strokeDashoffset={-offset}
            />
          )
          offset += dash
          return seg
        })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        {centerValue && <div className="text-xl font-semibold num">{centerValue}</div>}
        {centerLabel && <div className="text-2xs text-fg-dim uppercase tracking-wider">{centerLabel}</div>}
      </div>
    </div>
  )
}
