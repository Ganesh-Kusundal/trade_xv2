import * as React from 'react'
import { cn, pnlColor } from '@/lib/utils'

interface TabsContextValue {
  value: string
  onChange: (v: string) => void
}

const TabsContext = React.createContext<TabsContextValue | null>(null)

interface TabsProps {
  value: string
  onValueChange: (v: string) => void
  children: React.ReactNode
  className?: string
  variant?: 'default' | 'pills' | 'underline'
}

export function Tabs({ value, onValueChange, children, className, variant = 'default' }: TabsProps) {
  return (
    <TabsContext.Provider value={{ value, onChange: onValueChange }}>
      <div className={cn('flex', className)}>{children}</div>
    </TabsContext.Provider>
  )
}

interface TabsListProps {
  children: React.ReactNode
  className?: string
  variant?: 'default' | 'pills' | 'underline'
}

export function TabsList({ children, className }: TabsListProps) {
  return <div className={cn('flex items-center gap-0.5', className)}>{children}</div>
}

interface TabsTriggerProps {
  value: string
  children: React.ReactNode
  className?: string
  active?: boolean
  onClick?: () => void
}

export function TabsTrigger({ value, children, className, active, onClick }: TabsTriggerProps) {
  const ctx = React.useContext(TabsContext)
  const isActive = active ?? ctx?.value === value
  return (
    <button
      onClick={() => {
        ctx?.onChange(value)
        onClick?.()
      }}
      className={cn(
        'px-2.5 h-7 text-xs font-medium rounded transition-colors flex items-center gap-1.5',
        isActive
          ? 'bg-bg-2 text-fg border border-line'
          : 'text-fg-muted hover:text-fg hover:bg-bg-2 border border-transparent',
        className,
      )}
    >
      {children}
    </button>
  )
}

interface TabsContentProps {
  value: string
  children: React.ReactNode
  className?: string
}

export function TabsContent({ value, children, className }: TabsContentProps) {
  const ctx = React.useContext(TabsContext)
  if (ctx?.value !== value) return null
  return <div className={cn('flex-1 min-h-0', className)}>{children}</div>
}
