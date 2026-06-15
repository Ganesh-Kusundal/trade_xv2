/**
 * FunctionKeyBar — Bloomberg-style F1-F12 function keys at the bottom.
 *
 * Each key is a small button with a label. Pressing a key triggers an
 * action (e.g. F1 opens help, F4 opens chart settings, F6 opens T&S).
 */

import { useEffect } from 'react'
import {
  HelpCircle, Search, Play, CandlestickChart, Layers, Activity,
  FileText, Briefcase, Shield, Bell, Settings, Power,
} from 'lucide-react'
import { cn } from '@/lib/utils'

export interface FunctionKey {
  id: string
  label: string
  icon: typeof Search
  hint?: string
  onClick?: () => void
  active?: boolean
}

interface FunctionKeyBarProps {
  onCommand?: (cmd: string) => void
  activePanel?: string
}

export function FunctionKeyBar({ onCommand, activePanel }: FunctionKeyBarProps) {
  const keys: FunctionKey[] = [
    { id: 'F1',  label: 'HELP',    icon: HelpCircle,       hint: '?' },
    { id: 'F2',  label: 'SEARCH',  icon: Search,           hint: 'Find symbol' },
    { id: 'F3',  label: 'GO',      icon: Play,             hint: 'Command line' },
    { id: 'F4',  label: 'CHART',   icon: CandlestickChart, hint: 'Chart tools', active: activePanel === 'chart' },
    { id: 'F5',  label: 'DEPTH',   icon: Layers,           hint: 'Market depth', active: activePanel === 'depth' },
    { id: 'F6',  label: 'T&S',     icon: Activity,         hint: 'Time & sales', active: activePanel === 'tns' },
    { id: 'F7',  label: 'NEWS',    icon: FileText,         hint: 'News feed' },
    { id: 'F8',  label: 'PORT',    icon: Briefcase,        hint: 'Portfolio' },
    { id: 'F9',  label: 'RISK',    icon: Shield,           hint: 'Risk' },
    { id: 'F10', label: 'ALERT',   icon: Bell,             hint: 'Alerts' },
    { id: 'F11', label: 'PREFS',   icon: Settings,         hint: 'Preferences' },
    { id: 'F12', label: 'EXIT',    icon: Power,            hint: 'Exit / menu' },
  ]

  // F1-F12 keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!e.altKey) return
      const k = keys.find((x) => x.id === `F${e.key}`)
      if (k) {
        e.preventDefault()
        onCommand?.(k.id)
        k.onClick?.()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [keys, onCommand])

  return (
    <div className="flex items-stretch h-8 border-t border-bline bg-bbg1">
      {keys.map((k) => {
        const Icon = k.icon
        return (
          <button
            key={k.id}
            onClick={() => { onCommand?.(k.id); k.onClick?.() }}
            title={`${k.id} — ${k.hint ?? k.label}`}
            className={cn(
              'group flex-1 min-w-0 flex items-center justify-center gap-1 px-1.5 border-r border-bline last:border-r-0',
              'bg-bbg1 hover:bg-bbg2 text-bfgm hover:text-bfg',
              'transition-colors',
              k.active && 'bg-bamb/10 text-bamb',
            )}
          >
            <span className="text-[9px] font-mono text-bfgd group-hover:text-bamb w-5 text-left">
              {k.id}
            </span>
            <Icon className="h-3 w-3 flex-shrink-0" />
            <span className="text-2xs font-semibold uppercase tracking-wider truncate">
              {k.label}
            </span>
          </button>
        )
      })}
    </div>
  )
}
