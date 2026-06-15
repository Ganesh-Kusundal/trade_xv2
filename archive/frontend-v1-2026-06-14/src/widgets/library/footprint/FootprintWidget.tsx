/**
 * Footprint Candles Widget
 *
 * DeepCharts-style footprint chart: each candle is split into a ladder of
 * price levels. At every level, you can see:
 *   - bid volume (sellers hit by buyers below the level)
 *   - ask volume (buyers lifted from sellers above the level)
 *   - delta (ask - bid) — coloured by sign
 *   - POC / HVN / LVN markers
 *   - Detected iceberg (large passive refill)
 *
 * Reference: https://www.deepcharts.com/features/deepdom
 */

import { useMemo, useRef, useState, useEffect } from 'react'
import { WidgetFrame } from '../../WidgetFrame'
import type { WidgetProps } from '../../Widget'
import { cn, formatIN, formatNumber, pnlColor } from '@/lib/utils'
import {
  generateFootprintCandles,
  type FootprintCandle,
  type FootprintLevel,
} from '@/services/deepchartsData'
import { ChevronLeft, ChevronRight, Maximize2, Minimize2 } from 'lucide-react'

interface FootprintConfig {
  symbol?: string
  bars?: number
  levelsPerBar?: number
  title?: string
  /** show historical bar delta summaries in left rail */
  showDeltaSummary?: boolean
  /** highlight icebergs */
  showIcebergs?: boolean
}

const MAX_LEVEL_VOLUME_DEFAULT = 800

export default function FootprintWidget({
  config,
  refresh,
  loading,
  lastUpdated,
}: WidgetProps<FootprintConfig>) {
  const symbol = config.symbol || 'NIFTY'
  const bars = config.bars || 24
  const levelsPerBar = config.levelsPerBar || 12
  const [candles, setCandles] = useState<FootprintCandle[]>([])
  const [activeIdx, setActiveIdx] = useState(0)
  const [zoom, setZoom] = useState(1)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Generate (and re-generate on refresh) the candle ladder
  const reload = () => {
    const next = generateFootprintCandles(symbol, bars, levelsPerBar)
    setCandles(next)
    setActiveIdx(next.length - 1)
  }

  useEffect(() => {
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, bars, levelsPerBar])

  const active = candles[activeIdx]
  const maxVol = useMemo(() => {
    if (!candles.length) return MAX_LEVEL_VOLUME_DEFAULT
    let m = 0
    for (const c of candles) {
      for (const l of c.levels) {
        m = Math.max(m, l.bidVolume, l.askVolume)
      }
    }
    return m || MAX_LEVEL_VOLUME_DEFAULT
  }, [candles])

  // auto-scroll to latest on new data
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollLeft = scrollRef.current.scrollWidth
    }
  }, [candles.length])

  return (
    <WidgetFrame
      id=""
      config={{ ...config, title: `FOOTPRINT - ${symbol}` }}
      loading={loading}
      lastUpdated={lastUpdated}
      refresh={() => {
        reload()
        refresh()
      }}
    >
      <div className="flex flex-col h-full">
        {/* Top delta / volume summary rail */}
        {active && (
          <div className="px-2 py-1.5 border-b border-line bg-bg-2/40 grid grid-cols-6 gap-2 text-2xs">
            <div>
              <div className="text-fg-dim uppercase tracking-wider text-[10px]">Time</div>
              <div className="font-mono num font-semibold text-fg">{active.label}</div>
            </div>
            <div>
              <div className="text-fg-dim uppercase tracking-wider text-[10px]">OHLC</div>
              <div className="font-mono num text-fg">
                <span className="text-bullish">{formatIN(active.open)}</span>{' '}
                <span className="text-bearish">{formatIN(active.low)}</span>{' '}
                <span className="text-bullish">{formatIN(active.high)}</span>{' '}
                <span className={cn('font-semibold', pnlColor(active.close - active.open))}>
                  {formatIN(active.close)}
                </span>
              </div>
            </div>
            <div>
              <div className="text-fg-dim uppercase tracking-wider text-[10px]">Volume</div>
              <div className="font-mono num text-fg">{formatNumber(active.volume)}</div>
            </div>
            <div>
              <div className="text-fg-dim uppercase tracking-wider text-[10px]">Delta</div>
              <div className={cn('font-mono num font-semibold', pnlColor(active.totalDelta))}>
                {active.totalDelta > 0 ? '+' : ''}
                {formatNumber(active.totalDelta)}
              </div>
            </div>
            <div>
              <div className="text-fg-dim uppercase tracking-wider text-[10px]">Cum Delta</div>
              <div
                className={cn(
                  'font-mono num font-semibold',
                  pnlColor(candles.slice(0, activeIdx + 1).reduce((s, c) => s + c.totalDelta, 0)),
                )}
              >
                {formatNumber(
                  candles.slice(0, activeIdx + 1).reduce((s, c) => s + c.totalDelta, 0),
                )}
              </div>
            </div>
            <div className="flex items-center justify-end gap-1">
              <button
                onClick={() => setZoom((z) => Math.max(0.6, z - 0.2))}
                className="h-5 w-5 rounded hover:bg-bg-3 text-fg-dim hover:text-fg flex items-center justify-center"
                title="Zoom out"
              >
                <Minimize2 className="h-3 w-3" />
              </button>
              <button
                onClick={() => setZoom((z) => Math.min(2, z + 0.2))}
                className="h-5 w-5 rounded hover:bg-bg-3 text-fg-dim hover:text-fg flex items-center justify-center"
                title="Zoom in"
              >
                <Maximize2 className="h-3 w-3" />
              </button>
            </div>
          </div>
        )}

        {/* Footprint ladder — horizontal scroll for multiple bars */}
        <div
          ref={scrollRef}
          className="flex-1 min-h-0 overflow-x-auto overflow-y-auto"
          style={{ scrollBehavior: 'smooth' }}
        >
          <div
            className="inline-flex h-full"
            style={{ minWidth: '100%', transform: `scaleX(${zoom})`, transformOrigin: 'left top' }}
          >
            {candles.map((c, idx) => (
              <FootprintColumn
                key={c.timestamp}
                candle={c}
                maxVol={maxVol}
                isActive={idx === activeIdx}
                onClick={() => setActiveIdx(idx)}
                showIcebergs={config.showIcebergs !== false}
                showSummary={config.showDeltaSummary !== false}
              />
            ))}
          </div>
        </div>

        {/* Bottom nav */}
        <div className="flex items-center justify-between px-2 py-1 border-t border-line bg-bg-2/30 text-2xs">
          <div className="flex items-center gap-1">
            <button
              onClick={() => setActiveIdx((i) => Math.max(0, i - 1))}
              disabled={activeIdx === 0}
              className="h-5 w-5 rounded hover:bg-bg-3 disabled:opacity-30 text-fg-dim hover:text-fg flex items-center justify-center"
            >
              <ChevronLeft className="h-3 w-3" />
            </button>
            <span className="font-mono num text-fg-muted">
              {activeIdx + 1} / {candles.length}
            </span>
            <button
              onClick={() => setActiveIdx((i) => Math.min(candles.length - 1, i + 1))}
              disabled={activeIdx === candles.length - 1}
              className="h-5 w-5 rounded hover:bg-bg-3 disabled:opacity-30 text-fg-dim hover:text-fg flex items-center justify-center"
            >
              <ChevronRight className="h-3 w-3" />
            </button>
          </div>
          <div className="flex items-center gap-3 text-fg-dim">
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-bullish/40" /> Bid
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-bearish/40" /> Ask
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-warning" /> POC
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-accent" /> Iceberg
            </span>
          </div>
        </div>
      </div>
    </WidgetFrame>
  )
}

// ─── FootprintColumn — a single candle's ladder ──────────────────────

function FootprintColumn({
  candle,
  maxVol,
  isActive,
  onClick,
  showIcebergs,
  showSummary,
}: {
  candle: FootprintCandle
  maxVol: number
  isActive: boolean
  onClick: () => void
  showIcebergs: boolean
  showSummary: boolean
}) {
  const [hoveredPrice, setHoveredPrice] = useState<number | null>(null)
  return (
    <div
      onClick={onClick}
      className={cn(
        'flex flex-col border-r border-line-subtle min-w-[110px] flex-shrink-0 cursor-pointer',
        isActive ? 'bg-brand/5' : 'hover:bg-bg-2/30',
      )}
    >
      {/* Header — OHLC and delta */}
      <div className="px-1.5 py-1 border-b border-line-subtle text-center">
        <div className="text-[10px] text-fg-dim font-mono num">{candle.label}</div>
        {showSummary && (
          <div
            className={cn(
              'text-2xs font-mono num font-semibold',
              pnlColor(candle.totalDelta),
            )}
          >
            {candle.totalDelta > 0 ? '+' : ''}
            {formatNumber(candle.totalDelta)}
          </div>
        )}
      </div>

      {/* Levels ladder (low to high) */}
      <div className="flex-1 flex flex-col">
        {candle.levels.map((lvl) => (
          <FootprintRow
            key={lvl.price}
            level={lvl}
            maxVol={maxVol}
            showIcebergs={showIcebergs}
            onHover={(p) => setHoveredPrice(p)}
            highlighted={hoveredPrice === lvl.price}
          />
        ))}
      </div>
    </div>
  )
}

// ─── FootprintRow — single price row (bid | price | ask) ─────────────

function FootprintRow({
  level,
  maxVol,
  showIcebergs,
  onHover,
  highlighted,
}: {
  level: FootprintLevel
  maxVol: number
  showIcebergs: boolean
  onHover: (p: number | null) => void
  highlighted: boolean
}) {
  const bidW = (level.bidVolume / maxVol) * 100
  const askW = (level.askVolume / maxVol) * 100
  const deltaSign = level.delta >= 0 ? 'text-bullish' : 'text-bearish'
  const bg = highlighted ? 'bg-brand/15' : level.isPOC ? 'bg-warning/10' : ''
  return (
    <div
      onMouseEnter={() => onHover(level.price)}
      onMouseLeave={() => onHover(null)}
      className={cn('grid grid-cols-[1fr_auto_1fr] text-[10px] font-mono num items-stretch', bg)}
    >
      {/* Bid cell */}
      <div className="flex items-center justify-end pr-1 h-[18px] relative border-r border-line-subtle/40">
        {level.bidVolume > 0 && (
          <div
            className="absolute inset-y-0 right-0 bg-bullish/15"
            style={{ width: `${bidW}%` }}
          />
        )}
        <span className="relative text-bullish/90">
          {level.bidVolume > 0 ? formatNumber(level.bidVolume) : ''}
        </span>
      </div>

      {/* Price cell with markers */}
      <div
        className={cn(
          'px-1.5 h-[18px] flex items-center justify-center min-w-[42px] relative',
          level.isPOC && 'text-warning font-semibold',
          level.isHVN && !level.isPOC && 'text-info',
          level.isLVN && 'text-fg-dim',
        )}
      >
        {level.isIceberg && showIcebergs && (
          <span className="absolute -left-0.5 top-1/2 -translate-y-1/2 h-1.5 w-1.5 rounded-full bg-accent shadow-[0_0_4px_rgb(168,85,247,0.8)]" />
        )}
        {level.isPOC && (
          <span className="absolute -left-0.5 top-1/2 -translate-y-1/2 h-1.5 w-1.5 rounded-full bg-warning" />
        )}
        <span>{formatIN(level.price, 2)}</span>
      </div>

      {/* Ask cell */}
      <div className="flex items-center justify-start pl-1 h-[18px] relative border-l border-line-subtle/40">
        {level.askVolume > 0 && (
          <div
            className="absolute inset-y-0 left-0 bg-bearish/15"
            style={{ width: `${askW}%` }}
          />
        )}
        <span className="relative text-bearish/90">
          {level.askVolume > 0 ? formatNumber(level.askVolume) : ''}
        </span>
      </div>
    </div>
  )
}
