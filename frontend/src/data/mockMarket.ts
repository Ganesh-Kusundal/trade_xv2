/**
 * Mock market data generators.
 *
 * In production these are replaced by the FastAPI backend (see
 * BACKEND_API_SPEC.md). They are kept in the frontend so the UI is
 * fully functional when the backend is down or during local dev.
 *
 * The generators are *deterministic per symbol* — given a symbol name
 * they always produce the same historical price walk. This makes the
 * UI feel stable while you're typing in the search box.
 */

import type { Candle, Quote, Timeframe, Exchange } from '@/types'

// Stable base prices so the user sees "their" numbers in the chart.
const BASE_PRICES: Record<string, number> = {
  RELIANCE: 2935.4, TCS: 4080.5, HDFCBANK: 1670.2, INFY: 1847.3,
  ICICIBANK: 1290.5, HINDUNILVR: 2370.0, ITC: 480.0, SBIN: 825.0,
  BHARTIARTL: 1610.2, KOTAKBANK: 1750.0, LT: 3680.0, AXISBANK: 1175.0,
  ASIANPAINT: 2380.0, MARUTI: 12450.0, BAJFINANCE: 7180.0, WIPRO: 530.0,
  HCLTECH: 1800.0, SUNPHARMA: 1820.0, TITAN: 3640.0, ULTRACEMCO: 11800.0,
  NESTLEIND: 2280.0, TECHM: 1690.0, POWERGRID: 312.0, NTPC: 380.0,
  'M&M': 2890.0, TATAMOTORS: 950.0, TATASTEEL: 152.0, ADANIENT: 2640.0,
  ADANIPORTS: 1390.0, COALINDIA: 425.0, ONGC: 270.0, JSWSTEEL: 920.0,
  HINDALCO: 650.0, GRASIM: 2680.0, BPCL: 320.0, IOC: 142.0,
  DRREDDY: 1240.0, CIPLA: 1520.0, APOLLOHOSP: 7080.0, BRITANNIA: 4820.0,
  EICHERMOT: 4870.0, HEROMOTOCO: 4780.0, BAJAJFINSV: 1640.0,
  INDUSINDBK: 1480.0, DIVISLAB: 6080.0, TATAPOWER: 415.0, ADANIGREEN: 1010.0,
  SBILIFE: 1820.0, HDFCLIFE: 680.0, BAJAJ_AUTO: 9150.0,
}

export function hash(s: string): number {
  let h = 2166136261 >>> 0
  for (let i = 0; i < s.length; i++) {
    h = (h ^ s.charCodeAt(i)) * 16777619 >>> 0
  }
  return h >>> 0
}

/** Cheap seeded PRNG (mulberry32). */
export function rng(seed: number): () => number {
  let s = seed >>> 0
  return () => {
    s = (s + 0x6D2B79F5) >>> 0
    let t = s
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function basePrice(symbol: string): number {
  return BASE_PRICES[symbol] ?? 500 + (hash(symbol) % 4000)
}

const TF_MS: Record<Timeframe, number> = {
  '1m':  60_000,
  '3m':  180_000,
  '5m':  300_000,
  '15m': 900_000,
  '30m': 1_800_000,
  '1h':  3_600_000,
  '4h':  14_400_000,
  '1d':  86_400_000,
  '1w':  604_800_000,
}

const TF_VOL: Record<Timeframe, number> = {
  '1m':  0.0015, '3m': 0.0025, '5m': 0.0035, '15m': 0.005, '30m': 0.007,
  '1h':  0.01,   '4h': 0.018,  '1d':  0.025,  '1w':  0.04,
}

/**
 * Generate N historical candles ending at the most recent completed
 * interval for the given timeframe. The walk is anchored to the
 * base price and shaped to be self-consistent.
 */
export function generateCandles(
  symbol: string,
  timeframe: Timeframe,
  bars = 200,
  endTime: number = Date.now(),
): Candle[] {
  const base = basePrice(symbol)
  const ms = TF_MS[timeframe]
  const sigma = TF_VOL[timeframe]
  const r = rng(hash(symbol) ^ Math.floor(endTime / ms))

  // Anchor the last close to the base price with a small offset.
  const candles: Candle[] = []
  const total = bars
  let price = base * (1 - sigma * 10)
  // Walk forward from oldest to newest.
  const startT = endTime - total * ms
  for (let i = 0; i < total; i++) {
    const drift = (base - price) * 0.02
    const o = price
    const c = o + drift + (r() - 0.5) * base * sigma * 2
    const h = Math.max(o, c) + r() * base * sigma * 1.2
    const l = Math.min(o, c) - r() * base * sigma * 1.2
    const v = Math.floor(20_000 + r() * 400_000)
    candles.push({
      t: startT + i * ms,
      o: round2(o),
      h: round2(h),
      l: round2(l),
      c: round2(c),
      v,
    })
    price = c
  }
  return candles
}

export function generateQuote(symbol: string, prevClose?: number): Quote {
  const base = basePrice(symbol)
  const r = rng(hash(symbol) ^ Math.floor(Date.now() / 5000))
  const drift = (r() - 0.5) * 0.025
  const ltp = round2(base * (1 + drift))
  const pc = round2(prevClose ?? base)
  return {
    symbol,
    exchange: 'NSE',
    ltp,
    open:   round2(base * (1 + (r() - 0.5) * 0.012)),
    high:   round2(Math.max(base, ltp) + r() * base * 0.008),
    low:    round2(Math.min(base, ltp) - r() * base * 0.008),
    prevClose: pc,
    change:  round2(ltp - pc),
    changePct: round2(((ltp - pc) / pc) * 100),
    volume: Math.floor(100_000 + r() * 6_000_000),
    bid:    round2(ltp - 0.05),
    ask:    round2(ltp + 0.05),
    bidQty: Math.floor(200 + r() * 4000),
    askQty: Math.floor(200 + r() * 4000),
    ts: Date.now(),
  }
}

function round2(n: number): number {
  return Math.round(n * 100) / 100
}

/** Pad a date string (YYYY-MM-DD) to a millisecond epoch at 00:00:00 IST. */
export function isoToISTMs(iso: string): number {
  const d = new Date(iso + 'T00:00:00+05:30')
  return d.getTime()
}
