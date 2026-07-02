/**
 * API client — talks to the Python FastAPI backend (BACKEND_API_SPEC.md).
 */

import type { Candle, Quote, Timeframe, ReplaySession, ReplayEvent, Exchange } from '@/types'

const API_BASE = '/api/v1'

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

// ── Symbols ─────────────────────────────────────────────────────────────

export async function searchSymbols(q: string, limit = 25) {
  const r = await fetch(`${API_BASE}/symbols/search?q=${encodeURIComponent(q)}&limit=${limit}`)
  if (!r.ok) throw new Error(`Failed to search symbols: ${q}`)
  return (await r.json()).results
}

// ── Quote ───────────────────────────────────────────────────────────────

export async function getQuote(symbol: string, exchange: Exchange = 'NSE'): Promise<Quote> {
  const r = await fetch(`${API_BASE}/market/quote/${symbol}`)
  if (!r.ok) throw new Error(`Failed to fetch quote: ${symbol}`)
  return await r.json()
}

// ── Candles ─────────────────────────────────────────────────────────────

export async function getCandles(
  symbol: string,
  timeframe: Timeframe,
  bars = 200,
  exchange: Exchange = 'NSE',
  signal?: AbortSignal,
): Promise<Candle[]> {
  const r = await fetch(
    `${API_BASE}/market/candles?symbol=${symbol}&timeframe=${timeframe}&limit=${bars}`,
    { signal },
  )
  if (!r.ok) throw new Error(`Failed to fetch candles: ${symbol}`)
  const body = await r.json()
  if (!Array.isArray(body?.candles)) throw new Error(`Invalid candles response: ${symbol}`)
  return body.candles
}

// ── Replay ──────────────────────────────────────────────────────────────

export async function listReplaySessions(symbol: string, date: string) {
  const r = await fetch(`${API_BASE}/replay/sessions?symbol=${symbol}&date=${date}`)
  if (!r.ok) throw new Error(`Failed to list replay sessions: ${symbol}`)
  return (await r.json()).sessions ?? []
}

export interface CreateReplayBody {
  symbol: string
  date: string
  timeframe?: Timeframe
  from_t?: number
  to_t?: number
}

export async function createReplaySession(body: CreateReplayBody): Promise<ReplaySession> {
  const r = await fetch(`${API_BASE}/replay/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`Failed to create replay session: ${body.symbol}`)
  return await r.json()
}

export type ReplayAction =
  | { action: 'play' }
  | { action: 'pause' }
  | { action: 'step'; n?: number }
  | { action: 'seek'; to_t: number }
  | { action: 'set_speed'; speed: number }

export async function controlReplay(id: string, body: ReplayAction): Promise<ReplaySession> {
  const r = await fetch(`${API_BASE}/replay/sessions/${id}/control`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`Failed to control replay: ${id}`)
  return await r.json()
}

/**
 * Subscribe to a replay stream. Returns an unsubscribe function.
 */
export function subscribeReplay(
  session: ReplaySession,
  onEvent: (e: ReplayEvent) => void,
): () => void {
  const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/replay/${session.id}`
  const ws = new WebSocket(url)
  ws.onmessage = (msg) => {
    try { onEvent(JSON.parse(msg.data)) } catch { /* ignore */ }
  }
  ws.onerror = () => onEvent({ type: 'error', code: 'WS_ERROR', message: 'WebSocket error' })
  return () => { try { ws.close() } catch { /* ignore */ } }
}
