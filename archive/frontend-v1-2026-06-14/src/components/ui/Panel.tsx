import * as React from 'react'
import { cn } from '@/lib/utils'

interface PanelProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  title?: React.ReactNode
  subtitle?: React.ReactNode
  actions?: React.ReactNode
  bodyClassName?: string
  noPadding?: boolean
  variant?: 'default' | 'elevated' | 'flat'
}

export const Panel = React.forwardRef<HTMLDivElement, PanelProps>(
  ({ className, title, subtitle, actions, bodyClassName, children, noPadding, variant = 'default', ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          'flex flex-col bg-bg-1 border border-line rounded-md overflow-hidden',
          variant === 'elevated' && 'shadow-panel',
          variant === 'flat' && 'border-transparent',
          className,
        )}
        {...props}
      >
        {(title || actions) && (
          <div className="flex items-center justify-between px-3 py-2 border-b border-line bg-bg-2/40">
            <div className="flex items-center gap-2 min-w-0">
              {title && <div className="text-xs font-semibold uppercase tracking-wider text-fg-muted truncate">{title}</div>}
              {subtitle && <div className="text-2xs text-fg-dim truncate">{subtitle}</div>}
            </div>
            {actions && <div className="flex items-center gap-1.5 flex-shrink-0">{actions}</div>}
          </div>
        )}
        <div className={cn('flex-1 min-h-0 overflow-auto', !noPadding && 'p-3', bodyClassName)}>
          {children}
        </div>
      </div>
    )
  },
)
Panel.displayName = 'Panel'
