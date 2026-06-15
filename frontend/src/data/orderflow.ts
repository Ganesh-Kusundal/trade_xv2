/**
 * Orderflow data generators — live trade tape, L2 order book, and news
 * headlines for the side panels.
 *
 * Deterministic per symbol/time so the UI feels stable while you scroll.
 */

import { basePrice, rng as baseRng, hash as baseHash } from './mockMarket'

// ── Time & Sales ─────────────────────────────────────────────────────

export interface Trade {
  id: string
  t: number
  price: number
  size: number
  side: 'BUY' | 'SELL'
  condition?: 'BLOCK' | 'SWEEP' | 'LARGE' | 'AUCTION'
}

export function generateTrades(symbol: string, count = 50): Trade[] {
  const base = basePrice(symbol)
  const seed = baseHash(symbol) ^ Math.floor(Date.now() / 5000)
  const r = baseRng(seed)
  const trades: Trade[] = []
  let last = base
  for (let i = 0; i < count; i++) {
    const dir = r() < 0.5 ? -1 : 1
    const tick = (0.05) * (r() < 0.08 ? Math.floor(r() * 4) + 1 : 1)
    const move = dir * tick + (r() - 0.5) * base * 0.0008
    last = Math.max(0.05, last + move)
    const size = Math.floor(50 + r() ** 1.5 * 4500 + (r() < 0.04 ? 8000 : 0))
    const condition =
      size > 10000 ? 'BLOCK' : size > 5000 ? 'LARGE' : r() < 0.04 ? 'SWEEP' : undefined
    const side: 'BUY' | 'SELL' = move >= 0 ? 'BUY' : 'SELL'
    trades.unshift({
      id: `${symbol}-${Date.now()}-${i}`,
      t: Date.now() - i * (300 + Math.floor(r() * 1800)),
      price: Number(last.toFixed(2)),
      size,
      side,
      condition,
    })
  }
  return trades
}

// ── L2 Market Depth ──────────────────────────────────────────────────

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

export function generateDOM(symbol: string, levels = 10): DOMSnapshot {
  const base = basePrice(symbol)
  const r = baseRng(baseHash(symbol) ^ Math.floor(Date.now() / 4000))
  const mid = Number(base.toFixed(2))
  const tick = 0.05
  const bids: DOMLevel[] = []
  const asks: DOMLevel[] = []
  let totalBid = 0
  let totalAsk = 0
  for (let i = 0; i < levels; i++) {
    const decay = Math.exp(-i / 4)
    const bidSize = Math.floor((600 + r() * 4000) * decay)
    const askSize = Math.floor((600 + r() * 4000) * decay)
    const bidOrders = Math.max(1, Math.floor(r() * 8) + 1)
    const askOrders = Math.max(1, Math.floor(r() * 8) + 1)
    bids.push({
      price: Number((mid - (i + 1) * tick).toFixed(2)),
      bidSize,
      askSize: 0,
      bidOrders,
      askOrders: 0,
    })
    asks.push({
      price: Number((mid + (i + 1) * tick).toFixed(2)),
      bidSize: 0,
      askSize,
      bidOrders: 0,
      askOrders,
    })
    totalBid += bidSize
    totalAsk += askSize
  }
  const imbalance = (totalBid - totalAsk) / (totalBid + totalAsk)
  return {
    symbol,
    mid,
    spread: tick,
    bids,
    asks,
    totalBid,
    totalAsk,
    imbalance,
  }
}

// ── News Headlines ───────────────────────────────────────────────────

export interface NewsItem {
  t: number
  symbol: string
  category: 'EARNINGS' | 'CORP' | 'MARKET' | 'TECH' | 'MACRO' | 'REGULATORY'
  headline: string
  source: string
}

const SAMPLE_HEADLINES: Omit<NewsItem, 't'>[] = [
  { symbol: 'RELIANCE',   category: 'EARNINGS',  headline: 'Reliance Industries Q3 net profit rises 11% YoY, beats estimates', source: 'Reuters' },
  { symbol: 'TCS',        category: 'EARNINGS',  headline: 'TCS bags $1.2B deal from UK financial services giant', source: 'Bloomberg' },
  { symbol: 'HDFCBANK',   category: 'CORP',      headline: 'HDFC Bank raises ₹12,000 Cr via QIP, allotment on Jan 18', source: 'Moneycontrol' },
  { symbol: 'INFY',       category: 'EARNINGS',  headline: 'Infosys revises FY26 revenue guidance upward to 3.75-4.5%', source: 'CNBC' },
  { symbol: 'SBIN',       category: 'CORP',      headline: 'SBI to consider raising ₹20,000 Cr via infrastructure bonds', source: 'ET Markets' },
  { symbol: 'BHARTIARTL', category: 'CORP',      headline: 'Bharti Airtel to merge subsidiary with parent; Airtel Payments Bank deal', source: 'LiveMint' },
  { symbol: 'ICICIBANK',  category: 'EARNINGS',  headline: 'ICICI Bank Q3 PAT up 23% YoY at ₹11,792 Cr, NIM steady', source: 'BS' },
  { symbol: 'NIFTY',      category: 'MARKET',    headline: 'NIFTY 50 hits fresh record high; mid-cap outperformance broadens', source: 'CNBC' },
  { symbol: 'BANKNIFTY',  category: 'MARKET',    headline: 'Bank NIFTY outperforms as PSU banks see heavy FII buying', source: 'Moneycontrol' },
  { symbol: 'INDIA',      category: 'MACRO',     headline: 'RBI keeps repo rate unchanged at 6.25%, signals balanced stance', source: 'RBI' },
  { symbol: 'OIL',        category: 'MACRO',     headline: 'Crude oil prices ease on rising US inventories; Brent below $74', source: 'Reuters' },
  { symbol: 'GOLD',       category: 'MACRO',     headline: 'Gold prices hit 4-week high on safe-haven demand', source: 'Bloomberg' },
  { symbol: 'TATAMOTORS', category: 'TECH',      headline: 'Tata Motors JLR sales up 12% YoY in Q3, US demand strong', source: 'ET' },
  { symbol: 'MARUTI',     category: 'TECH',      headline: 'Maruti Suzuki hikes prices across models by up to 4%', source: 'CNBC' },
  { symbol: 'ADANIENT',  category: 'REGULATORY',headline: 'SEBI clears Adani Group entities of certain disclosure lapses', source: 'ET' },
  { symbol: 'TATASTEEL', category: 'CORP',      headline: 'Tata Steel UK unions accept revised restructuring plan', source: 'Reuters' },
  { symbol: 'WIPRO',     category: 'EARNINGS',  headline: 'Wipro Q3 net profit beats estimates; BFSI vertical shows revival', source: 'Moneycontrol' },
  { symbol: 'HCLTECH',   category: 'EARNINGS',  headline: 'HCLTech Q3 constant-currency revenue up 4.6% QoQ, upbeat on AI', source: 'BS' },
]

export function generateNews(count = 20): NewsItem[] {
  const out: NewsItem[] = []
  const r = baseRng(Math.floor(Date.now() / 60_000))
  for (let i = 0; i < count; i++) {
    const h = SAMPLE_HEADLINES[Math.floor(r() * SAMPLE_HEADLINES.length)]
    out.push({
      ...h,
      t: Date.now() - i * Math.floor(60_000 + r() * 600_000),
    })
  }
  return out
}

// Re-export the rng/hash for callers that don't want to import mockMarket
import { rng, hash } from './mockMarket'
export { rng, hash }
