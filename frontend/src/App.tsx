/**
 * App — top-level Bloomberg-style layout.
 *
 *   ┌────────────────────────────────────────────────────────────────────┐
 *   │  TopBar                                                            │
 *   ├──────────┬─────────────────────────────────────┬────────────────────┤
 *   │ Sidebar  │  ChartPanel                         │ TimeAndSales        │
 *   │ (watch)  │  ┌─ ChartToolbar ────────────────┐  │                    │
 *   │          │  │       CandlestickChart         │  ├────────────────────┤
 *   │          │  └────────────────────────────────┘  │ MarketDepth        │
 *   ├──────────┴─────────────────────────────────────┴────────────────────┤
 *   │  NewsTicker                                                        │
 *   ├────────────────────────────────────────────────────────────────────┤
 *   │  CommandBar                                                        │
 *   ├────────────────────────────────────────────────────────────────────┤
 *   │  FunctionKeyBar                                                    │
 *   ├────────────────────────────────────────────────────────────────────┤
 *   │  Footer                                                            │
 *   └────────────────────────────────────────────────────────────────────┘
 */

import { useState } from 'react'
import { TopBar } from './components/TopBar'
import { Sidebar } from './components/Sidebar'
import { ChartPanel } from './components/ChartPanel'
import { TimeAndSales } from './components/TimeAndSales'
import { MarketDepth } from './components/MarketDepth'
import { NewsTicker } from './components/NewsTicker'
import { CommandBar } from './components/CommandBar'
import { FunctionKeyBar } from './components/FunctionKeyBar'
import { useAppStore } from './store/app'
import { searchSymbols } from './api/client'

type RightPanel = 'tns' | 'depth' | 'both'

export function App() {
  const setActiveSymbol = useAppStore((s) => s.setActiveSymbol)
  const setReplayOpen   = useAppStore((s) => s.setReplayOpen)
  const activeSymbol    = useAppStore((s) => s.activeSymbol)

  const [activeFn, setActiveFn] = useState<string | null>(null)
  const [rightPanel, setRightPanel] = useState<RightPanel>('both')

  /** Handle a command typed in the CommandBar. Returns a string if handled,
   *  or `undefined` to signal "treat it as a symbol search". */
  const onCommand = (raw: string): string | void => {
    const cmd = raw.trim().toUpperCase()
    if (!cmd) return ''
    if (cmd === 'GP') { window.alert('Go to Portfolio — not implemented in this build.'); return '' }
    if (cmd === 'HP') { window.alert('Heatmap — not implemented in this build.'); return '' }
    if (cmd === 'ECHO') { window.alert('Equity Curve — not implemented in this build.'); return '' }
    if (cmd === 'TOP') { window.alert('Top Movers — not implemented in this build.'); return '' }
    if (cmd === 'REPLAY') { setReplayOpen(true); return '' }
    if (cmd === 'HELP' || cmd === '?') { window.alert(openHelp()); return '' }
    if (cmd === 'CLEAR' || cmd === 'CLS') { return '' }
    if (cmd === 'T&S') { setRightPanel('tns'); return '' }
    if (cmd === 'DEPTH') { setRightPanel('depth'); return '' }
    if (cmd === 'CHART') { setRightPanel('both'); return '' }
    // If it looks like a symbol, let onSearch handle it.
    if (/^[A-Z0-9&\-]{1,12}$/.test(cmd)) return undefined
    window.alert(`Unknown command: ${raw}`)
    return ''
  }

  const onSearch = async (q: string) => {
    const r = await searchSymbols(q, 1)
    if (r.length > 0) setActiveSymbol(r[0].symbol)
    else window.alert(`No symbol matches "${q}"`)
  }

  const onFnKey = (id: string) => {
    setActiveFn(id)
    if (id === 'F5') setRightPanel('depth')
    else if (id === 'F6') setRightPanel('tns')
    else if (id === 'F4') setRightPanel('both')
    window.setTimeout(() => setActiveFn((cur) => (cur === id ? null : cur)), 1200)
  }

  return (
    <div className="h-screen w-screen flex flex-col bg-bbg text-bfg overflow-hidden">
      <TopBar />
      <div className="flex-1 min-h-0 flex">
        <Sidebar />
        <div className="flex-1 min-w-0 min-h-0 flex flex-col">
          <ChartPanel />
        </div>
        <div className="w-[340px] flex-shrink-0 border-l border-bline bg-bbg0 flex flex-col">
          {(rightPanel === 'both' || rightPanel === 'tns') && (
            <TimeAndSales symbol={activeSymbol} height={rightPanel === 'tns' ? undefined : 280} />
          )}
          {rightPanel === 'both' && <div className="h-1.5" />}
          {(rightPanel === 'both' || rightPanel === 'depth') && (
            <MarketDepth symbol={activeSymbol} height={rightPanel === 'depth' ? undefined : 360} />
          )}
        </div>
      </div>
      <NewsTicker />
      <CommandBar onCommand={onCommand} onSearch={onSearch} />
      <FunctionKeyBar onCommand={onFnKey} activePanel={
        rightPanel === 'tns' ? 'tns' : rightPanel === 'depth' ? 'depth' : 'chart'
      } />
      <footer className="h-6 px-2 flex items-center justify-between border-t border-bline bg-bbg1 text-[10px] font-mono num text-fgd">
        <div className="flex items-center gap-3">
          <span className="text-bamb font-semibold">TradeXV2</span>
          <span>v3.0.0</span>
        </div>
        <div className="flex items-center gap-3">
          <span>Build: 2026-06-14</span>
          <span>·</span>
          <span>Backend: <span className="text-fg">auto-detect (mock fallback)</span></span>
          <span>·</span>
          <span>Press <span className="b-kbd">/</span> to focus command bar</span>
        </div>
      </footer>
    </div>
  )
}

function openHelp(): string {
  return [
    'TradeXV2 — Quick help',
    '',
    'Keyboard:',
    '  /            focus command bar',
    '  ⌘K / Ctrl+K  open symbol search',
    '  Alt+F1-F12   trigger function keys',
    '  Esc          close popovers',
    '',
    'Commands (type in the GO bar):',
    '  REPLAY       open the replay panel',
    '  T&S          show only time & sales',
    '  DEPTH        show only market depth',
    '  CHART        show both side panels',
    '  GP / HP / ECHO / TOP   shortcuts (n/a in this build)',
    '  HELP / ?     this message',
    '  <SYMBOL>     open that symbol, e.g. RELIANCE',
  ].join('\n')
}
