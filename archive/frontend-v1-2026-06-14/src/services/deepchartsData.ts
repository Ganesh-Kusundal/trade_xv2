/**
 * DeepCharts-style Orderflow Data Generator
 *
 * Generates synthetic but realistic data structures for the order-flow
 * widget family:
 *   - Footprint candles (price ladder with bid/ask volume + delta)
 *   - Deep DOM (multi-level order book with iceberg detection)
 *   - Volume profile (POC, HVN, LVN)
 *   - TPO profile (singleprints)
 *   - Time & Sales / Deep Print
 *   - Initial Balance (IB high/low, VAH, VAL)
 *   - Buyside squeeze bubbles
 *   - DOM heatmap
 *
 * In production, these will be served by the Python backend. For now we
 * generate deterministic-ish mock data that looks like real orderflow.
 */

import { getBasePrice } from './mockData'
import { randomBetween } from '@/lib/utils'

// ───────────────────────────────────────────────────────────────────────
// Footprint candle
// ───────────────────────────────────────────────────────────────────────

export interface FootprintLevel {
  price: number
  bidVolume: number
  askVolume: number
  /** askVolume - bidVolume */
  delta: number
  /** number of buy trades at this level */
  buyTrades: number
  /** number of sell trades at this level */
  sellTrades: number
  /** highlight this level (unusual activity) */
  isPOC?: boolean
  isHVN?: boolean
  isLVN?: boolean
  /** detected iceberg/divider */
  isIceberg?: boolean
  /** single-print flag (TPO) */
  isSinglePrint?: boolean
}

export interface FootprintCandle {
  /** candle start (ms) */
  timestamp: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  totalDelta: number
  /** ladder of price levels, low→high */
  levels: FootprintLevel[]
  /** label: HH:MM */
  label: string
}

export function generateFootprintCandles(
  symbol: string,
  bars = 30,
  levelsPerBar = 12,
): FootprintCandle[] {
  const base = getBasePrice(symbol)
  const tickSize = 0.05
  const now = Date.now()
  const out: FootprintCandle[] = []
  let price = base * 0.99

  for (let i = bars - 1; i >= 0; i--) {
    const drift = (base - price) * 0.04 + randomBetween(-base * 0.003, base * 0.003)
    const open = price
    const close = open + drift
    const high = Math.max(open, close) + randomBetween(0, base * 0.004)
    const low = Math.min(open, close) - randomBetween(0, base * 0.004)
    const numLevels = levelsPerBar + Math.floor(randomBetween(-2, 3))
    const range = high - low
    const step = Math.max(tickSize, range / numLevels)

    // Choose one POC level (highest volume)
    const pocIdx = Math.floor(randomBetween(0, numLevels - 1))
    const lvns = new Set<number>()
    if (numLevels > 6) {
      lvns.add(Math.floor(numLevels / 4))
      lvns.add(Math.floor((numLevels * 3) / 4))
    }
    const hvnIdx = pocIdx === Math.floor(numLevels / 2) ? pocIdx + 1 : Math.floor(numLevels / 2)

    const levels: FootprintLevel[] = []
    let totalDelta = 0
    for (let j = 0; j < numLevels; j++) {
      const lvlPrice = Number((low + j * step).toFixed(2))
      const isPOC = j === pocIdx
      const isHVN = j === hvnIdx && !isPOC
      const isLVN = lvns.has(j)
      const proximity = 1 - Math.abs(j - pocIdx) / numLevels
      const baseVol = Math.floor(80 + randomBetween(0, 700) * proximity)
      const buyBias = close > open ? 0.62 : 0.38
      const bidVolume = Math.floor(baseVol * (1 - buyBias) * (0.6 + Math.random() * 0.8))
      const askVolume = Math.floor(baseVol * buyBias * (0.6 + Math.random() * 0.8))
      const isIceberg = Math.random() < 0.04 && (bidVolume + askVolume) > 400
      const total = bidVolume + askVolume
      const delta = askVolume - bidVolume
      totalDelta += delta
      levels.push({
        price: lvlPrice,
        bidVolume,
        askVolume,
        delta,
        buyTrades: Math.max(1, Math.floor(askVolume / 80)),
        sellTrades: Math.max(1, Math.floor(bidVolume / 80)),
        isPOC,
        isHVN,
        isLVN,
        isIceberg,
        isSinglePrint: isLVN,
      })
    }
    const totalVol = levels.reduce((s, l) => s + l.bidVolume + l.askVolume, 0)
    const d = new Date(now - i * 5 * 60 * 1000)
    out.push({
      timestamp: d.getTime(),
      open: Number(open.toFixed(2)),
      high: Number(high.toFixed(2)),
      low: Number(low.toFixed(2)),
      close: Number(close.toFixed(2)),
      volume: totalVol,
      totalDelta,
      levels,
      label: `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`,
    })
    price = close
  }
  return out
}

// ───────────────────────────────────────────────────────────────────────
// Deep DOM (Level 2 + iceberg detection)
// ───────────────────────────────────────────────────────────────────────

export interface DOMLevel {
  price: number
  bidSize: number
  askSize: number
  /** cumulative aggressive hits at this level */
  bidAggressive: number
  askAggressive: number
  /** number of times this level was refilled (iceberg signal) */
  refillCount: number
  /** size of the hidden / not-in-book iceberg */
  icebergSize: number
  /** last refresh time (ms) */
  timestamp: number
}

export interface DeepDOMSnapshot {
  symbol: string
  midPrice: number
  spread: number
  bids: DOMLevel[]
  asks: DOMLevel[]
  /** levels with active icebergs (any side) */
  icebergLevels: number[]
  timestamp: number
}

export function generateDeepDOM(symbol: string, levels = 20): DeepDOMSnapshot {
  const base = getBasePrice(symbol)
  const tickSize = 0.05
  const mid = base
  const spread = tickSize
  const bids: DOMLevel[] = []
  const asks: DOMLevel[] = []
  const icebergLevels: number[] = []
  for (let i = 0; i < levels; i++) {
    const bidBase = 800 + Math.floor(randomBetween(-300, 3000) * Math.exp(-i / 6))
    const askBase = 800 + Math.floor(randomBetween(-300, 3000) * Math.exp(-i / 6))
    const bidIceberg = Math.random() < 0.08 ? Math.floor(randomBetween(5000, 25000)) : 0
    const askIceberg = Math.random() < 0.08 ? Math.floor(randomBetween(5000, 25000)) : 0
    const bidRefills = bidIceberg > 0 ? Math.floor(randomBetween(2, 9)) : 0
    const askRefills = askIceberg > 0 ? Math.floor(randomBetween(2, 9)) : 0
    const price = Number((mid - (i + 1) * tickSize).toFixed(2))
    const bid: DOMLevel = {
      price: Number((mid - (i + 1) * tickSize).toFixed(2)),
      bidSize: bidBase + bidIceberg,
      askSize: 0,
      bidAggressive: Math.floor(randomBetween(0, 2000)),
      askAggressive: 0,
      refillCount: bidRefills,
      icebergSize: bidIceberg,
      timestamp: Date.now(),
    }
    bids.push(bid)
    if (bidIceberg > 0) icebergLevels.push(price)
    const ask: DOMLevel = {
      price: Number((mid + (i + 1) * tickSize).toFixed(2)),
      bidSize: 0,
      askSize: askBase + askIceberg,
      bidAggressive: 0,
      askAggressive: Math.floor(randomBetween(0, 2000)),
      refillCount: askRefills,
      icebergSize: askIceberg,
      timestamp: Date.now(),
    }
    asks.push(ask)
    if (askIceberg > 0 && !icebergLevels.includes(ask.price)) icebergLevels.push(ask.price)
  }
  return {
    symbol,
    midPrice: Number(mid.toFixed(2)),
    spread,
    bids,
    asks,
    icebergLevels,
    timestamp: Date.now(),
  }
}

// ───────────────────────────────────────────────────────────────────────
// Volume Profile (POC / HVN / LVN)
// ───────────────────────────────────────────────────────────────────────

export interface VolumeProfileLevel {
  price: number
  volume: number
  /** % of total session volume */
  pct: number
  type: 'POC' | 'HVN' | 'LVN' | 'NORMAL'
  buyVolume: number
  sellVolume: number
  /** TPO letter count (TPO mode) */
  tpoCount: number
}

export interface VolumeProfileData {
  symbol: string
  levels: VolumeProfileLevel[]
  poc: number
  vah: number // Value Area High (70%)
  val: number // Value Area Low (70%)
  totalVolume: number
  range: { high: number; low: number }
}

export function generateVolumeProfile(symbol: string, levels = 30): VolumeProfileData {
  const base = getBasePrice(symbol)
  const range = base * 0.025
  const low = base - range
  const high = base + range
  const step = (high - low) / levels

  // Generate a distribution: bell curve with random spikes
  const rawVols: number[] = []
  const mid = levels / 2
  for (let i = 0; i < levels; i++) {
    const dist = Math.abs(i - mid) / mid
    const bell = Math.exp(-dist * dist * 3.5)
    const noise = randomBetween(0, 0.6)
    rawVols.push(bell * 1000 + noise * 400 + randomBetween(0, 200))
  }

  // Pick POC (highest)
  const pocIdx = rawVols.indexOf(Math.max(...rawVols))

  // Find HVN: peaks > 70% of POC
  const hvnIdxs: number[] = []
  for (let i = 0; i < rawVols.length; i++) {
    if (i !== pocIdx && rawVols[i] > rawVols[pocIdx] * 0.65) hvnIdxs.push(i)
  }

  // Find LVN: valleys < 30% of POC
  const lvnIdxs: number[] = []
  for (let i = 1; i < rawVols.length - 1; i++) {
    if (rawVols[i] < rawVols[pocIdx] * 0.25 && rawVols[i] < rawVols[i - 1] && rawVols[i] < rawVols[i + 1]) {
      lvnIdxs.push(i)
    }
  }

  // Compute Value Area (70% of volume)
  const totalVol = rawVols.reduce((s, v) => s + v, 0)
  const target = totalVol * 0.7
  let lo = pocIdx
  let hi = pocIdx
  let acc = rawVols[pocIdx]
  while (acc < target && (lo > 0 || hi < rawVols.length - 1)) {
    const loV = lo > 0 ? rawVols[lo - 1] : 0
    const hiV = hi < rawVols.length - 1 ? rawVols[hi + 1] : 0
    if (loV >= hiV && lo > 0) {
      lo--
      acc += loV
    } else if (hi < rawVols.length - 1) {
      hi++
      acc += hiV
    } else {
      break
    }
  }

  const profileLevels: VolumeProfileLevel[] = rawVols.map((v, i) => {
    const price = Number((low + i * step).toFixed(2))
    let type: VolumeProfileLevel['type'] = 'NORMAL'
    if (i === pocIdx) type = 'POC'
    else if (hvnIdxs.includes(i)) type = 'HVN'
    else if (lvnIdxs.includes(i)) type = 'LVN'
    return {
      price,
      volume: Math.floor(v),
      pct: (v / totalVol) * 100,
      type,
      buyVolume: Math.floor(v * randomBetween(0.4, 0.6)),
      sellVolume: 0, // filled below
      tpoCount: Math.min(8, Math.floor((v / rawVols[pocIdx]) * 7) + 1),
    }
  })
  profileLevels.forEach((l) => (l.sellVolume = l.volume - l.buyVolume))

  return {
    symbol,
    levels: profileLevels,
    poc: Number((low + pocIdx * step).toFixed(2)),
    vah: Number((low + hi * step).toFixed(2)),
    val: Number((low + lo * step).toFixed(2)),
    totalVolume: totalVol,
    range: { high, low },
  }
}

// ───────────────────────────────────────────────────────────────────────
// TPO Profile
// ───────────────────────────────────────────────────────────────────────

export interface TPOLevel {
  price: number
  /** letters (A, B, C, ...) that printed at this price, in time order */
  letters: string[]
  /** number of distinct 30-min periods */
  count: number
  isSinglePrint: boolean
}

export interface TPOProfileData {
  symbol: string
  levels: TPOLevel[]
  /** total number of 30-min periods in the session */
  periodCount: number
  poc: number
  vah: number
  val: number
  singlePrintZones: { from: number; to: number }[]
  poorHigh: boolean
  poorLow: boolean
}

export function generateTPOProfile(symbol: string, levels = 24, periods = 13): TPOProfileData {
  const base = getBasePrice(symbol)
  const range = base * 0.018
  const low = base - range
  const high = base + range
  const step = (high - low) / levels
  const profileLevels: TPOLevel[] = []

  for (let i = 0; i < levels; i++) {
    const dist = Math.abs(i - levels / 2) / (levels / 2)
    const prob = Math.exp(-dist * dist * 2.5) * 0.85
    const letters: string[] = []
    const isSinglePrint = Math.random() < 0.18
    for (let p = 0; p < periods; p++) {
      if (isSinglePrint) {
        // single prints have 1-2 letters only
        if (p < 1 && Math.random() < 0.7) {
          letters.push(String.fromCharCode(65 + p))
        }
      } else if (Math.random() < prob) {
        letters.push(String.fromCharCode(65 + p))
      }
    }
    profileLevels.push({
      price: Number((low + i * step).toFixed(2)),
      letters,
      count: letters.length,
      isSinglePrint: isSinglePrint && letters.length > 0,
    })
  }

  // POC = row with most letters
  const pocIdx = profileLevels.reduce((best, l, i) => (l.count > profileLevels[best].count ? i : best), 0)
  const totalLetters = profileLevels.reduce((s, l) => s + l.count, 0)
  const target = totalLetters * 0.7
  let lo = pocIdx
  let hi = pocIdx
  let acc = profileLevels[pocIdx].count
  while (acc < target && (lo > 0 || hi < profileLevels.length - 1)) {
    const loV = lo > 0 ? profileLevels[lo - 1].count : 0
    const hiV = hi < profileLevels.length - 1 ? profileLevels[hi + 1].count : 0
    if (loV >= hiV && lo > 0) {
      lo--
      acc += loV
    } else if (hi < profileLevels.length - 1) {
      hi++
      acc += hiV
    } else {
      break
    }
  }

  // Detect single print zones
  const singlePrintZones: { from: number; to: number }[] = []
  let inZone = false
  let zoneStart = 0
  for (let i = 0; i < profileLevels.length; i++) {
    if (profileLevels[i].isSinglePrint && !inZone) {
      inZone = true
      zoneStart = i
    } else if (!profileLevels[i].isSinglePrint && inZone) {
      inZone = false
      singlePrintZones.push({
        from: profileLevels[zoneStart].price,
        to: profileLevels[i - 1].price,
      })
    }
  }

  return {
    symbol,
    levels: profileLevels,
    periodCount: periods,
    poc: profileLevels[pocIdx].price,
    vah: profileLevels[hi].price,
    val: profileLevels[lo].price,
    singlePrintZones,
    poorHigh: profileLevels[profileLevels.length - 1].count <= 1,
    poorLow: profileLevels[0].count <= 1,
  }
}

// ───────────────────────────────────────────────────────────────────────
// Time & Sales / Deep Print
// ───────────────────────────────────────────────────────────────────────

export interface Trade {
  id: string
  timestamp: number
  price: number
  size: number
  /** 'BUY' = uptick/lift (hit ask) | 'SELL' = downtick/hit bid */
  side: 'BUY' | 'SELL'
  /** aggression: 'AGGRESSIVE' (lifts offer/hits bid) | 'PASSIVE' (joins queue) */
  aggression: 'AGGRESSIVE' | 'PASSIVE'
  condition?: string
  exchange: 'NSE' | 'BSE'
}

export function generateTrades(symbol: string, count = 80): Trade[] {
  const base = getBasePrice(symbol)
  const now = Date.now()
  const trades: Trade[] = []
  let lastPrice = base
  let trend = randomBetween(-0.002, 0.002)
  for (let i = 0; i < count; i++) {
    const size = Math.floor(
      50 +
        Math.random() ** 1.6 * 4500 +
        (Math.random() < 0.05 ? randomBetween(5000, 30000) : 0),
    )
    if (Math.random() < 0.03) {
      // sweep / iceberg refill
      trend += randomBetween(-0.0008, 0.0008)
    }
    const change = trend * lastPrice + randomBetween(-0.0005, 0.0005) * lastPrice
    lastPrice = Math.max(0.05, lastPrice + change)
    const price = Number(lastPrice.toFixed(2))
    const side: 'BUY' | 'SELL' = change >= 0 ? 'BUY' : 'SELL'
    const condition =
      size > 10000
        ? Math.random() < 0.5
          ? 'BLOCK'
          : 'SWEEP'
        : size > 5000
          ? 'LARGE'
          : undefined
    trades.unshift({
      id: `t-${i}-${Math.random().toString(36).slice(2, 6)}`,
      timestamp: now - i * (randomBetween(80, 800)),
      price,
      size,
      side,
      aggression: 'AGGRESSIVE',
      condition,
      exchange: 'NSE',
    })
  }
  return trades
}

// ───────────────────────────────────────────────────────────────────────
// Initial Balance / Value Area (IB / VAH / VAL)
// ───────────────────────────────────────────────────────────────────────

export interface InitialBalance {
  symbol: string
  ibHigh: number
  ibLow: number
  ibMid: number
  /** IB range (high - low) */
  ibRange: number
  /** current extensions: 1x, 2x, 3x */
  extensions: { x1: number; x2: number; x3: number }
  vah: number
  val: number
  /** period used for IB (in minutes) */
  ibMinutes: number
  /** % of session complete */
  sessionProgress: number
  /** whether the period range is being broken */
  brokeUp: boolean
  brokeDown: boolean
}

export function generateInitialBalance(symbol: string, ibMinutes = 30): InitialBalance {
  const base = getBasePrice(symbol)
  const range = base * 0.012
  const ibHigh = base + range * randomBetween(0.3, 0.8)
  const ibLow = base - range * randomBetween(0.3, 0.8)
  const ibMid = (ibHigh + ibLow) / 2
  const ibRange = ibHigh - ibLow
  // 70% Value Area - widening
  const vah = Number((ibHigh + ibRange * 0.4).toFixed(2))
  const val = Number((ibLow - ibRange * 0.4).toFixed(2))
  return {
    symbol,
    ibHigh: Number(ibHigh.toFixed(2)),
    ibLow: Number(ibLow.toFixed(2)),
    ibMid: Number(ibMid.toFixed(2)),
    ibRange: Number(ibRange.toFixed(2)),
    extensions: {
      x1: Number((ibMid + ibRange * 0.5).toFixed(2)),
      x2: Number((ibMid + ibRange * 1.0).toFixed(2)),
      x3: Number((ibMid + ibRange * 1.5).toFixed(2)),
    },
    vah,
    val,
    ibMinutes,
    sessionProgress: 0.45,
    brokeUp: false,
    brokeDown: false,
  }
}

// ───────────────────────────────────────────────────────────────────────
// Buyside Squeeze bubbles
// ───────────────────────────────────────────────────────────────────────

export interface SqueezeBubble {
  id: string
  timestamp: number
  price: number
  /** size of aggressive buy at ask */
  size: number
  /** number of consecutive prints that triggered this */
  aggregation: number
  /** % above size threshold */
  trigger: number
  /** side */
  side: 'BUY' | 'SELL'
  /** subsequent bar movement in % (0..1) */
  result?: number
}

export function generateSqueezeBubbles(symbol: string, count = 40): SqueezeBubble[] {
  const base = getBasePrice(symbol)
  const now = Date.now()
  const bubbles: SqueezeBubble[] = []
  let lastPrice = base
  for (let i = 0; i < count; i++) {
    const isBuy = Math.random() < 0.55
    if (isBuy) {
      const size = Math.floor(800 + Math.random() ** 1.4 * 6000 + (Math.random() < 0.1 ? 12000 : 0))
      const agg = Math.floor(randomBetween(2, 7))
      lastPrice = lastPrice + randomBetween(-0.0015, 0.004) * lastPrice
      bubbles.push({
        id: `sq-${i}`,
        timestamp: now - i * randomBetween(15_000, 90_000),
        price: Number(lastPrice.toFixed(2)),
        size,
        aggregation: agg,
        trigger: Math.min(2.5, size / 1500),
        side: 'BUY',
        result: Math.random(),
      })
    } else {
      lastPrice = lastPrice + randomBetween(-0.004, 0.0015) * lastPrice
    }
  }
  return bubbles.reverse()
}

// ───────────────────────────────────────────────────────────────────────
// DOM Heatmap (cumulative heat over time)
// ───────────────────────────────────────────────────────────────────────

export interface DOMHeatCell {
  price: number
  /** 0..1 normalized heat intensity (size + persistence) */
  bidHeat: number
  askHeat: number
  bidSize: number
  askSize: number
  /** 0..1 — how stable / persistent this level was */
  bidStability: number
  askStability: number
  /** is this a "natural price magnet" — high heat + high stability */
  isMagnet?: boolean
  /** completed a "reliable test" — price tested and bounced */
  reliableTest?: boolean
  /** is this a "low slippage" zone for aggressive players */
  lowSlippage?: boolean
}

export interface DOMHeatmapData {
  symbol: string
  midPrice: number
  cells: DOMHeatCell[]
  /** highlighted magnet prices */
  magnets: number[]
}

export function generateDOMHeatmap(symbol: string, levels = 20): DOMHeatmapData {
  const base = getBasePrice(symbol)
  const cells: DOMHeatCell[] = []
  const magnets: number[] = []
  for (let i = 0; i < levels; i++) {
    const dist = Math.abs(i - levels / 2) / (levels / 2)
    const heat = Math.max(0.1, 1 - dist * 0.7)
    const stability = Math.max(0.2, 1 - dist * 0.6)
    const bidHeat = heat * (0.6 + Math.random() * 0.5)
    const askHeat = heat * (0.6 + Math.random() * 0.5)
    const bidSize = Math.floor(1000 * bidHeat + randomBetween(0, 1500))
    const askSize = Math.floor(1000 * askHeat + randomBetween(0, 1500))
    const price = Number((base - (levels / 2 - i) * 0.05).toFixed(2))
    const isMagnet = bidHeat > 0.8 && stability > 0.7
    if (isMagnet) magnets.push(price)
    cells.push({
      price,
      bidHeat: Math.min(1, bidHeat),
      askHeat: Math.min(1, askHeat),
      bidSize,
      askSize,
      bidStability: stability * (0.7 + Math.random() * 0.4),
      askStability: stability * (0.7 + Math.random() * 0.4),
      isMagnet,
      reliableTest: Math.random() < 0.25,
      lowSlippage: heat > 0.6 && stability > 0.55,
    })
  }
  return { symbol, midPrice: Number(base.toFixed(2)), cells, magnets }
}
