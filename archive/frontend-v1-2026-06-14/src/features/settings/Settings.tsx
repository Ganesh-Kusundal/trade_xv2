import { Panel } from '@/components/ui/Panel'
import { Pill } from '@/components/ui/Pill'
import { Toggle } from '@/components/ui/Toggle'
import { useState } from 'react'
import { cn } from '@/lib/utils'
import { User, Server, Bell, Shield, CreditCard, Palette, Key, Wifi, Globe, Save, Database, Cloud, Bot, FileText, Smartphone, Mail, AlertCircle, Check, Award } from 'lucide-react'

const SECTIONS = [
  { id: 'profile', label: 'Profile', icon: User },
  { id: 'broker', label: 'Broker Connections', icon: Server },
  { id: 'data', label: 'Data Sources', icon: Database },
  { id: 'notifications', label: 'Notifications', icon: Bell },
  { id: 'security', label: 'Security', icon: Shield },
  { id: 'billing', label: 'Billing', icon: CreditCard },
  { id: 'appearance', label: 'Appearance', icon: Palette },
  { id: 'apikeys', label: 'API Keys', icon: Key },
  { id: 'automation', label: 'Automation', icon: Bot },
] as const

export function Settings() {
  const [section, setSection] = useState<typeof SECTIONS[number]['id']>('profile')
  const [darkMode, setDarkMode] = useState(true)
  const [notif, setNotif] = useState({ desktop: true, email: true, sms: false, telegram: true })

  return (
    <div className="h-full grid grid-cols-12 gap-2 p-2">
      {/* Sidebar */}
      <Panel className="col-span-2" title="Settings" noPadding>
        <nav className="p-1.5 space-y-0.5">
          {SECTIONS.map((s) => {
            const Icon = s.icon
            return (
              <button
                key={s.id}
                onClick={() => setSection(s.id)}
                className={cn(
                  'w-full flex items-center gap-2 px-2.5 h-8 text-xs font-medium rounded transition-colors',
                  section === s.id ? 'bg-bg-3 text-fg' : 'text-fg-muted hover:bg-bg-2',
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                <span className="truncate">{s.label}</span>
              </button>
            )
          })}
        </nav>
      </Panel>

      {/* Content */}
      <div className="col-span-10 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 100px)' }}>
        {section === 'profile' && (
          <Panel title="Profile" actions={<button className="btn btn-primary"><Save className="h-3.5 w-3.5" /> Save</button>}>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-2xs text-fg-dim uppercase tracking-wider">Full Name</label>
                <input defaultValue="Arjun Kumar" className="w-full h-9 bg-bg-0 border border-line rounded px-2 text-sm mt-1" />
              </div>
              <div>
                <label className="text-2xs text-fg-dim uppercase tracking-wider">Email</label>
                <input defaultValue="arjun@tradexv2.com" className="w-full h-9 bg-bg-0 border border-line rounded px-2 text-sm mt-1" />
              </div>
              <div>
                <label className="text-2xs text-fg-dim uppercase tracking-wider">Mobile</label>
                <input defaultValue="+91 98765 43210" className="w-full h-9 bg-bg-0 border border-line rounded px-2 text-sm mt-1" />
              </div>
              <div>
                <label className="text-2xs text-fg-dim uppercase tracking-wider">Trading Style</label>
                <select className="w-full h-9 bg-bg-0 border border-line rounded px-2 text-sm mt-1">
                  <option>Intraday</option>
                  <option>Swing</option>
                  <option>Positional</option>
                  <option>Options</option>
                </select>
              </div>
              <div className="col-span-2">
                <label className="text-2xs text-fg-dim uppercase tracking-wider">Bio</label>
                <textarea defaultValue="Quant researcher with 8+ years of experience in Indian markets. Specializing in momentum and mean-reversion strategies." className="w-full h-20 bg-bg-0 border border-line rounded p-2 text-sm mt-1 resize-none" />
              </div>
            </div>
          </Panel>
        )}

        {section === 'broker' && (
          <div className="space-y-2">
            <Panel title="Broker Connections" subtitle="Manage your broker integrations">
              <div className="space-y-2">
                {[
                  { name: 'DhanHQ', status: 'connected', user: 'TR12345', mode: 'Live', icon: '🟢' },
                  { name: 'Upstox', status: 'connected', user: 'UP98765', mode: 'Live', icon: '🟢' },
                  { name: 'Zerodha Kite', status: 'disconnected', user: '-', mode: '-', icon: '⚪' },
                  { name: 'Angel One', status: 'disconnected', user: '-', mode: '-', icon: '⚪' },
                  { name: 'ICICI Direct', status: 'disconnected', user: '-', mode: '-', icon: '⚪' },
                  { name: 'Paper Trading', status: 'connected', user: 'PAPER-01', mode: 'Simulated', icon: '🟢' },
                ].map((b) => (
                  <div key={b.name} className="flex items-center gap-3 p-3 bg-bg-2 rounded border border-line">
                    <div className="h-10 w-10 rounded bg-bg-3 flex items-center justify-center text-lg">{b.icon}</div>
                    <div className="flex-1">
                      <div className="text-sm font-semibold">{b.name}</div>
                      <div className="text-2xs text-fg-muted font-mono">{b.user}</div>
                    </div>
                    <Pill variant={b.status === 'connected' ? 'bull' : 'neutral'} dot className="text-2xs">
                      {b.status === 'connected' ? `${b.mode} · Connected` : 'Disconnected'}
                    </Pill>
                    <button className={cn('btn', b.status === 'connected' ? 'btn-secondary' : 'btn-primary')}>
                      {b.status === 'connected' ? 'Manage' : 'Connect'}
                    </button>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
        )}

        {section === 'data' && (
          <Panel title="Data Sources">
            <div className="space-y-2">
              {[
                { name: 'NSE Equity (Live)', status: 'connected', latency: '12ms', source: 'DhanHQ' },
                { name: 'NSE Derivatives', status: 'connected', latency: '14ms', source: 'DhanHQ' },
                { name: 'NSE Options Chain', status: 'connected', latency: '18ms', source: 'DhanHQ' },
                { name: 'Historical Data Lake', status: 'connected', latency: 'offline', source: 'Parquet · 5Y' },
                { name: 'Upstox WebSocket', status: 'connected', latency: '16ms', source: 'Upstox' },
                { name: 'News Feed', status: 'connected', latency: '5m', source: 'NewsAPI' },
                { name: 'Alternative Data', status: 'disconnected', latency: '-', source: 'Not configured' },
              ].map((d) => (
                <div key={d.name} className="flex items-center gap-3 p-3 bg-bg-2 rounded border border-line">
                  <Database className="h-4 w-4 text-fg-muted" />
                  <div className="flex-1">
                    <div className="text-sm font-semibold">{d.name}</div>
                    <div className="text-2xs text-fg-muted">{d.source}</div>
                  </div>
                  <Pill variant={d.status === 'connected' ? 'bull' : 'neutral'} className="text-2xs font-mono">
                    {d.latency}
                  </Pill>
                  <Pill variant={d.status === 'connected' ? 'bull' : 'neutral'} dot className="text-2xs">
                    {d.status}
                  </Pill>
                </div>
              ))}
            </div>
          </Panel>
        )}

        {section === 'notifications' && (
          <Panel title="Notification Preferences">
            <div className="space-y-3">
              {[
                { key: 'desktop', label: 'Desktop Notifications', desc: 'Browser push notifications', icon: Smartphone },
                { key: 'email', label: 'Email Notifications', desc: 'Daily digest + critical alerts', icon: Mail },
                { key: 'sms', label: 'SMS Notifications', desc: 'Critical alerts only', icon: Smartphone },
                { key: 'telegram', label: 'Telegram Bot', desc: 'Real-time signals & alerts', icon: Bot },
              ].map((n) => {
                const Icon = n.icon
                return (
                  <div key={n.key} className="flex items-center gap-3 p-3 bg-bg-2 rounded border border-line">
                    <Icon className="h-4 w-4 text-fg-muted" />
                    <div className="flex-1">
                      <div className="text-sm font-semibold">{n.label}</div>
                      <div className="text-2xs text-fg-muted">{n.desc}</div>
                    </div>
                    <Toggle value={(notif as any)[n.key]} onChange={(v) => setNotif((p) => ({ ...p, [n.key]: v }))} />
                  </div>
                )
              })}
            </div>
          </Panel>
        )}

        {section === 'security' && (
          <Panel title="Security" actions={<button className="btn btn-primary">Update</button>}>
            <div className="space-y-3">
              <div className="p-3 bg-bg-2 rounded border border-line">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-semibold">Two-Factor Authentication</div>
                    <div className="text-2xs text-fg-muted">TOTP-based, enabled via authenticator app</div>
                  </div>
                  <Pill variant="bull" dot>Enabled</Pill>
                </div>
              </div>
              <div className="p-3 bg-bg-2 rounded border border-line">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-semibold">Trading PIN</div>
                    <div className="text-2xs text-fg-muted">Required for order placement above ₹1L</div>
                  </div>
                  <Pill variant="bull" dot>Set</Pill>
                </div>
              </div>
              <div className="p-3 bg-bg-2 rounded border border-line">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-semibold">IP Whitelisting</div>
                    <div className="text-2xs text-fg-muted">Restrict API access to known IPs</div>
                  </div>
                  <Pill variant="neutral">2 IPs</Pill>
                </div>
              </div>
              <div className="p-3 bg-bg-2 rounded border border-line">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-semibold">Session Timeout</div>
                    <div className="text-2xs text-fg-muted">Auto-logout after inactivity</div>
                  </div>
                  <Pill variant="info">30 min</Pill>
                </div>
              </div>
            </div>
          </Panel>
        )}

        {section === 'billing' && (
          <div className="space-y-2">
            <Panel title="Current Plan" actions={<button className="btn btn-primary">Upgrade</button>}>
              <div className="flex items-center gap-4 p-4 bg-gradient-to-br from-brand/20 to-accent/10 border border-brand/30 rounded">
                <div className="h-12 w-12 rounded-full bg-brand/30 flex items-center justify-center">
                  <Award className="h-6 w-6 text-brand" />
                </div>
                <div className="flex-1">
                  <div className="text-lg font-semibold">Pro Plan</div>
                  <div className="text-2xs text-fg-muted">Unlimited scanners · Live data · Multi-broker</div>
                </div>
                <div className="text-right">
                  <div className="text-2xl font-semibold font-mono num">₹4,999</div>
                  <div className="text-2xs text-fg-muted">/month</div>
                </div>
              </div>
            </Panel>
            <Panel title="Usage" noPadding>
              <div className="p-3 space-y-3">
                {[
                  { label: 'API Calls', used: 45200, max: 100000 },
                  { label: 'Scanners', used: 6, max: 20 },
                  { label: 'Strategies', used: 4, max: 10 },
                  { label: 'Backtests', used: 8, max: 50 },
                ].map((u) => (
                  <div key={u.label}>
                    <div className="flex justify-between text-2xs mb-1">
                      <span className="text-fg-muted">{u.label}</span>
                      <span className="font-mono num">{u.used.toLocaleString('en-IN')} / {u.max.toLocaleString('en-IN')}</span>
                    </div>
                    <div className="h-2 bg-bg-2 rounded">
                      <div className="h-full bg-brand rounded" style={{ width: `${(u.used / u.max) * 100}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
        )}

        {section === 'appearance' && (
          <Panel title="Appearance">
            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 bg-bg-2 rounded border border-line">
                <div>
                  <div className="text-sm font-semibold">Dark Mode</div>
                  <div className="text-2xs text-fg-muted">Recommended for long trading sessions</div>
                </div>
                <Toggle value={darkMode} onChange={setDarkMode} />
              </div>
              <div>
                <label className="text-2xs text-fg-dim uppercase tracking-wider">Accent Color</label>
                <div className="flex gap-2 mt-1">
                  {['#3b82f6', '#10b981', '#f59e0b', '#a855f7', '#ec4899', '#06b6d4'].map((c) => (
                    <button key={c} className="h-8 w-8 rounded border-2 border-line hover:border-fg" style={{ background: c }} />
                  ))}
                </div>
              </div>
              <div>
                <label className="text-2xs text-fg-dim uppercase tracking-wider">Density</label>
                <div className="flex gap-2 mt-1">
                  {['Compact', 'Comfortable', 'Spacious'].map((d) => (
                    <button key={d} className="h-9 px-3 bg-bg-2 hover:bg-bg-3 rounded text-xs flex-1">{d}</button>
                  ))}
                </div>
              </div>
            </div>
          </Panel>
        )}

        {section === 'apikeys' && (
          <Panel title="API Keys" actions={<button className="btn btn-primary">+ New Key</button>}>
            <div className="space-y-2">
              {[
                { name: 'Production Key', key: 'tv2_live_************a3b4', created: '2025-01-15', lastUsed: '2m ago' },
                { name: 'Algo Trading', key: 'tv2_algo_************f8e9', created: '2025-02-22', lastUsed: '15m ago' },
                { name: 'Read-only', key: 'tv2_ro_*****7c1d', created: '2025-04-10', lastUsed: '1h ago' },
              ].map((k) => (
                <div key={k.name} className="flex items-center gap-3 p-3 bg-bg-2 rounded border border-line">
                  <Key className="h-4 w-4 text-fg-muted" />
                  <div className="flex-1">
                    <div className="text-sm font-semibold">{k.name}</div>
                    <div className="text-2xs text-fg-muted font-mono">{k.key}</div>
                  </div>
                  <div className="text-2xs text-fg-muted">
                    Created {k.created} · Used {k.lastUsed}
                  </div>
                  <button className="btn btn-ghost text-2xs">Revoke</button>
                </div>
              ))}
            </div>
          </Panel>
        )}

        {section === 'automation' && (
          <Panel title="Automation & Bots">
            <div className="grid grid-cols-2 gap-3">
              {[
                { name: 'Telegram Bot', desc: 'Send signals to your Telegram channel', enabled: true, icon: Bot },
                { name: 'Discord Webhook', desc: 'Post trades to Discord', enabled: false, icon: Globe },
                { name: 'Email Reports', desc: 'Auto-send daily performance report', enabled: true, icon: Mail },
                { name: 'Webhook (Generic)', desc: 'POST trade events to any URL', enabled: true, icon: Cloud },
                { name: 'Slack Bot', desc: 'Real-time alerts to Slack channel', enabled: false, icon: Globe },
                { name: 'Cron Jobs', desc: 'Scheduled task automation', enabled: true, icon: Bot },
              ].map((b) => {
                const Icon = b.icon
                return (
                  <div key={b.name} className="flex items-start gap-3 p-3 bg-bg-2 rounded border border-line">
                    <Icon className="h-5 w-5 text-fg-muted mt-0.5" />
                    <div className="flex-1">
                      <div className="text-sm font-semibold">{b.name}</div>
                      <div className="text-2xs text-fg-muted mt-0.5">{b.desc}</div>
                    </div>
                    <Toggle value={b.enabled} onChange={() => {}} />
                  </div>
                )
              })}
            </div>
          </Panel>
        )}
      </div>
    </div>
  )
}
