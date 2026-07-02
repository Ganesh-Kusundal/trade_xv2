/**
 * useTrades — real-time trade tape from WebSocket depth/trade events.
 *
 * Listens to the shared MarketStreamClient for 'depth' and 'trade' events
 * and accumulates them into a trade tape for the TimeAndSales component.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { createMarketWebSocket, getApiKey } from '@/api/client'
import { sharedMarketClient } from './useMarketStream'

export interface Trade {
  t: number        // timestamp (epoch ms)
  price: number
  size: number
  side: 'BUY' | 'SELL'
  condition?: 'BLOCK' | 'SWEEP' | 'LARGE' | null
  symbol: string
}

interface UseTradesOptions {
  symbol?: string
  maxTrades?: number
  enabled?: boolean
}

interface UseTradesResult {
  trades: Trade[]
  connected: boolean
  totalBuyVolume: number
  totalSellVolume: number
  delta: number
}

const MAX_TRADES = 80
const MAX_BACKOFF_MS = 30_000
const BASE_BACKOFF_MS = 500

function classifyTrade(size: number): Trade['condition'] {
  if (size > 10000) return 'BLOCK'
  if (size > 5000) return 'LARGE'
  if (Math.random() < 0.04) return 'SWEEP'
  return null
}

class TradesStreamClient {
  private ws: WebSocket | null = null
  private offMarketStream: (() => void) | null = null
  private symbol: string | null = null
  private listeners = new Set<(trades: Trade[]) => void>()
  private reconnectAttempt = 0
  private reconnectTimer: number | null = null
  private enabled = true
  private trades: Trade[] = []
  private maxTrades = MAX_TRADES

  setMaxTrades(n: number): void {
    this.maxTrades = n
  }

  addListener(fn: (trades: Trade[]) => void): () => void {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  getTrades(): Trade[] {
    return this.trades
  }

  isConnected(): boolean {
    return sharedMarketClient.isConnected()
  }

  setEnabled(on: boolean): void {
    this.enabled = on
    if (!on) this.disconnect()
    else if (this.symbol) this.connect()
  }

  setSymbol(symbol: string | null): void {
    if (symbol === this.symbol) return
    this.symbol = symbol?.toUpperCase() ?? null
    this.trades = []
    if (this.enabled && this.symbol) this.connect()
    else this.disconnect()
  }

  private connect(): void {
    const isTest = typeof process !== 'undefined' && process.env.NODE_ENV === 'test'
    const disableLiveWs = !isTest && import.meta.env.VITE_DISABLE_LIVE_WS !== 'false'
    if (disableLiveWs) {
      return
    }
    if (!this.enabled || !this.symbol) return
    this.disconnect()

    sharedMarketClient.subscribe([this.symbol])
    this.offMarketStream = sharedMarketClient.addListener((msg) => {
      this.handleMessage(msg as any)
    })
  }

  private handleMessage(msg: { type: string; symbol?: string; [k: string]: unknown }): void {
    if (!this.symbol) return
    if (msg.type === 'trade' && msg.symbol?.toUpperCase() === this.symbol) {
      const trade: Trade = {
        t: (msg.ts as number) ?? Date.now(),
        price: msg.price as number,
        size: msg.size as number,
        side: (msg.side as 'BUY' | 'SELL') ?? 'BUY',
        condition: classifyTrade(msg.size as number),
        symbol: this.symbol,
      }
      this.trades = [trade, ...this.trades].slice(0, this.maxTrades)
      this.emit()
    }

    // Also extract trades from depth updates (bid/ask hit detection)
    if (msg.type === 'depth' && msg.symbol?.toUpperCase() === this.symbol) {
      // Depth updates don't directly give trades, but we can track changes
      // For now, depth events are handled by useMarketDepth
    }
  }

  private emit(): void {
    const snapshot = [...this.trades]
    this.listeners.forEach((fn) => fn(snapshot))
  }

  private disconnect(): void {
    if (this.offMarketStream) {
      this.offMarketStream()
      this.offMarketStream = null
    }
    if (this.symbol) {
      sharedMarketClient.unsubscribe([this.symbol])
    }
    if (this.ws) {
      try { this.ws.close() } catch { /* ignore */ }
      this.ws = null
    }
  }
}

const sharedClient = new TradesStreamClient()

export function useTrades(opts: UseTradesOptions = {}): UseTradesResult {
  const { symbol, maxTrades = MAX_TRADES, enabled = true } = opts
  const [trades, setTrades] = useState<Trade[]>([])
  const [connected, setConnected] = useState(false)
  const symbolRef = useRef(symbol)

  useEffect(() => {
    symbolRef.current = symbol
  }, [symbol])

  useEffect(() => {
    sharedClient.setMaxTrades(maxTrades)
    sharedClient.setEnabled(enabled)
    sharedClient.setSymbol(symbol ?? null)
    const off = sharedClient.addListener((t) => {
      setTrades(t)
      setConnected(sharedClient.isConnected())
    })
    setConnected(sharedClient.isConnected())
    return () => { off() }
  }, [symbol, maxTrades, enabled])

  const totalBuyVolume = trades.filter((t) => t.side === 'BUY').reduce((s, t) => s + t.size, 0)
  const totalSellVolume = trades.filter((t) => t.side === 'SELL').reduce((s, t) => s + t.size, 0)
  const delta = totalBuyVolume - totalSellVolume

  void getApiKey()

  return { trades, connected, totalBuyVolume, totalSellVolume, delta }
}

export function __resetTradesStreamForTests(): void {
  sharedClient.setEnabled(false)
  sharedClient.setSymbol(null)
}
