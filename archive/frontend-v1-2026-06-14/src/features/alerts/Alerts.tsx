import { Panel } from '@/components/ui/Panel'
import { Pill } from '@/components/ui/Pill'
import { ALERTS } from '@/services/mockData'
import { cn, formatTime, timeAgo, pnlColor } from '@/lib/utils'
import { Bell, AlertTriangle, AlertCircle, Info, CheckCircle2, X, Plus, Settings, Filter, Search, Activity, TrendingUp, Volume2, Shield, Zap } from 'lucide-react'
import { useState } from 'react'

const ALERT_TEMPLATES = [
  { id: 'price-above', icon: TrendingUp, label: 'Price crosses above', type: 'PRICE' },
  { id: 'price-below', icon: TrendingUp, label: 'Price crosses below', type: 'PRICE' },
  { id: 'volume-spike', icon: Volume2, label: 'Volume > Nx avg', type: 'VOLUME' },
  { id: 'oi-buildup', icon: Activity, label: 'OI build-up detected', type: 'OI' },
  { id: 'rsi-extreme', icon: Zap, label: 'RSI overbought/oversold', type: 'TECHNICAL' },
  { id: 'risk-limit', icon: Shield, label: 'Risk limit approached', type: 'RISK' },
]

export function Alerts() {
  const [filter, setFilter] = useState<'all' | 'active' | 'acknowledged' | 'dismissed'>('all')
  const filtered = ALERTS.filter((a) => filter === 'all' || a.status.toLowerCase() === filter)
  const activeCount = ALERTS.filter((a) => a.status === 'ACTIVE').length
  const criticalCount = ALERTS.filter((a) => a.priority === 'CRITICAL').length

  return (
    <div className="h-full grid grid-cols-12 gap-2 p-2">
      {/* Left: New alert templates */}
      <Panel
        className="col-span-3"
        title="Create Alert"
        actions={<Pill variant="info" className="text-2xs">{ALERT_TEMPLATES.length} templates</Pill>}
      >
        <div className="space-y-1.5">
          {ALERT_TEMPLATES.map((t) => {
            const Icon = t.icon
            return (
              <button key={t.id} className="w-full flex items-center gap-2 p-2 bg-bg-2 hover:bg-bg-3 rounded border border-line text-left transition-colors">
                <div className="h-7 w-7 rounded bg-brand/15 flex items-center justify-center flex-shrink-0">
                  <Icon className="h-3.5 w-3.5 text-brand" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium">{t.label}</div>
                  <div className="text-2xs text-fg-dim">{t.type}</div>
                </div>
                <Plus className="h-3.5 w-3.5 text-fg-muted" />
              </button>
            )
          })}
        </div>

        <div className="mt-4 pt-3 border-t border-line space-y-2 text-2xs">
          <div className="flex justify-between">
            <span className="text-fg-dim">Active Alerts</span>
            <span className="font-mono num text-bullish">{activeCount}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-fg-dim">Critical</span>
            <span className="font-mono num text-bearish">{criticalCount}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-fg-dim">Total Today</span>
            <span className="font-mono num">{ALERTS.length}</span>
          </div>
        </div>
      </Panel>

      {/* Right: Alert feed */}
      <Panel
        className="col-span-9"
        title="Alert Feed"
        subtitle={`${filtered.length} alerts`}
        actions={
          <>
            <div className="flex items-center gap-1 mr-2">
              {(['all', 'active', 'acknowledged', 'dismissed'] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={cn(
                    'h-7 px-2.5 text-2xs font-medium rounded uppercase tracking-wider',
                    filter === f ? 'bg-bg-3 text-fg' : 'text-fg-muted hover:bg-bg-2',
                  )}
                >
                  {f}
                </button>
              ))}
            </div>
            <button className="btn btn-ghost"><Filter className="h-3.5 w-3.5" /></button>
            <button className="btn btn-secondary"><Settings className="h-3.5 w-3.5" /></button>
          </>
        }
        noPadding
      >
        <div className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 180px)' }}>
          {filtered.map((a) => {
            const Icon = a.type === 'PRICE' ? TrendingUp :
                         a.type === 'VOLUME' ? Volume2 :
                         a.type === 'OI' ? Activity :
                         a.type === 'TECHNICAL' ? Zap :
                         a.type === 'RISK' ? Shield : Info
            return (
              <div
                key={a.id}
                className={cn('flex items-start gap-3 p-3 border-b border-line-subtle hover:bg-bg-2 transition-colors',
                  a.priority === 'CRITICAL' && 'bg-bearish/5',
                  a.priority === 'HIGH' && 'bg-warning/5',
                )}
              >
                <div className={cn(
                  'h-9 w-9 rounded-full flex items-center justify-center flex-shrink-0',
                  a.priority === 'CRITICAL' ? 'bg-bearish/20' :
                  a.priority === 'HIGH' ? 'bg-warning/20' :
                  'bg-brand/20',
                )}>
                  <Icon className={cn(
                    'h-4 w-4',
                    a.priority === 'CRITICAL' ? 'text-bearish' :
                    a.priority === 'HIGH' ? 'text-warning' :
                    'text-brand',
                  )} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <Pill variant={a.priority === 'CRITICAL' ? 'bear' : a.priority === 'HIGH' ? 'warn' : a.priority === 'MEDIUM' ? 'info' : 'neutral'} className="text-2xs">
                      {a.priority}
                    </Pill>
                    <Pill variant="neutral" className="text-2xs">{a.type}</Pill>
                    <span className="text-xs font-semibold">{a.symbol}</span>
                    <span className="ml-auto text-2xs text-fg-dim font-mono">{timeAgo(a.triggeredAt)}</span>
                  </div>
                  <div className="text-sm text-fg mt-1">{a.message}</div>
                  <div className="text-2xs text-fg-dim mt-1 font-mono">{a.condition}</div>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <button className="h-7 px-2.5 text-2xs rounded bg-bg-2 hover:bg-bg-3 text-fg-muted">
                    <CheckCircle2 className="h-3 w-3" />
                  </button>
                  <button className="h-7 px-2.5 text-2xs rounded bg-bearish/15 text-bearish border border-bearish/30 hover:bg-bearish/25">
                    <X className="h-3 w-3" />
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </Panel>
    </div>
  )
}
