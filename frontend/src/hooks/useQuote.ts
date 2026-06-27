/**
 * useQuote — live quote via WebSocket with HTTP poll fallback.
 */

import { useEffect, useRef, useState } from 'react'
import { getQuote } from '@/api/client'
import { useMarketStream } from '@/hooks/useMarketStream'
import type { Quote } from '@/types'

const REQUIRE_API = import.meta.env.VITE_REQUIRE_API === 'true'

interface UseQuoteOptions {
  intervalMs?: number
  enabled?: boolean
}

export type DataSource = 'ws' | 'http' | 'mock' | 'stale'

interface UseQuoteResult {
  quote: Quote | null
  isLive: boolean
  wsConnected: boolean
  latencyMs: number
  lastUpdated: number
  dataSource: DataSource
}

export function useQuote(symbol: string, opts: UseQuoteOptions = {}): UseQuoteResult {
  const { intervalMs = 1500, enabled = true } = opts
  const [quote, setQuote] = useState<Quote | null>(null)
  const [latencyMs, setLatencyMs] = useState(0)
  const [lastUpdated, setLastUpdated] = useState(0)
  const [dataSource, setDataSource] = useState<DataSource>('stale')
  const symRef = useRef(symbol)

  const { connected: wsConnected, quotes: wsQuotes } = useMarketStream({
    symbols: enabled ? [symbol] : [],
    enabled,
  })

  useEffect(() => {
    symRef.current = symbol
    setQuote(null)
    setDataSource('stale')
  }, [symbol])

  useEffect(() => {
    const wsQuote = wsQuotes[symbol.toUpperCase()]
    if (wsQuote) {
      setQuote(wsQuote)
      setLatencyMs(0)
      setLastUpdated(Date.now())
      setDataSource('ws')
    }
  }, [wsQuotes, symbol])

  useEffect(() => {
    if (!enabled) return
    if (wsConnected) return
    if (REQUIRE_API) {
      // Production: no mock poll when WS down — surface stale/null quote
      setDataSource('stale')
      return
    }
    let alive = true
    const tick = async () => {
      if (!alive || wsConnected) return
      const t0 = performance.now()
      try {
        const q = await getQuote(symRef.current)
        const dt = performance.now() - t0
        if (!alive) return
        setQuote(q)
        setLatencyMs(Math.round(dt))
        setLastUpdated(Date.now())
        setDataSource('http')
      } catch {
        setDataSource('mock')
      }
    }
    tick()
    const id = window.setInterval(tick, intervalMs)
    return () => { alive = false; clearInterval(id) }
  }, [symbol, intervalMs, enabled, wsConnected])

  return {
    quote,
    isLive: wsConnected || !!quote,
    wsConnected,
    latencyMs,
    lastUpdated,
    dataSource,
  }
}
