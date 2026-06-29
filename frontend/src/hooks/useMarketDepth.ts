/**
 * useMarketDepth — real-time L2 order book from WebSocket depth events.
 *
 * Listens to the shared MarketStreamClient for 'depth' events and
 * maintains the current order book state for the MarketDepth component.
 */

import { useEffect, useState } from 'react'
import { createMarketWebSocket, getApiKey } from '@/api/client'

export interface DOMLevel {
  price: number
  bidSize: number
  askSize: number
  bidOrders: number
  askOrders: number
}

export interface DOMSnapshot {
  symbol: string
  mid: number
  spread: number
  bids: DOMLevel[]
  asks: DOMLevel[]
  totalBid: number
  totalAsk: number
  imbalance: number
}

interface UseMarketDepthOptions {
  symbol?: string
  levels?: number
  enabled?: boolean
}

interface UseMarketDepthResult {
  depth: DOMSnapshot | null
  connected: boolean
}

const MAX_BACKOFF_MS = 30_000
const BASE_BACKOFF_MS = 500

class DepthStreamClient {
  private ws: WebSocket | null = null
  private symbol: string | null = null
  private listeners = new Set<(depth: DOMSnapshot | null) => void>()
  private reconnectAttempt = 0
  private reconnectTimer: number | null = null
  private enabled = true
  private depth: DOMSnapshot | null = null
  private levels = 10

  setLevels(n: number): void {
    this.levels = n
  }

  addListener(fn: (depth: DOMSnapshot | null) => void): () => void {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  getDepth(): DOMSnapshot | null {
    return this.depth
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }

  setEnabled(on: boolean): void {
    this.enabled = on
    if (!on) this.disconnect()
    else if (this.symbol) this.connect()
  }

  setSymbol(symbol: string | null): void {
    if (symbol === this.symbol) return
    this.symbol = symbol?.toUpperCase() ?? null
    this.depth = null
    if (this.enabled && this.symbol) this.connect()
    else this.disconnect()
  }

  private connect(): void {
    if (!this.enabled || !this.symbol || this.ws?.readyState === WebSocket.CONNECTING) return
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
      this.ws?.send(JSON.stringify({ action: 'subscribe', symbols: [this.symbol] }))
    }
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(String(ev.data))
        this.handleMessage(msg)
      } catch { /* ignore malformed */ }
    }
    ws.onclose = () => {
      this.ws = null
      if (this.enabled) this.scheduleReconnect()
    }
    ws.onerror = () => {}
  }

  private handleMessage(msg: { type: string; symbol?: string; [k: string]: unknown }): void {
    const msgType = msg.type?.toLowerCase()
    if (msgType !== 'depth' && msgType !== 'depth_20' && msgType !== 'depth_200') return
    if (msg.symbol?.toUpperCase() !== this.symbol) return
    if (!this.symbol) return

    const bids = (msg.bids as Array<{ price: number; quantity: number; orders?: number }>) ?? []
    const asks = (msg.asks as Array<{ price: number; quantity: number; orders?: number }>) ?? []

    const bidLevels: DOMLevel[] = bids.slice(0, this.levels).map((b) => ({
      price: b.price,
      bidSize: b.quantity,
      askSize: 0,
      bidOrders: b.orders ?? 0,
      askOrders: 0,
    }))

    const askLevels: DOMLevel[] = asks.slice(0, this.levels).map((a) => ({
      price: a.price,
      bidSize: 0,
      askSize: a.quantity,
      bidOrders: 0,
      askOrders: a.orders ?? 0,
    }))

    const totalBid = bidLevels.reduce((s, l) => s + l.bidSize, 0)
    const totalAsk = askLevels.reduce((s, l) => s + l.askSize, 0)
    const mid = bidLevels.length > 0 && askLevels.length > 0
      ? (bidLevels[0].price + askLevels[0].price) / 2
      : 0
    const spread = bidLevels.length > 0 && askLevels.length > 0
      ? askLevels[0].price - bidLevels[0].price
      : 0
    const imbalance = (totalBid + totalAsk) > 0
      ? (totalBid - totalAsk) / (totalBid + totalAsk)
      : 0

    this.depth = {
      symbol: this.symbol,
      mid,
      spread,
      bids: bidLevels,
      asks: askLevels,
      totalBid,
      totalAsk,
      imbalance,
    }
    this.emit()
  }

  private emit(): void {
    this.listeners.forEach((fn) => fn(this.depth))
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
}

const sharedClient = new DepthStreamClient()

export function useMarketDepth(opts: UseMarketDepthOptions = {}): UseMarketDepthResult {
  const { symbol, levels = 10, enabled = true } = opts
  const [depth, setDepth] = useState<DOMSnapshot | null>(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    sharedClient.setLevels(levels)
    sharedClient.setEnabled(enabled)
    sharedClient.setSymbol(symbol ?? null)
    const off = sharedClient.addListener((d) => {
      setDepth(d)
      setConnected(sharedClient.isConnected())
    })
    setConnected(sharedClient.isConnected())
    return () => { off() }
  }, [symbol, levels, enabled])

  void getApiKey()

  return { depth, connected }
}

export function __resetDepthStreamForTests(): void {
  sharedClient.setEnabled(false)
  sharedClient.setSymbol(null)
}
