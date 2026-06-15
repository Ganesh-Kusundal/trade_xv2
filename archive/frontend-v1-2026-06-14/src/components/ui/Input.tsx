import * as React from 'react'
import { cn } from '@/lib/utils'

interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size' | 'prefix'> {
  prefix?: React.ReactNode
  suffix?: React.ReactNode
  size?: 'sm' | 'md'
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, prefix, suffix, size = 'sm', ...props }, ref) => {
    return (
      <div
        className={cn(
          'flex items-center bg-bg-0 border border-line rounded transition-colors focus-within:border-brand focus-within:ring-1 focus-within:ring-brand/30',
          size === 'sm' ? 'h-7' : 'h-9',
          className,
        )}
      >
        {prefix && <div className="pl-2 text-fg-dim flex items-center">{prefix}</div>}
        <input
          ref={ref}
          className="flex-1 min-w-0 bg-transparent border-0 outline-none text-fg placeholder:text-fg-dim px-2 text-xs"
          {...props}
        />
        {suffix && <div className="pr-2 text-fg-dim flex items-center">{suffix}</div>}
      </div>
    )
  },
)
Input.displayName = 'Input'

interface SelectProps extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'size'> {
  size?: 'sm' | 'md'
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, size = 'sm', children, ...props }, ref) => {
    return (
      <select
        ref={ref}
        className={cn(
          'bg-bg-0 border border-line rounded text-fg text-xs px-2 outline-none focus:border-brand focus:ring-1 focus:ring-brand/30',
          size === 'sm' ? 'h-7' : 'h-9',
          'appearance-none pr-6 cursor-pointer',
          className,
        )}
        style={{
          backgroundImage: "url(\"data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2399a5bc' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E\")",
          backgroundRepeat: 'no-repeat',
          backgroundPosition: 'right 0.5rem center',
        }}
        {...props}
      >
        {children}
      </select>
    )
  },
)
Select.displayName = 'Select'
