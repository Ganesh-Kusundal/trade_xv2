/**
 * NewsTicker — horizontally scrolling news headline bar.
 *
 * CSS-animated marquee. Pauses on hover. Uses real news from backend
 * via useNews hook.
 */

import { useMemo } from 'react'
import { Newspaper, TrendingUp, TrendingDown, AlertCircle, Building2, Landmark, Scale } from 'lucide-react'
import { useNews } from '@/hooks/useNews'
import { cn, timeAgo } from '@/lib/utils'

const CAT_ICON: Record<string, typeof TrendingUp> = {
  EARNINGS: TrendingUp,
  CORP: Building2,
  MARKET: TrendingDown,
  TECH: AlertCircle,
  MACRO: Landmark,
  REGULATORY: Scale,
}

const CAT_COLOR: Record<string, string> = {
  EARNINGS: 'text-bull',
  CORP: 'text-bcy',
  MARKET: 'text-bfg',
  TECH: 'text-warning',
  MACRO: 'text-accent',
  REGULATORY: 'text-bear',
}

export function NewsTicker() {
  const { items: realNews, loading, error } = useNews({ limit: 20 })

  // Map real news items to display format
  const news = useMemo(() => {
    if (realNews.length === 0 || error) return []
    return realNews.map((n) => ({
      t: n.timestamp ? new Date(n.timestamp).getTime() : Date.now(),
      symbol: n.symbol,
      category: (n.category.toUpperCase() as string) || 'MARKET',
      headline: n.headline,
      source: n.source,
    }))
  }, [realNews, error])

  // Duplicate the list so the marquee loops seamlessly
  const items = useMemo(() => [...news, ...news], [news])

  if (items.length === 0 && !loading) {
    return (
      <div className="flex items-center h-7 border-t border-bline bg-bbg1 overflow-hidden">
        <div className="flex items-center gap-1.5 px-2 border-r border-bline bg-bbg2 text-bamb">
          <Newspaper className="h-3 w-3" />
          <span className="text-2xs font-semibold uppercase tracking-wider">News</span>
        </div>
        <div className="flex-1 flex items-center justify-center text-2xs text-fg-dim">
          No news available
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-stretch h-7 border-t border-bline bg-bbg1 overflow-hidden">
      {/* Label */}
      <div className="flex items-center gap-1.5 px-2 border-r border-bline bg-bbg2 text-bamb">
        <Newspaper className="h-3 w-3" />
        <span className="text-2xs font-semibold uppercase tracking-wider">News</span>
      </div>

      {/* Marquee */}
      <div className="flex-1 relative overflow-hidden group">
        <div className="absolute inset-y-0 left-0 w-6 bg-gradient-to-r from-bbg1 to-transparent z-10 pointer-events-none" />
        <div className="absolute inset-y-0 right-0 w-6 bg-gradient-to-l from-bbg1 to-transparent z-10 pointer-events-none" />
        <div className="flex h-full items-center gap-6 whitespace-nowrap animate-marquee group-hover:[animation-play-state:paused]">
          {items.map((n, i) => {
            const Icon = CAT_ICON[n.category] ?? TrendingDown
            const color = CAT_COLOR[n.category] ?? 'text-fg-dim'
            return (
              <span key={i} className="flex items-center gap-1.5 text-2xs font-mono num">
                <Icon className={cn('h-3 w-3', color)} />
                <span className={cn('font-semibold', color)}>
                  [{n.symbol}]
                </span>
                <span className="text-fg">{n.headline}</span>
                <span className="text-fg-dim">— {n.source} · {timeAgo(n.t)}</span>
                <span className="text-bfgd">|</span>
              </span>
            )
          })}
        </div>
      </div>
    </div>
  )
}
