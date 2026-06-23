/**
 * useMarketStream — shared WebSocket connection to `/ws/market`.
 *
 * Subscribes to symbols, parses quote/tick messages, reconnects with backoff.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { createMarketWebSocket, getApiKey } from '@/api/client'
import type { Exchange, Quote } from '@/types'

export type MarketStreamMessage =
  | { type: 'quote' | 'tick'; symbol: string; ltp: number; ts?: number; volume?: number; open?: number; high?: number; low?: number; prevClose?: number; change?: number; changePct?: number; exchange?: Exchange }
  | { type: 'subscribed' | 'unsubscribed'; symbols: string[] }
  | { type: 'error'; reason?: string; message?: string }

interface UseMarketStreamOptions {
  symbols?: string[]
  enabled?: boolean
}

interface UseMarketStreamResult {
  connected: boolean
  quotes: Record<string, Quote | null>
  subscribe: (symbols: string[]) => void
  unsubscribe: (symbols: string[]) => void
  lastMessage: MarketStreamMessage | null
}

type Listener = (msg: MarketStreamMessage) => void

const MAX_BACKOFF_MS = 30_000
const BASE_BACKOFF_MS = 500

class MarketStreamClient {
  private ws: WebSocket | null = null
  private symbols = new Set<string>()
  private listeners = new Set<Listener>()
  private reconnectAttempt = 0
  private reconnectTimer: number | null = null
  private enabled = true
  private quotes: Record<string, Quote | null> = {}

  addListener(fn: Listener): () => void {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  getQuotes(): Record<string, Quote | null> {
    return this.quotes
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }

  setEnabled(on: boolean): void {
    this.enabled = on
    if (!on) {
      this.disconnect()
    } else if (this.symbols.size > 0) {
      this.connect()
    }
  }

  setSymbols(symbols: string[]): void {
    const next = new Set(symbols.map((s) => s.toUpperCase()).filter(Boolean))
    const added = [...next].filter((s) => !this.symbols.has(s))
    const removed = [...this.symbols].filter((s) => !next.has(s))
    this.symbols = next
    if (added.length > 0) this.sendSubscribe(added)
    if (removed.length > 0) this.sendUnsubscribe(removed)
    if (this.enabled && this.symbols.size > 0 && !this.isConnected()) {
      this.connect()
    }
  }

  subscribe(symbols: string[]): void {
    const upper = symbols.map((s) => s.toUpperCase()).filter(Boolean)
    upper.forEach((s) => this.symbols.add(s))
    this.sendSubscribe(upper)
    if (this.enabled && !this.isConnected()) this.connect()
  }

  unsubscribe(symbols: string[]): void {
    const upper = symbols.map((s) => s.toUpperCase()).filter(Boolean)
    upper.forEach((s) => this.symbols.delete(s))
    this.sendUnsubscribe(upper)
  }

  private connect(): void {
    if (!this.enabled || this.ws?.readyState === WebSocket.CONNECTING) return
    this.disconnect(false)
    try {
      this.ws = createMarketWebSocket()
    } catch {
      this.scheduleReconnect()
      return
    }
    const ws = this.ws
    ws.onopen = () => {
      this.reconnectAttempt = 0
      if (this.symbols.size > 0) {
        this.sendSubscribe([...this.symbols])
      }
      this.emit({ type: 'subscribed', symbols: [...this.symbols] })
    }
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(String(ev.data)) as MarketStreamMessage
        this.handleMessage(msg)
        this.emit(msg)
      } catch { /* ignore malformed */ }
    }
    ws.onclose = () => {
      this.ws = null
      if (this.enabled) this.scheduleReconnect()
    }
    ws.onerror = () => {
      this.emit({ type: 'error', message: 'WebSocket error' })
    }
  }

  private handleMessage(msg: MarketStreamMessage): void {
    if (msg.type !== 'quote' && msg.type !== 'tick') return
    const symbol = msg.symbol?.toUpperCase()
    if (!symbol || msg.ltp == null) return
    const prev = this.quotes[symbol]
    const ts = msg.ts ?? Date.now()
    const prevClose = msg.prevClose ?? prev?.prevClose ?? msg.ltp
    const change = msg.change ?? msg.ltp - prevClose
    const changePct = msg.changePct ?? (prevClose ? (change / prevClose) * 100 : 0)
    this.quotes[symbol] = {
      symbol,
      exchange: msg.exchange ?? prev?.exchange ?? 'NSE',
      ltp: msg.ltp,
      open: msg.open ?? prev?.open ?? msg.ltp,
      high: msg.high ?? prev?.high ?? msg.ltp,
      low: msg.low ?? prev?.low ?? msg.ltp,
      prevClose,
      change,
      changePct,
      volume: msg.volume ?? prev?.volume ?? 0,
      bid: prev?.bid ?? msg.ltp,
      ask: prev?.ask ?? msg.ltp,
      bidQty: prev?.bidQty ?? 0,
      askQty: prev?.askQty ?? 0,
      ts,
    }
  }

  private sendSubscribe(symbols: string[]): void {
    if (!symbols.length || !this.isConnected()) return
    this.ws?.send(JSON.stringify({ action: 'subscribe', symbols }))
  }

  private sendUnsubscribe(symbols: string[]): void {
    if (!symbols.length || !this.isConnected()) return
    this.ws?.send(JSON.stringify({ action: 'unsubscribe', symbols }))
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer != null) return
    const delay = Math.min(MAX_BACKOFF_MS, BASE_BACKOFF_MS * 2 ** this.reconnectAttempt)
    this.reconnectAttempt += 1
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, delay)
  }

  private disconnect(clearTimer = true): void {
    if (clearTimer && this.reconnectTimer != null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.ws) {
      try { this.ws.close() } catch { /* ignore */ }
      this.ws = null
    }
  }

  private emit(msg: MarketStreamMessage): void {
    this.listeners.forEach((fn) => fn(msg))
  }
}

const sharedClient = new MarketStreamClient()

export function useMarketStream(opts: UseMarketStreamOptions = {}): UseMarketStreamResult {
  const { symbols = [], enabled = true } = opts
  const [connected, setConnected] = useState(sharedClient.isConnected())
  const [quotes, setQuotes] = useState<Record<string, Quote | null>>(() => ({ ...sharedClient.getQuotes() }))
  const [lastMessage, setLastMessage] = useState<MarketStreamMessage | null>(null)
  const symbolsKey = symbols.map((s) => s.toUpperCase()).sort().join(',')
  const symbolsRef = useRef(symbols)

  useEffect(() => {
    symbolsRef.current = symbols
  }, [symbols])

  useEffect(() => {
    sharedClient.setEnabled(enabled)
    if (enabled && symbols.length > 0) {
      sharedClient.setSymbols(symbols)
    }
    const off = sharedClient.addListener((msg) => {
      setLastMessage(msg)
      setQuotes({ ...sharedClient.getQuotes() })
      setConnected(sharedClient.isConnected())
    })
    setConnected(sharedClient.isConnected())
    return () => {
      off()
    }
  }, [enabled, symbolsKey])

  const subscribe = useCallback((syms: string[]) => {
    sharedClient.subscribe(syms)
    setQuotes({ ...sharedClient.getQuotes() })
  }, [])

  const unsubscribe = useCallback((syms: string[]) => {
    sharedClient.unsubscribe(syms)
    setQuotes({ ...sharedClient.getQuotes() })
  }, [])

  // Touch api key at module load so bundlers retain env
  void getApiKey()

  return { connected, quotes, subscribe, unsubscribe, lastMessage }
}

/** Test helper: reset shared client state between vitest cases. */
export function __resetMarketStreamForTests(): void {
  sharedClient.setEnabled(false)
  sharedClient.setSymbols([])
}
