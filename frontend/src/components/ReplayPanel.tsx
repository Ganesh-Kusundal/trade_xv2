/**
 * ReplayPanel — date picker + play/pause/seek/speed controls.
 *
 * Drives a `ReplaySession` from the API client. In mock mode (no
 * backend) it emits candles locally through the in-process emitter
 * defined in `api/client.ts`.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Play, Pause, StepBack, StepForward, Rewind, FastForward,
  Calendar, X, Loader2, AlertCircle,
} from 'lucide-react'
import {
  createReplaySession,
  controlReplay,
  subscribeReplay,
  type ReplayAction,
} from '@/api/client'
import type { ReplaySession, ReplayState, Candle } from '@/types'
import { formatTime, cn } from '@/lib/utils'

const SPEEDS = [1, 4, 16, 64, 128] as const

interface ReplayPanelProps {
  symbol: string
  /** When the panel is open, the parent calls this to receive candles. */
  onCandle: (c: Candle) => void
  /** When the parent is showing a live chart, it can also receive state events. */
  onState: (s: { state: ReplayState; speed: number; cursor_t: number }) => void
  onClose: () => void
}

export function ReplayPanel({ symbol, onCandle, onState, onClose }: ReplayPanelProps) {
  const [date, setDate] = useState<string>(() => isoToday())
  const [session, setSession] = useState<ReplaySession | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [state, setState] = useState<ReplayState>('IDLE')
  const [speed, setSpeed] = useState<number>(1)
  const [cursorT, setCursorT] = useState<number>(0)
  const [progress, setProgress] = useState(0) // 0..1

  const sessionRef = useRef<ReplaySession | null>(null)
  const unsubRef = useRef<null | (() => void)>(null)

  // Open / refresh session when symbol or date changes
  useEffect(() => {
    let cancelled = false
    setBusy(true)
    setError(null)
    setSession(null)
    setState('IDLE')
    setProgress(0)
    setCursorT(0)
    if (unsubRef.current) { unsubRef.current(); unsubRef.current = null }
    createReplaySession({ symbol, date, timeframe: '1m' })
      .then((s) => {
        if (cancelled) return
        sessionRef.current = s
        setSession(s)
        setCursorT(s.from_t)
        // Subscribe.
        unsubRef.current = subscribeReplay(s, (ev) => {
          if (ev.type === 'replay_candle' && ev.candle) {
            onCandle(ev.candle)
            setCursorT(ev.candle.t)
            if (s.to_t > s.from_t) {
              setProgress(Math.min(1, (ev.candle.t - s.from_t) / (s.to_t - s.from_t)))
            }
          } else if (ev.type === 'replay_state') {
            if (ev.state) {
              setState(ev.state)
              onState({ state: ev.state, speed: ev.speed ?? speed, cursor_t: ev.cursor_t ?? cursorT })
            }
            if (ev.speed) setSpeed(ev.speed)
            if (typeof ev.cursor_t === 'number') setCursorT(ev.cursor_t)
          } else if (ev.type === 'error') {
            setError(ev.message ?? ev.code ?? 'Replay error')
          }
        })
      })
      .catch((e) => !cancelled && setError(String(e)))
      .finally(() => !cancelled && setBusy(false))
    return () => {
      cancelled = true
      if (unsubRef.current) { unsubRef.current(); unsubRef.current = null }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, date])

  const onCommand = async (action: ReplayAction) => {
    if (!session) return
    try {
      const updated = await controlReplay(session.id, action)
      setSession((prev) => (prev ? { ...prev, ...updated } : updated))
    } catch { /* ignore */ }
  }

  const onScrub = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!session) return
    const t = session.from_t + Number(e.target.value) * (session.to_t - session.from_t)
    onCommand({ action: 'seek', to_t: t })
  }

  const totalSpan = session ? Math.max(1, session.to_t - session.from_t) : 1

  return (
    <div className="b-panel rounded-sm">
      {/* Header */}
      <div className="flex items-center justify-between px-2 py-1.5 border-b border-bline bg-bbg2">
        <div className="flex items-center gap-2">
          <span className="text-2xs font-semibold uppercase tracking-wider text-bamb">REPLAY</span>
          <span className="text-2xs text-bfgm font-mono num">{symbol}</span>
          <span className={cn(
            'text-[10px] px-1.5 py-0.5 rounded font-mono num uppercase',
            state === 'PLAYING' ? 'bg-bull/20 text-bull' :
            state === 'PAUSED'  ? 'bg-warning/20 text-warning' :
            state === 'ENDED'   ? 'bg-bear/20 text-bear' :
            'bg-bbg3 text-bfgd',
          )}>
            {state}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <DatePicker value={date} onChange={setDate} />
          <button onClick={onClose} className="text-bfgd hover:text-bfg"><X className="h-3.5 w-3.5" /></button>
        </div>
      </div>

      {/* Body */}
      <div className="px-2 py-2 flex flex-col gap-2">
        {busy && (
          <div className="flex items-center gap-2 text-2xs text-bfgm">
            <Loader2 className="h-3 w-3 animate-spin" /> Loading session…
          </div>
        )}
        {error && (
          <div className="flex items-center gap-2 text-2xs text-bear">
            <AlertCircle className="h-3 w-3" /> {error}
          </div>
        )}

        {session && (
          <>
            {/* Transport */}
            <div className="flex items-center gap-1.5">
              <TransportButton
                title="Rewind to start"
                onClick={() => onCommand({ action: 'seek', to_t: session.from_t })}
                disabled={state === 'IDLE'}
              >
                <Rewind className="h-3.5 w-3.5" />
              </TransportButton>
              <TransportButton
                title="Step back (1m)"
                onClick={() => onCommand({ action: 'seek', to_t: Math.max(session.from_t, cursorT - 60_000) })}
                disabled={state === 'IDLE'}
              >
                <StepBack className="h-3.5 w-3.5" />
              </TransportButton>
              <TransportButton
                title={state === 'PLAYING' ? 'Pause' : 'Play'}
                primary
                onClick={() => onCommand({ action: state === 'PLAYING' ? 'pause' : 'play' })}
                disabled={state === 'ENDED'}
              >
                {state === 'PLAYING' ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              </TransportButton>
              <TransportButton
                title="Step forward (1m)"
                onClick={() => onCommand({ action: 'step' })}
                disabled={state === 'ENDED'}
              >
                <StepForward className="h-3.5 w-3.5" />
              </TransportButton>
              <TransportButton
                title="Skip to end"
                onClick={() => onCommand({ action: 'seek', to_t: session.to_t })}
                disabled={state === 'ENDED'}
              >
                <FastForward className="h-3.5 w-3.5" />
              </TransportButton>

              <div className="w-px h-5 bg-bline mx-1" />

              <div className="flex items-center gap-0.5 text-2xs">
                {SPEEDS.map((s) => (
                  <button
                    key={s}
                    onClick={() => onCommand({ action: 'set_speed', speed: s })}
                    className={cn(
                      'h-5 px-1.5 rounded-sm font-mono num text-[10px] border',
                      speed === s
                        ? 'bg-bcy/15 border-bcy/40 text-bcy'
                        : 'bg-bbg2 border-bline text-bfgm hover:text-bfg',
                    )}
                    title={`Set playback speed to ${s}×`}
                  >
                    {s}×
                  </button>
                ))}
              </div>
            </div>

            {/* Scrub bar */}
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-bfgd font-mono num w-12 text-right">
                {formatTime(session.from_t, false)}
              </span>
              <input
                type="range"
                min={0}
                max={totalSpan}
                step={60_000}
                value={Math.max(0, cursorT - session.from_t)}
                onChange={onScrub}
                className="flex-1 accent-bcy"
                disabled={state === 'ENDED'}
              />
              <span className="text-[10px] text-bfgd font-mono num w-12">
                {formatTime(session.to_t, false)}
              </span>
            </div>

            {/* Status row */}
            <div className="flex items-center justify-between text-[10px] text-bfgd font-mono num">
              <span>Cursor {formatTime(cursorT)}</span>
              <span>{(progress * 100).toFixed(1)}%</span>
              <span>Speed {speed}×</span>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function TransportButton({
  children, onClick, title, primary, disabled,
}: {
  children: React.ReactNode
  onClick: () => void
  title: string
  primary?: boolean
  disabled?: boolean
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      disabled={disabled}
      className={cn(
        'h-7 w-7 inline-flex items-center justify-center rounded-sm border transition-colors',
        primary
          ? 'bg-bamb/15 border-bamb/40 text-bamb hover:bg-bamb/25'
          : 'bg-bbg2 border-bline text-bfgm hover:text-bfg hover:border-bline2',
        disabled && 'opacity-40 cursor-not-allowed hover:border-bline',
      )}
    >
      {children}
    </button>
  )
}

function DatePicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex items-center gap-1 px-1.5 h-6 bg-bbg2 border border-bline rounded-sm">
      <Calendar className="h-3 w-3 text-bfgd" />
      <input
        type="date"
        value={value}
        max={isoToday()}
        onChange={(e) => onChange(e.target.value)}
        className="bg-transparent text-2xs font-mono num text-bfg outline-none"
      />
    </div>
  )
}

function isoToday(): string {
  const d = new Date()
  return d.toISOString().slice(0, 10)
}
