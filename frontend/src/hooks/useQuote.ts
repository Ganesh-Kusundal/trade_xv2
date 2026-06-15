/**
 * useQuote — small hook to poll a single symbol's quote.
 *
 * Uses the API client (real backend if up, mock otherwise).
 */

import { useEffect, useRef, useState } from 'react'
import { getQuote } from '@/api/client'
import type { Quote } from '@/types'

interface UseQuoteOptions {
  intervalMs?: number
  enabled?: boolean
}

interface UseQuoteResult {
  quote: Quote | null
  isLive: boolean
  latencyMs: number
  lastUpdated: number
}

export function useQuote(symbol: string, opts: UseQuoteOptions = {}): UseQuoteResult {
  const { intervalMs = 1500, enabled = true } = opts
  const [quote, setQuote] = useState<Quote | null>(null)
  const [latencyMs, setLatencyMs] = useState(0)
  const [lastUpdated, setLastUpdated] = useState(0)
  const symRef = useRef(symbol)

  useEffect(() => {
    symRef.current = symbol
    setQuote(null)
    if (!enabled) return
    let alive = true
    const tick = async () => {
      if (!alive) return
      const t0 = performance.now()
      try {
        const q = await getQuote(symRef.current)
        const dt = performance.now() - t0
        if (!alive) return
        setQuote(q)
        setLatencyMs(Math.round(dt))
        setLastUpdated(Date.now())
      } catch { /* ignore */ }
    }
    tick()
    const id = window.setInterval(tick, intervalMs)
    return () => { alive = false; clearInterval(id) }
  }, [symbol, intervalMs, enabled])

  return {
    quote,
    isLive: !!quote,
    latencyMs,
    lastUpdated,
  }
}
