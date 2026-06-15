/**
 * CommandBar — Bloomberg-style "GO" command line at the bottom.
 *
 *   GO > RELIANCE EQUITY <Enter>
 *   GO > HP <Enter>            (show heatmap)
 *   GO > GP <Enter>            (go to portfolio)
 *
 * Also handles "/" as a global hotkey to focus the bar.
 */

import { useEffect, useRef, useState } from 'react'
import { ChevronRight, History, X } from 'lucide-react'
import { cn } from '@/lib/utils'

interface CommandBarProps {
  onCommand: (cmd: string) => string | void
  onSearch: (q: string) => void
}

const SUGGESTIONS = [
  { cmd: 'GP',          desc: 'Go to Portfolio' },
  { cmd: 'HP',          desc: 'Heatmap' },
  { cmd: 'ECHO',        desc: 'Equity curve' },
  { cmd: 'TOP',         desc: 'Top movers' },
  { cmd: 'NSE',         desc: 'Switch exchange' },
  { cmd: 'RELIANCE',    desc: 'Open RELIANCE chart' },
  { cmd: 'NIFTY',       desc: 'Open NIFTY 50 chart' },
  { cmd: 'BANKNIFTY',   desc: 'Open BANKNIFTY chart' },
  { cmd: 'HELP',        desc: 'Show help' },
  { cmd: 'REPLAY',      desc: 'Open replay panel' },
]

export function CommandBar({ onCommand, onSearch }: CommandBarProps) {
  const [value, setValue] = useState('')
  const [history, setHistory] = useState<string[]>(['RELIANCE', 'NIFTY'])
  const [showHistory, setShowHistory] = useState(false)
  const [matched, setMatched] = useState<typeof SUGGESTIONS>([])
  const [feedback, setFeedback] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const q = value.trim().toUpperCase()
    if (!q) { setMatched([]); return }
    setMatched(SUGGESTIONS.filter((s) => s.cmd.startsWith(q) || s.cmd.includes(q)).slice(0, 5))
  }, [value])

  // Global hotkey: "/" focuses the bar, "Escape" clears
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      const isInput = t.tagName === 'INPUT' || t.tagName === 'TEXTAREA'
      if (e.key === '/' && !isInput) {
        e.preventDefault()
        inputRef.current?.focus()
      } else if (e.key === 'Escape' && document.activeElement === inputRef.current) {
        ;(e.target as HTMLInputElement).blur()
        setValue('')
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const submit = (raw?: string) => {
    const cmd = (raw ?? value).trim()
    if (!cmd) return
    setHistory((h) => [cmd, ...h.filter((x) => x !== cmd)].slice(0, 10))
    // First, try a command match
    const ret = onCommand(cmd)
    // If it didn't handle it, treat it as a symbol search
    if (ret === undefined) {
      onSearch(cmd)
    }
    setValue('')
    inputRef.current?.blur()
  }

  return (
    <div className="flex items-stretch h-7 border-t border-bline bg-bbg1 relative">
      {/* GO prompt */}
      <div className="flex items-center gap-1 px-2 border-r border-bline bg-bbg2 text-bamb font-mono num text-2xs font-semibold tracking-wider">
        <ChevronRight className="h-3 w-3" />
        GO
      </div>

      {/* Input */}
      <div className="flex-1 flex items-center gap-2 px-2 relative">
        <input
          ref={inputRef}
          value={value}
          onChange={(e) => { setValue(e.target.value); setShowHistory(false) }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submit()
            if (e.key === 'ArrowUp' && history.length) { e.preventDefault(); setValue(history[0]) }
          }}
          onFocus={() => setShowHistory(true)}
          onBlur={() => setTimeout(() => setShowHistory(false), 150)}
          placeholder="Type a command or symbol (e.g. RELIANCE, NIFTY, GP, REPLAY, HELP) — press / to focus"
          className="flex-1 bg-transparent text-2xs font-mono text-bfg outline-none placeholder:text-bfgd"
        />
        {value && (
          <button
            onClick={() => setValue('')}
            className="text-bfgd hover:text-bfg"
            title="Clear"
          >
            <X className="h-3 w-3" />
          </button>
        )}
        {feedback && (
          <span className="text-2xs text-bull font-mono num">{feedback}</span>
        )}
        <span className="text-[10px] text-bfgd font-mono">
          <span className="b-kbd">/</span> focus
          <span className="b-kbd ml-1">↵</span> run
        </span>
      </div>

      {/* History button */}
      <button
        onClick={() => setShowHistory((v) => !v)}
        className="px-2 border-l border-bline bg-bbg2 text-bfgm hover:text-bfg hover:bg-bbg3 flex items-center gap-1 text-2xs"
        title="Recent commands"
      >
        <History className="h-3 w-3" />
        <span className="font-mono num">{history.length}</span>
      </button>

      {/* Dropdown */}
      {(showHistory || matched.length > 0) && (
        <div className="absolute z-40 left-[52px] right-[60px] bottom-full mb-1 b-panel rounded-sm max-h-[300px] overflow-y-auto">
          {matched.length > 0 && (
            <ul className="py-1">
              <li className="px-2 py-0.5 text-[10px] uppercase tracking-wider text-bfgd border-b border-bline">
                Suggestions
              </li>
              {matched.map((s) => (
                <li
                  key={s.cmd}
                  onMouseDown={() => submit(s.cmd)}
                  className="px-2 py-1 cursor-pointer text-2xs hover:bg-bbg2 flex items-center gap-2"
                >
                  <span className="font-mono num font-semibold text-bamb w-20">{s.cmd}</span>
                  <span className="text-bfgm">{s.desc}</span>
                </li>
              ))}
            </ul>
          )}
          {showHistory && history.length > 0 && (
            <ul className="py-1 border-t border-bline">
              <li className="px-2 py-0.5 text-[10px] uppercase tracking-wider text-bfgd">
                Recent
              </li>
              {history.map((h, i) => (
                <li
                  key={i}
                  onMouseDown={() => submit(h)}
                  className="px-2 py-1 cursor-pointer text-2xs hover:bg-bbg2 flex items-center gap-2"
                >
                  <History className="h-3 w-3 text-bfgd" />
                  <span className="font-mono num text-bfgm">{h}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
