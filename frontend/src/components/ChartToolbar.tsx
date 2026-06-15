/**
 * ChartToolbar — a compact strip of chart controls (indicators,
 * drawing tools, settings). Sits just above the chart.
 */

import { useState } from 'react'
import {
  TrendingUp, BarChart3, Hash, Activity, Settings, Maximize2, Camera,
  Crosshair, Type, Square, Eye, EyeOff,
} from 'lucide-react'
import { cn } from '@/lib/utils'

export interface ChartSettings {
  showMA: boolean
  showVolume: boolean
  crosshair: boolean
  indicators: { ema9: boolean; ema20: boolean; ema50: boolean; vwap: boolean; bb: boolean }
  theme: 'dark' | 'classic'
}

interface ChartToolbarProps {
  settings: ChartSettings
  onChange: (s: ChartSettings) => void
  bars: number
  onBarsChange: (n: number) => void
}

export function ChartToolbar({ settings, onChange, bars, onBarsChange }: ChartToolbarProps) {
  const [open, setOpen] = useState(false)

  const update = (patch: Partial<ChartSettings>) => onChange({ ...settings, ...patch })
  const toggleInd = (key: keyof ChartSettings['indicators']) =>
    update({
      indicators: { ...settings.indicators, [key]: !settings.indicators[key] },
    })

  return (
    <div className="flex items-center gap-1 px-2 h-7 border-b border-bline bg-bbg1">
      {/* Quick toggles */}
      <ToggleButton
        active={settings.showMA}
        onClick={() => update({ showMA: !settings.showMA })}
        icon={TrendingUp}
        label="MA"
      />
      <ToggleButton
        active={settings.showVolume}
        onClick={() => update({ showVolume: !settings.showVolume })}
        icon={BarChart3}
        label="VOL"
      />
      <ToggleButton
        active={settings.crosshair}
        onClick={() => update({ crosshair: !settings.crosshair })}
        icon={Crosshair}
        label="✛"
      />

      <div className="w-px h-4 bg-bline mx-1" />

      {/* Indicators dropdown */}
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'h-5 px-1.5 text-2xs font-medium rounded-sm border flex items-center gap-1',
          open
            ? 'bg-bcy/15 border-bcy/30 text-bcy'
            : 'bg-bbg2 border-bline text-bfgm hover:text-bfg',
        )}
      >
        <Activity className="h-3 w-3" />
        Indicators
        <span className="text-[10px] text-fg-dim font-mono num">
          {Object.values(settings.indicators).filter(Boolean).length}
        </span>
      </button>

      {/* Drawing tools (visual only for this build) */}
      <ToolButton icon={Crosshair} label="Cursor" active />
      <ToolButton icon={Type} label="Text" />
      <ToolButton icon={Square} label="Box" />

      <div className="flex-1" />

      {/* Bars */}
      <div className="flex items-center gap-1.5 text-2xs text-fg-dim font-mono">
        <span>bars</span>
        <select
          value={bars}
          onChange={(e) => onBarsChange(Number(e.target.value))}
          className="bg-bbg2 border border-bline rounded-sm h-5 px-1 text-2xs text-bfg font-mono num"
        >
          {[50, 100, 200, 500, 1000].map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
      </div>

      <div className="w-px h-4 bg-bline mx-1" />

      <ToolButton icon={Camera} label="Snap" />
      <ToolButton icon={Maximize2} label="Max" />
      <ToolButton icon={Settings} label="Prefs" />

      {/* Indicators popover */}
      {open && (
        <div className="absolute z-30 top-8 right-2 b-panel rounded-sm w-56 p-2 shadow-2xl">
          <div className="text-2xs uppercase tracking-wider text-fg-dim mb-1.5">Overlays</div>
          {([
            ['ema9',  'EMA 9',  'rgb(34,211,238)'],
            ['ema20', 'EMA 20', 'rgb(255,168,38)'],
            ['ema50', 'EMA 50', 'rgb(217,70,239)'],
            ['vwap',  'VWAP',   'rgb(168,85,247)'],
            ['bb',    'Bands',  'rgb(156,165,188)'],
          ] as const).map(([k, label, color]) => (
            <label
              key={k}
              className="flex items-center gap-2 px-1.5 py-1 hover:bg-bbg2 rounded cursor-pointer text-2xs"
            >
              <input
                type="checkbox"
                checked={settings.indicators[k]}
                onChange={() => toggleInd(k)}
                className="accent-bcy"
              />
              <span className="h-2 w-2 rounded-sm" style={{ background: color }} />
              <span className="flex-1 text-fg">{label}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  )
}

function ToggleButton({
  active, onClick, icon: Icon, label,
}: {
  active: boolean
  onClick: () => void
  icon: typeof TrendingUp
  label: string
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'h-5 px-1.5 text-2xs font-mono num rounded-sm border flex items-center gap-1',
        active
          ? 'bg-bcy/15 border-bcy/30 text-bcy'
          : 'bg-bbg2 border-bline text-fg-muted hover:text-fg',
      )}
    >
      <Icon className="h-3 w-3" />
      {label}
    </button>
  )
}

function ToolButton({ icon: Icon, label, active }: { icon: typeof TrendingUp; label: string; active?: boolean }) {
  return (
    <button
      title={label}
      className={cn(
        'h-5 w-5 rounded-sm flex items-center justify-center',
        active
          ? 'bg-bcy/15 text-bcy'
          : 'bg-transparent text-fg-muted hover:text-fg hover:bg-bbg2',
      )}
    >
      <Icon className="h-3 w-3" />
    </button>
  )
}
