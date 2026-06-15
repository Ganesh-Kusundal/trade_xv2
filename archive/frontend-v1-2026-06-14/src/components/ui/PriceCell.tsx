import * as React from 'react'
import { cn, pnlColor, formatIN, pnlBgColor } from '@/lib/utils'

interface PriceCellProps {
  value: number
  change?: number
  prevValue?: number
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  decimals?: number
  showChange?: boolean
  className?: string
  flash?: boolean
  pulse?: boolean
}

const sizeClasses = {
  xs: 'text-xs',
  sm: 'text-sm',
  md: 'text-base',
  lg: 'text-2xl',
  xl: 'text-3xl',
}

export function PriceCell({
  value,
  change,
  prevValue,
  size = 'sm',
  decimals = 2,
  showChange = false,
  className,
  flash,
  pulse,
}: PriceCellProps) {
  const effectiveChange = change != null ? change : prevValue != null ? value - prevValue : 0
  return (
    <div className={cn('flex items-baseline gap-1.5', className)}>
      <span className={cn('font-mono font-semibold num leading-none', sizeClasses[size], pnlColor(effectiveChange))}>
        {formatIN(value, decimals)}
      </span>
      {showChange && change != null && (
        <span className={cn('text-2xs font-mono num', pnlColor(change))}>
          {change >= 0 ? '+' : ''}
          {change.toFixed(2)}%
        </span>
      )}
      {pulse && <span className="h-1.5 w-1.5 rounded-full bg-current pulse-dot" />}
    </div>
  )
}

interface ChangeCellProps {
  value: number
  format?: 'percent' | 'number' | 'currency'
  prefix?: string
  size?: 'xs' | 'sm' | 'md'
  bg?: boolean
  className?: string
}

export function ChangeCell({ value, format = 'percent', prefix = '', size = 'xs', bg, className }: ChangeCellProps) {
  const display = format === 'percent' ? `${value >= 0 ? '+' : ''}${value.toFixed(2)}%` : format === 'currency' ? `${value >= 0 ? '+' : ''}₹${Math.abs(value).toFixed(2)}` : `${value >= 0 ? '+' : ''}${value.toFixed(2)}`
  return (
    <span
      className={cn(
        'font-mono num',
        size === 'xs' && 'text-2xs',
        size === 'sm' && 'text-xs',
        size === 'md' && 'text-sm',
        pnlColor(value),
        bg && cn('px-1.5 py-0.5 rounded', pnlBgColor(value)),
        className,
      )}
    >
      {prefix}
      {display}
    </span>
  )
}
