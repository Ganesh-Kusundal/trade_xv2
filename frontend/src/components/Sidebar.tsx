/**
 * Sidebar — vertical nav + watchlist (left rail).
 *
 * Click a watchlist row to switch the active symbol. The watchlist
 * is persisted to localStorage via the app store.
 */

import { useState, useEffect } from 'react'
import { Star, X, Activity } from 'lucide-react'
import { useAppStore } from '@/store/app'
import { getQuote } from '@/api/client'
import { cn, formatIN, formatPercent, pnlColor } from '@/lib/utils'
import type { Quote } from '@/types'

export function Sidebar() {
  const watchlist = useAppStore((s) => s.watchlist)
  const active = useAppStore((s) => s.activeSymbol)
  const setActive = useAppStore((s) => s.setActiveSymbol)
  const remove = useAppStore((s) => s.removeFromWatchlist)
  const [quotes, setQuotes] = useState<Record<string, Quote | null>>({})

  useEffect(() => {
    let alive = true
    const tick = async () => {
      const out: Record<string, Quote | null> = {}
      await Promise.all(
        watchlist.map(async (s) => {
          try { out[s] = await getQuote(s) } catch { out[s] = null }
        }),
      )
      if (alive) setQuotes(out)
    }
    tick()
    const id = window.setInterval(tick, 3000)
    return () => { alive = false; clearInterval(id) }
  }, [watchlist])

  return (
    <aside className="w-64 border-r border-bline bg-bbg1 flex flex-col min-h-0">
      {/* Section title */}
      <div className="flex items-center justify-between px-2 h-7 border-b border-bline bg-bbg2">
        <div className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wider text-bfgm">
          <Star className="h-3 w-3 text-bamb" /> Watchlist
        </div>
        <span className="text-[10px] font-mono num text-bfgd">{watchlist.length}</span>
      </div>

      {/* Header row */}
      <div className="grid grid-cols-[1fr_64px_56px] px-2 py-1 text-[10px] uppercase tracking-wider text-bfgd border-b border-bline">
        <span>Symbol</span>
        <span className="text-right">LTP</span>
        <span className="text-right">Chg%</span>
      </div>

      {/* Rows */}
      <ul className="flex-1 overflow-y-auto">
        {watchlist.map((s) => {
          const q = quotes[s]
          const isActive = s === active
          return (
            <li
              key={s}
              onClick={() => setActive(s)}
              className={cn(
                'group grid grid-cols-[1fr_64px_56px_18px] items-center gap-1 px-2 py-1 cursor-pointer border-b border-bline-subtle text-2xs',
                isActive ? 'bg-bamb/10 text-bfg' : 'text-bfgm hover:bg-bbg2 hover:text-bfg',
              )}
            >
              <div className="flex items-center gap-1.5 min-w-0">
                <span className={cn(
                  'h-1.5 w-1.5 rounded-full',
                  q ? (q.change >= 0 ? 'bg-bull' : 'bg-bear') : 'bg-bfgd',
                )} />
                <span className={cn('font-mono num font-semibold truncate', isActive && 'text-bfg')}>
                  {s}
                </span>
              </div>
              <span className="font-mono num text-right">
                {q ? formatIN(q.ltp) : '—'}
              </span>
              <span className={cn('font-mono num text-right', q ? pnlColor(q.changePct) : '')}>
                {q ? formatPercent(q.changePct) : '—'}
              </span>
              <button
                onClick={(e) => { e.stopPropagation(); remove(s) }}
                className="opacity-0 group-hover:opacity-100 text-bfgd hover:text-bear"
                title="Remove from watchlist"
              >
                <X className="h-3 w-3" />
              </button>
            </li>
          )
        })}
        {watchlist.length === 0 && (
          <li className="px-2 py-4 text-center text-2xs text-bfgd">
            Empty. Use ⌘K to add symbols.
          </li>
        )}
      </ul>

      {/* Footer */}
      <div className="border-t border-bline px-2 py-1.5 text-[10px] text-bfgd flex items-center gap-1.5">
        <Activity className="h-3 w-3 text-bcy" />
        <span className="font-mono num">Auto-refresh 3s</span>
      </div>
    </aside>
  )
}
