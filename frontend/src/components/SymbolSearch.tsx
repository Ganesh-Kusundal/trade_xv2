/**
 * Symbol search — type-ahead dropdown for picking a NSE / BSE symbol.
 *
 * Uses /api/v1/symbols/search in production. Falls back to a static
 * in-memory list when the backend is not running.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { Search, X, Plus } from 'lucide-react'
import { searchSymbols } from '@/api/client'
import { useAppStore } from '@/store/app'
import { cn } from '@/lib/utils'
import type { Symbol } from '@/types'

export function SymbolSearch() {
  const activeSymbol = useAppStore((s) => s.activeSymbol)
  const setActiveSymbol = useAppStore((s) => s.setActiveSymbol)
  const addToWatchlist = useAppStore((s) => s.addToWatchlist)

  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Symbol[]>([])
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  // Debounced search.
  useEffect(() => {
    if (!open) return
    const id = setTimeout(async () => {
      const r = await searchSymbols(query, 30)
      setResults(r)
      setActive(0)
    }, 80)
    return () => clearTimeout(id)
  }, [query, open])

  // Click outside to close
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('mousedown', handler)
    return () => window.removeEventListener('mousedown', handler)
  }, [open])

  const submit = (s: string) => {
    setActiveSymbol(s)
    setOpen(false)
    setQuery('')
  }

  // Keyboard
  const onKey = (e: React.KeyboardEvent) => {
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'Enter') setOpen(true)
      return
    }
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => Math.min(results.length - 1, i + 1)) }
    if (e.key === 'ArrowUp')   { e.preventDefault(); setActive((i) => Math.max(0, i - 1)) }
    if (e.key === 'Enter')     { e.preventDefault(); if (results[active]) submit(results[active].symbol) }
    if (e.key === 'Escape')    { setOpen(false); setQuery('') }
  }

  const initialList = useMemo(() => results.slice(0, 12), [results])

  return (
    <div ref={wrapRef} className="relative">
      <div
        className={cn(
          'flex items-center gap-2 h-7 px-2 border rounded-sm bg-bbg0 transition-colors min-w-[280px]',
          open ? 'border-bcy/60 ring-1 ring-bcy/30' : 'border-bline hover:border-bline2',
        )}
        onClick={() => { setOpen(true); setTimeout(() => inputRef.current?.focus(), 0) }}
      >
        <Search className="h-3.5 w-3.5 text-bfgd" />
        {open ? (
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKey}
            placeholder="Search NSE / BSE symbol (e.g. RELI)"
            className="flex-1 bg-transparent outline-none text-sm placeholder:text-bfgd"
            autoFocus
          />
        ) : (
          <span className="flex-1 text-sm font-mono num font-semibold text-bfg tracking-wide">
            {activeSymbol}
          </span>
        )}
        {open && query && (
          <button onClick={(e) => { e.stopPropagation(); setQuery('') }} className="text-bfgd hover:text-bfg">
            <X className="h-3 w-3" />
          </button>
        )}
        <span className="b-kbd">⌘K</span>
      </div>

      {open && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 b-panel rounded-sm max-h-[420px] overflow-y-auto shadow-2xl">
          {initialList.length === 0 ? (
            <div className="px-3 py-2 text-2xs text-bfgd">No matches</div>
          ) : (
            <ul className="py-1">
              {initialList.map((s, i) => (
                <li
                  key={s.symbol}
                  className={cn(
                    'flex items-center gap-2 px-2 py-1 cursor-pointer text-2xs',
                    i === active ? 'bg-bbg2 text-bfg' : 'text-bfgm hover:bg-bbg2 hover:text-bfg',
                  )}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => submit(s.symbol)}
                >
                  <span className="font-mono num font-semibold w-[68px] text-bfg">{s.symbol}</span>
                  <span className="flex-1 truncate text-bfgm">{s.name}</span>
                  <span className="text-bfgd text-[10px]">{s.exchange}</span>
                  <span className="text-bfgd text-[10px] w-[88px] text-right">{s.sector ?? '—'}</span>
                  <button
                    onClick={(e) => { e.stopPropagation(); addToWatchlist(s.symbol) }}
                    className="opacity-50 hover:opacity-100 text-bcy"
                    title="Add to watchlist"
                  >
                    <Plus className="h-3 w-3" />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="border-t border-bline px-2 py-1 text-[10px] text-bfgd flex items-center gap-3">
            <span><span className="b-kbd">↑↓</span> navigate</span>
            <span><span className="b-kbd">↵</span> select</span>
            <span><span className="b-kbd">Esc</span> close</span>
          </div>
        </div>
      )}
    </div>
  )
}
