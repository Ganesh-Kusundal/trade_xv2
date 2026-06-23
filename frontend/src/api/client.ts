/**
 * API client — talks to the Python FastAPI backend (BACKEND_API_SPEC.md).
 *
 * When VITE_REQUIRE_API=true, mock fallbacks are disabled and API errors
 * propagate to the caller (production / staging UI).
 */

import type { Candle, Quote, Timeframe, ReplaySession, ReplayEvent, Exchange } from '@/types'
import { generateCandles, generateQuote, basePrice } from '@/data/mockMarket'
import { SYMBOLS } from '@/data/symbols'

const API_BASE = '/api/v1'
const REQUIRE_API = import.meta.env.VITE_REQUIRE_API === 'true'

/** WebSocket base URL (same host as the page). */
export function getWsBaseUrl(): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}`
}

/** API key for WebSocket auth when AUTH_MODE=api_key on the backend. */
export function getApiKey(): string | undefined {
  const key = import.meta.env.VITE_API_KEY
  return key && key.length > 0 ? key : undefined
}

/** Open an authenticated market WebSocket to `/ws/market`. */
export function createMarketWebSocket(): WebSocket {
  const apiKey = getApiKey()
  const qs = apiKey ? `?api_key=${encodeURIComponent(apiKey)}` : ''
  return new WebSocket(`${getWsBaseUrl()}/ws/market${qs}`)
}

let backendUp: boolean | null = null
let lastProbeAt = 0
const PROBE_TTL_MS = 30_000 // re-probe every 30s if previously down

function allowMockFallback(): boolean {
  return !REQUIRE_API
}

async function probe(): Promise<boolean> {
  if (backendUp === true) return true
  const now = Date.now()
  if (backendUp === false && now - lastProbeAt < PROBE_TTL_MS) return false
  lastProbeAt = now
  try {
    const c = new AbortController()
    const id = setTimeout(() => c.abort(), 800)
    const r = await fetch(`${API_BASE}/health`, { signal: c.signal })
    clearTimeout(id)
    backendUp = r.ok
  } catch {
    backendUp = false
  }
  return backendUp
}

// ── Symbols ─────────────────────────────────────────────────────────────

export async function searchSymbols(q: string, limit = 25) {
  if (await probe()) {
    try {
      const r = await fetch(`${API_BASE}/symbols/search?q=${encodeURIComponent(q)}&limit=${limit}`)
      if (r.ok) return (await r.json()).results
    } catch { /* fall through to mock */ }
  }
  // Mock (disabled when VITE_REQUIRE_API=true)
  if (!allowMockFallback()) {
    throw new Error(`Backend unavailable for symbol search: ${q}`)
  }
  const needle = q.trim().toUpperCase()
  if (!needle) return SYMBOLS.slice(0, limit)
  return SYMBOLS
    .filter((s) => s.symbol.includes(needle) || s.name.toUpperCase().includes(needle))
    .slice(0, limit)
}

// ── Quote ───────────────────────────────────────────────────────────────

export async function getQuote(symbol: string, exchange: Exchange = 'NSE'): Promise<Quote> {
  if (await probe()) {
    try {
      const r = await fetch(`${API_BASE}/market/quote/${symbol}`)
      if (r.ok) return await r.json()
    } catch { /* fall through */ }
  }
  if (!allowMockFallback()) {
    throw new Error(`Backend unavailable for quote: ${symbol}`)
  }
  return generateQuote(symbol)
}

// ── Candles ─────────────────────────────────────────────────────────────

export async function getCandles(
  symbol: string,
  timeframe: Timeframe,
  bars = 200,
  exchange: Exchange = 'NSE',
): Promise<Candle[]> {
  if (await probe()) {
    try {
      const r = await fetch(
        `${API_BASE}/market/candles?symbol=${symbol}&timeframe=${timeframe}&limit=${bars}`,
      )
      if (r.ok) {
        const body = await r.json()
        if (Array.isArray(body?.candles)) return body.candles
      }
    } catch { /* fall through */ }
  }
  if (!allowMockFallback()) {
    throw new Error(`Backend unavailable for candles: ${symbol}`)
  }
  return generateCandles(symbol, timeframe, bars)
}

// ── Replay ──────────────────────────────────────────────────────────────

/**
 * List available replay sessions for a given symbol+date.
 * (Mock returns a single virtual session per (symbol, date) pair.)
 */
export async function listReplaySessions(symbol: string, date: string) {
  if (await probe()) {
    try {
      const r = await fetch(`${API_BASE}/replay/sessions?symbol=${symbol}&date=${date}`)
      if (r.ok) return (await r.json()).sessions ?? []
    } catch { /* fall through */ }
  }
  return [
    {
      id: `mock-${symbol}-${date}`,
      symbol,
      exchange: 'NSE' as Exchange,
      timeframe: '1m' as Timeframe,
      from_t: new Date(date + 'T09:15:00+05:30').getTime(),
      to_t:   new Date(date + 'T15:30:00+05:30').getTime(),
      cursor_t: new Date(date + 'T09:15:00+05:30').getTime(),
      state: 'IDLE' as const,
      speed: 1,
    },
  ]
}

export interface CreateReplayBody {
  symbol: string
  date: string
  timeframe?: Timeframe
  from_t?: number
  to_t?: number
}

export async function createReplaySession(body: CreateReplayBody): Promise<ReplaySession> {
  if (await probe()) {
    try {
      const r = await fetch(`${API_BASE}/replay/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (r.ok) return await r.json()
    } catch { /* fall through */ }
  }
  // Mock session: derive a stable ID.
  const id = `mock-${body.symbol}-${body.date}-${body.timeframe ?? '1m'}`
  const from_t = body.from_t ?? new Date(body.date + 'T09:15:00+05:30').getTime()
  const to_t   = body.to_t   ?? new Date(body.date + 'T15:30:00+05:30').getTime()
  return {
    id,
    symbol: body.symbol,
    exchange: 'NSE',
    timeframe: body.timeframe ?? '1m',
    from_t,
    to_t,
    cursor_t: from_t,
    state: 'IDLE',
    speed: 1,
  }
}

export type ReplayAction =
  | { action: 'play' }
  | { action: 'pause' }
  | { action: 'step'; n?: number }
  | { action: 'seek'; to_t: number }
  | { action: 'set_speed'; speed: number }

export async function controlReplay(id: string, body: ReplayAction): Promise<ReplaySession> {
  if (await probe()) {
    try {
      const r = await fetch(`${API_BASE}/replay/sessions/${id}/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (r.ok) return await r.json()
    } catch { /* fall through */ }
  }
  // Mock: no-op success; the WebSocket-style subscription below drives
  // the visible behaviour.
  const [_, sym, date, tf] = id.split('-')
  return {
    id, symbol: sym, exchange: 'NSE', timeframe: (tf ?? '1m') as Timeframe,
    from_t: new Date(date + 'T09:15:00+05:30').getTime(),
    to_t:   new Date(date + 'T15:30:00+05:30').getTime(),
    cursor_t: new Date(date + 'T09:15:00+05:30').getTime(),
    state: body.action === 'play' ? 'PLAYING' : body.action === 'pause' ? 'PAUSED' : 'IDLE',
    speed: (body as any).speed ?? 1,
  }
}

/**
 * Subscribe to a replay stream. Returns an unsubscribe function.
 *
 * If the backend is reachable we open `/ws/replay/{id}`. Otherwise we
 * drive a local in-process emitter over a pre-fetched history of
 * candles and emit them on a timer at the chosen speed.
 */
export function subscribeReplay(
  session: ReplaySession,
  onEvent: (e: ReplayEvent) => void,
): () => void {
  if (backendUp) {
    // Real WS — assume the backend is up if the probe was positive.
    try {
      const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/replay/${session.id}`
      const ws = new WebSocket(url)
      ws.onmessage = (msg) => {
        try { onEvent(JSON.parse(msg.data)) } catch { /* ignore */ }
      }
      ws.onerror = () => onEvent({ type: 'error', code: 'WS_ERROR', message: 'WebSocket error' })
      return () => { try { ws.close() } catch { /* ignore */ } }
    } catch { /* fall through to mock */ }
  }
  return subscribeReplayMock(session, onEvent)
}

function subscribeReplayMock(session: ReplaySession, onEvent: (e: ReplayEvent) => void): () => void {
  // Pre-generate the day's candles for the requested timeframe.
  const base = basePrice(session.symbol)
  const dateISO = new Date(session.from_t).toISOString().slice(0, 10)
  // Generate 1m candles from session.from_t to session.to_t (one trading day).
  const oneMin = 60_000
  const totalBars = Math.min(380, Math.floor((session.to_t - session.from_t) / oneMin))
  // Use the helper to generate a contiguous walk.
  const generated = generateCandles(session.symbol, session.timeframe, totalBars, session.to_t)
  // Rescale them to fit the requested time range.
  const span = session.to_t - session.from_t
  const candles: Candle[] = generated.map((c, i) => ({
    ...c,
    t: session.from_t + Math.floor((i / generated.length) * span),
  }))

  let cursor = 0
  let playing = false
  let speed = session.speed
  let timer: number | null = null
  let lastTick = 0

  const tick = () => {
    if (!playing) return
    const now = performance.now()
    const elapsed = now - lastTick
    // Advance ~1 candle per 200ms at 1x; scale by speed.
    const msPerCandle = Math.max(20, 200 / speed)
    if (elapsed < msPerCandle) {
      timer = window.setTimeout(tick, msPerCandle - elapsed)
      return
    }
    lastTick = now
    if (cursor >= candles.length) {
      onEvent({ type: 'replay_state', session_id: session.id, state: 'ENDED', speed, cursor_t: session.to_t })
      playing = false
      return
    }
    const c = candles[cursor++]
    onEvent({ type: 'replay_candle', session_id: session.id, candle: c })
    onEvent({ type: 'replay_state', session_id: session.id, state: 'PLAYING', speed, cursor_t: c.t })
    timer = window.setTimeout(tick, msPerCandle)
  }

  // Start: emit the first state so the UI knows.
  onEvent({ type: 'replay_state', session_id: session.id, state: 'IDLE', speed, cursor_t: session.from_t })

  // Public commands through a global registry so the UI can drive
  // play/pause/seek/speed without owning the timer.
  const id = session.id
  const handler = (ev: Event) => {
    const detail = (ev as CustomEvent).detail as { action: string; to_t?: number; speed?: number }
    if (!detail) return
    switch (detail.action) {
      case 'play':
        playing = true
        lastTick = performance.now()
        onEvent({ type: 'replay_state', session_id: id, state: 'PLAYING', speed, cursor_t: candles[Math.max(0, cursor - 1)]?.t ?? session.from_t })
        tick()
        break
      case 'pause':
        playing = false
        if (timer) { clearTimeout(timer); timer = null }
        onEvent({ type: 'replay_state', session_id: id, state: 'PAUSED', speed, cursor_t: candles[Math.max(0, cursor - 1)]?.t ?? session.from_t })
        break
      case 'seek': {
        if (timer) { clearTimeout(timer); timer = null }
        playing = false
        const target = detail.to_t ?? session.from_t
        // Find the first candle index at or after the target.
        cursor = candles.findIndex((c) => c.t >= target)
        if (cursor < 0) cursor = candles.length
        onEvent({ type: 'replay_state', session_id: id, state: 'PAUSED', speed, cursor_t: target })
        // Emit a single "current" candle so the chart updates.
        if (cursor > 0) onEvent({ type: 'replay_candle', session_id: id, candle: candles[cursor - 1] })
        break
      }
      case 'set_speed':
        speed = Math.max(0.25, Math.min(128, detail.speed ?? 1))
        onEvent({ type: 'replay_state', session_id: id, state: playing ? 'PLAYING' : 'PAUSED', speed, cursor_t: candles[Math.max(0, cursor - 1)]?.t ?? session.from_t })
        break
    }
  }
  window.addEventListener(`replay-cmd:${id}`, handler as EventListener)

  return () => {
    playing = false
    if (timer) clearTimeout(timer)
    window.removeEventListener(`replay-cmd:${id}`, handler as EventListener)
  }
}

/** Convenience: drive a local mock replay from the UI. */
export function dispatchReplayCommand(
  id: string,
  cmd: { action: 'play' | 'pause' | 'seek' | 'set_speed'; to_t?: number; speed?: number },
) {
  window.dispatchEvent(new CustomEvent(`replay-cmd:${id}`, { detail: cmd }))
}
