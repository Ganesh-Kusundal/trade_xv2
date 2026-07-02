/**
 * useCandles — fetches and refreshes historical candles for a symbol.
 *
 * The visible-count is local (replay progressively reveals candles).
 */

import { useEffect, useRef, useState } from 'react'
import { getCandles } from '@/api/client'
import type { Candle, Timeframe } from '@/types'

interface UseCandlesResult {
  candles: Candle[]
  loading: boolean
  error: string | null
  /** Append or replace the last candle (used for live tick + replay). */
  push: (c: Candle) => void
  /** Reset visible count to a specific value (used by replay seek). */
  setVisible: (n: number) => void
  visibleCount: number
}

export function useCandles(
  symbol: string,
  timeframe: Timeframe,
  bars = 200,
): UseCandlesResult {
  const [candles, setCandles] = useState<Candle[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [visibleCount, setVisibleCount] = useState(bars)
  const keyRef = useRef<string>('')

  useEffect(() => {
    let alive = true
    const key = `${symbol}|${timeframe}|${bars}`
    keyRef.current = key
    setLoading(true)
    setError(null)
    setVisibleCount(bars)

    const controller = new AbortController()

    getCandles(symbol, timeframe, bars, 'NSE', controller.signal)
      .then((c) => {
        if (!alive || keyRef.current !== key) return
        setCandles(c)
        setVisibleCount(c.length)
      })
      .catch((e) => {
        if (!alive) return
        if (e instanceof Error && e.name === 'AbortError') return
        setError(String(e))
      })
      .finally(() => { if (!alive) return; setLoading(false) })

    return () => {
      alive = false
      controller.abort()
    }
  }, [symbol, timeframe, bars])

  const push = (c: Candle) => {
    setCandles((prev) => {
      if (prev.length === 0) return [c]
      const last = prev[prev.length - 1]
      // Replay: if the new candle is later than the last, append.
      if (c.t > last.t) {
        const next = [...prev, c]
        setVisibleCount(next.length)
        return next
      }
      // Same bucket: update the last candle in place.
      if (c.t === last.t) {
        const next = prev.slice()
        next[next.length - 1] = {
          t: last.t,
          o: last.o,
          h: Math.max(last.h, c.h),
          l: Math.min(last.l, c.l),
          c: c.c,
          v: last.v + c.v,
        }
        return next
      }
      // Older than the last — ignore.
      return prev
    })
  }

  return { candles, loading, error, push, visibleCount, setVisible: setVisibleCount }
}
