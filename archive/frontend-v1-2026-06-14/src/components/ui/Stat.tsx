import * as React from 'react'
import { cn, pnlColor } from '@/lib/utils'

interface StatProps {
  label: React.ReactNode
  value: React.ReactNode
  subValue?: React.ReactNode
  delta?: number                   /* numeric change for coloring */
  deltaPrefix?: string             /* e.g. "+", "-" */
  size?: 'sm' | 'md' | 'lg' | 'xl'
  align?: 'left' | 'right' | 'center'
  variant?: 'default' | 'muted' | 'highlighted' | 'outlined'
  className?: string
  valueClassName?: string
  loading?: boolean
}

const sizeClasses = {
  sm: { label: 'text-2xs', value: 'text-sm' },
  md: { label: 'text-xs', value: 'text-base' },
  lg: { label: 'text-xs', value: 'text-2xl' },
  xl: { label: 'text-xs', value: 'text-3xl' },
}

export function Stat({
  label,
  value,
  subValue,
  delta,
  deltaPrefix = '',
  size = 'md',
  align = 'left',
  variant = 'default',
  className,
  valueClassName,
  loading,
}: StatProps) {
  const sz = sizeClasses[size]
  return (
    <div
      className={cn(
        'flex flex-col gap-0.5',
        align === 'right' && 'items-end',
        align === 'center' && 'items-center text-center',
        variant === 'highlighted' && 'px-3 py-2 rounded-md bg-bg-2 border border-line',
        variant === 'outlined' && 'px-3 py-2 rounded-md border border-line',
        className,
      )}
    >
      <div className={cn('uppercase tracking-wider text-fg-dim font-medium', sz.label)}>{label}</div>
      {loading ? (
        <div className={cn('h-6 w-16 rounded bg-bg-2 animate-pulse', sz.value)} />
      ) : (
        <div className={cn('font-semibold num leading-tight', sz.value, valueClassName)}>
          {value}
        </div>
      )}
      {subValue != null && (
        <div className={cn('text-2xs', delta != null ? pnlColor(delta) : 'text-fg-dim')}>
          {delta != null && `${deltaPrefix}${delta >= 0 ? '+' : ''}${delta.toFixed(2)}%`}
          {delta == null && subValue}
        </div>
      )}
    </div>
  )
}
