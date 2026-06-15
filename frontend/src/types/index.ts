/**
 * Domain types shared across the app.
 * These match the JSON shapes the backend will return (see BACKEND_API_SPEC.md).
 */

export type Exchange = 'NSE' | 'BSE' | 'MCX'
export type Segment = 'EQ' | 'FO' | 'CD' | 'COM'

export type Timeframe = '1m' | '3m' | '5m' | '15m' | '30m' | '1h' | '4h' | '1d' | '1w'

export interface Symbol {
  symbol: string
  name: string
  exchange: Exchange
  segment: Segment
  isin: string
  lotSize: number
  tickSize: number
  sector?: string
}

export interface Quote {
  symbol: string
  exchange: Exchange
  ltp: number
  open: number
  high: number
  low: number
  prevClose: number
  change: number
  changePct: number
  volume: number
  bid: number
  ask: number
  bidQty: number
  askQty: number
  ts: number
}

export interface Candle {
  /** open-time, epoch ms */
  t: number
  o: number
  h: number
  l: number
  c: number
  v: number
}

export interface CandlesResponse {
  symbol: string
  exchange: Exchange
  timeframe: Timeframe
  candles: Candle[]
}

export type ReplayState = 'IDLE' | 'PLAYING' | 'PAUSED' | 'ENDED'

export interface ReplaySession {
  id: string
  symbol: string
  exchange: Exchange
  timeframe: Timeframe
  from_t: number
  to_t: number
  cursor_t: number
  state: ReplayState
  speed: number
}

export interface ReplayEvent {
  type: 'replay_candle' | 'replay_quote' | 'replay_state' | 'replay_end' | 'error'
  session_id?: string
  candle?: Candle
  ltp?: number
  ts?: number
  state?: ReplayState
  speed?: number
  cursor_t?: number
  code?: string
  message?: string
}
