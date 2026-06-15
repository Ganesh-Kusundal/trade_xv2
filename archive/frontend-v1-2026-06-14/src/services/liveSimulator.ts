/**
 * Live data simulator — mimics WebSocket streams from the backend:
 *   - Quotes (LTP updates with bid/ask)
 *   - Candles (tick-by-tick aggregation)
 *   - Order/position updates
 *   - Alerts
 *
 * In production this will be replaced by an EventBus WebSocket connection.
 */

import { useEffect, useRef, useState } from 'react'
import { generateQuote } from './mockData'
import { randomBetween } from '@/lib/utils'
import type { Quote, Candle } from '@/types/trading'

interface UseLiveQuotesOptions {
  symbols: string[]
  intervalMs?: number
}

export function useLiveQuotes({ symbols, intervalMs = 1500 }: UseLiveQuotesOptions) {
  const [quotes, setQuotes] = useState<Record<string, Quote>>(() => {
    const m: Record<string, Quote> = {}
    symbols.forEach((s) => (m[s] = generateQuote(s)))
    return m
  })
  const intervalRef = useRef<number | null>(null)
  const prevRef = useRef<Record<string, number>>({})

  useEffect(() => {
    symbols.forEach((s) => {
      if (!prevRef.current[s]) prevRef.current[s] = quotes[s]?.ltp || 0
    })
    intervalRef.current = window.setInterval(() => {
      setQuotes((prev) => {
        const next: Record<string, Quote> = { ...prev }
        symbols.forEach((s) => {
          const cur = prev[s]
          if (!cur) {
            next[s] = generateQuote(s)
            return
          }
          const drift = randomBetween(-0.0035, 0.0035) * cur.ltp
          const newLtp = Math.max(0.05, cur.ltp + drift)
          const direction = newLtp >= cur.ltp ? 1 : -1
          const newQuote: Quote = {
            ...cur,
            ltp: Number(newLtp.toFixed(2)),
            change: Number((cur.prevClose - newLtp > 0 ? -(cur.prevClose - newLtp) : (newLtp - cur.prevClose)).toFixed(2)),
            changePct: Number((((newLtp - cur.prevClose) / cur.prevClose) * 100).toFixed(2)),
            high: Math.max(cur.high, newLtp),
            low: Math.min(cur.low, newLtp),
            volume: cur.volume + Math.floor(randomBetween(100, 5000)),
            value: cur.value + Math.floor(newLtp * randomBetween(100, 5000)),
            bid: Number((newLtp - 0.05).toFixed(2)),
            ask: Number((newLtp + 0.05).toFixed(2)),
            oi: cur.oi + Math.floor(randomBetween(-1000, 1000)),
            timestamp: Date.now(),
          }
          prevRef.current[s] = newLtp
          next[s] = newQuote
        })
        return next
      })
    }, intervalMs)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbols.join(','), intervalMs])

  return quotes
}

interface UseLiveCandlesOptions {
  symbol: string
  initialCandles: Candle[]
  intervalMs?: number
}

export function useLiveCandles({ symbol, initialCandles, intervalMs = 1000 }: UseLiveCandlesOptions) {
  const [candles, setCandles] = useState<Candle[]>(initialCandles)
  const lastPriceRef = useRef<number>(initialCandles[initialCandles.length - 1]?.close || 100)

  useEffect(() => {
    setCandles(initialCandles)
    lastPriceRef.current = initialCandles[initialCandles.length - 1]?.close || 100
  }, [symbol, initialCandles])

  useEffect(() => {
    const id = window.setInterval(() => {
      setCandles((prev) => {
        const next = [...prev]
        const last = next[next.length - 1]
        if (!last) return prev
        const drift = randomBetween(-0.0025, 0.0025) * last.close
        const newClose = Math.max(0.05, last.close + drift)
        const newHigh = Math.max(last.high, newClose)
        const newLow = Math.min(last.low, newClose)
        const newVol = last.volume + Math.floor(randomBetween(50, 1500))
        // Aggregate into a 5m candle for the demo
        if (Date.now() - last.timestamp > 5 * 60 * 1000) {
          next.push({
            timestamp: Date.now(),
            open: newClose,
            high: newHigh,
            low: newLow,
            close: newClose,
            volume: newVol,
            vwap: (newHigh + newLow + newClose) / 3,
          })
          if (next.length > 300) next.shift()
        } else {
          next[next.length - 1] = {
            ...last,
            high: newHigh,
            low: newLow,
            close: newClose,
            volume: newVol,
            vwap: (newHigh + newLow + newClose) / 3,
          }
        }
        lastPriceRef.current = newClose
        return next
      })
    }, intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])

  return { candles, lastPrice: lastPriceRef.current }
}
