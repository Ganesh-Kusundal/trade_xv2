import * as React from 'react'
import { cn } from '@/lib/utils'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'bull' | 'bear' | 'danger' | 'outline'
  size?: 'xs' | 'sm' | 'md' | 'lg'
  iconOnly?: boolean
  loading?: boolean
}

const variants = {
  primary: 'bg-brand text-white hover:bg-brand-600 active:bg-brand-700',
  secondary: 'bg-bg-2 text-fg border border-line hover:bg-bg-3 hover:border-line-strong',
  ghost: 'text-fg-muted hover:text-fg hover:bg-bg-2',
  bull: 'bg-bullish/15 text-bullish border border-bullish/30 hover:bg-bullish/25',
  bear: 'bg-bearish/15 text-bearish border border-bearish/30 hover:bg-bearish/25',
  danger: 'bg-danger text-white hover:bg-red-600',
  outline: 'border border-line text-fg hover:bg-bg-2',
}

const sizes = {
  xs: 'h-6 px-2 text-2xs',
  sm: 'h-7 px-2.5 text-xs',
  md: 'h-8 px-3 text-sm',
  lg: 'h-10 px-4 text-base',
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'secondary', size = 'sm', iconOnly, loading, children, disabled, ...props }, ref) => {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={cn(
          'inline-flex items-center justify-center gap-1.5 font-medium rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed',
          variants[variant],
          sizes[size],
          iconOnly && 'aspect-square px-0',
          className,
        )}
        {...props}
      >
        {loading ? <span className="inline-block h-3 w-3 border-2 border-current border-t-transparent rounded-full animate-spin" /> : children}
      </button>
    )
  },
)
Button.displayName = 'Button'
