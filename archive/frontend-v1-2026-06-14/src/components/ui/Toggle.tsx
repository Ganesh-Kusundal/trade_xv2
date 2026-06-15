import * as React from 'react'
import { cn } from '@/lib/utils'

interface ToggleProps {
  value: boolean
  onChange: (v: boolean) => void
  size?: 'sm' | 'md'
  disabled?: boolean
  className?: string
}

export function Toggle({ value, onChange, size = 'sm', disabled, className }: ToggleProps) {
  const sizes = {
    sm: { track: 'w-7 h-4', thumb: 'h-3 w-3', translate: 'translate-x-3' },
    md: { track: 'w-9 h-5', thumb: 'h-4 w-4', translate: 'translate-x-4' },
  }
  const s = sizes[size]
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onChange(!value)}
      className={cn(
        'relative inline-flex items-center rounded-full transition-colors',
        s.track,
        value ? 'bg-brand' : 'bg-bg-3',
        disabled && 'opacity-50 cursor-not-allowed',
        className,
      )}
    >
      <span
        className={cn(
          'inline-block bg-white rounded-full transform transition-transform',
          s.thumb,
          value ? s.translate : 'translate-x-0.5',
        )}
      />
    </button>
  )
}
