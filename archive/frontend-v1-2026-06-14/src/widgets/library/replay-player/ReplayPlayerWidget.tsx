import { WidgetFrame } from '../../WidgetFrame'
import { useWidgetData } from '../../useWidgetData'
import { Pill } from '@/components/ui/Pill'
import { cn, formatIN } from '@/lib/utils'
import type { WidgetProps } from '../../Widget'
import { Play, Pause } from 'lucide-react'
import { useState } from 'react'

interface ReplayConfig {
  symbol?: string
  date?: string
}

export default function ReplayPlayerWidget({ config, refresh, loading, lastUpdated }: WidgetProps<ReplayConfig>) {
  const [playing, setPlaying] = useState(false)
  const [time, setTime] = useState(50)

  return (
    <WidgetFrame id="" config={config} loading={loading} lastUpdated={lastUpdated} refresh={refresh}>
      <div className="p-3 space-y-2">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPlaying(!playing)}
            className="h-9 w-9 rounded-full bg-brand text-white flex items-center justify-center hover:bg-brand-600"
          >
            {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4 ml-0.5" />}
          </button>
          <div className="flex-1">
            <input
              type="range"
              min={0}
              max={100}
              value={time}
              onChange={(e) => setTime(+e.target.value)}
              className="w-full accent-brand"
            />
            <div className="flex items-center justify-between text-2xs text-fg-dim mt-0.5">
              <span>09:15</span>
              <span className="font-mono num">{time}%</span>
              <span>15:30</span>
            </div>
          </div>
        </div>
        <div className="grid grid-cols-4 gap-1 text-2xs">
          {[0.5, 1, 2, 5].map((s) => (
            <button key={s} className="h-6 bg-bg-2 hover:bg-bg-3 rounded font-mono num">{s}x</button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2 text-2xs pt-2 border-t border-line">
          <div>
            <div className="text-fg-dim">Symbol</div>
            <div className="font-semibold text-fg">{config.symbol || 'RELIANCE'}</div>
          </div>
          <div>
            <div className="text-fg-dim">Date</div>
            <div className="font-semibold text-fg">{config.date || '2024-12-30'}</div>
          </div>
        </div>
      </div>
    </WidgetFrame>
  )
}
