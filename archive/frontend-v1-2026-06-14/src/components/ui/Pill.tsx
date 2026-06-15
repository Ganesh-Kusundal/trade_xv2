import * as React from 'react'
import { cn } from '@/lib/utils'

type Variant = 'default' | 'bull' | 'bear' | 'warn' | 'info' | 'neutral' | 'brand'

interface PillProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: Variant
  dot?: boolean
}

const variantClasses: Record<Variant, string> = {
  default: 'bg-bg-2 text-fg-muted border border-line',
  bull: 'bg-bullish/15 text-bullish border border-bullish/25',
  bear: 'bg-bearish/15 text-bearish border border-bearish/25',
  warn: 'bg-warning/15 text-warning border border-warning/25',
  info: 'bg-info/15 text-info border border-info/25',
  neutral: 'bg-bg-2 text-fg-dim border border-line',
  brand: 'bg-brand/15 text-brand border border-brand/30',
}

const dotColors: Record<Variant, string> = {
  default: 'bg-fg-muted',
  bull: 'bg-bullish',
  bear: 'bg-bearish',
  warn: 'bg-warning',
  info: 'bg-info',
  neutral: 'bg-fg-dim',
  brand: 'bg-brand',
}

export const Pill = React.forwardRef<HTMLSpanElement, PillProps>(
  ({ className, variant = 'default', dot, children, ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={cn(
          'inline-flex items-center gap-1 px-1.5 py-0.5 text-2xs font-medium rounded uppercase tracking-wide whitespace-nowrap',
          variantClasses[variant],
          className,
        )}
        {...props}
      >
        {dot && <span className={cn('h-1.5 w-1.5 rounded-full', dotColors[variant], variant === 'bull' && 'pulse-dot')} />}
        {children}
      </span>
    )
  },
)
Pill.displayName = 'Pill'
