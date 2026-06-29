/**
 * useNews — fetches market/instrument news from backend.
 *
 * Polls the /api/v1/news endpoint periodically and provides
 * news items to the NewsTicker component.
 */

import { useEffect, useState, useCallback } from 'react'

export interface NewsItem {
  headline: string
  summary: string
  symbol: string
  category: string
  source: string
  timestamp: string
  url: string | null
}

interface UseNewsOptions {
  symbol?: string
  category?: string
  limit?: number
  pollIntervalMs?: number
  enabled?: boolean
}

interface UseNewsResult {
  items: NewsItem[]
  loading: boolean
  error: string | null
  refresh: () => void
}

const DEFAULT_POLL_INTERVAL = 60_000 // 1 minute

export function useNews(opts: UseNewsOptions = {}): UseNewsResult {
  const {
    symbol,
    category,
    limit = 20,
    pollIntervalMs = DEFAULT_POLL_INTERVAL,
    enabled = true,
  } = opts

  const [items, setItems] = useState<NewsItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchNews = useCallback(async () => {
    if (!enabled) return
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (symbol) params.set('symbol', symbol)
      if (category) params.set('category', category)
      params.set('limit', String(limit))

      const resp = await fetch(`/api/v1/news?${params.toString()}`)
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}))
        throw new Error(body.detail ?? `HTTP ${resp.status}`)
      }
      const data = await resp.json()
      setItems(data.items ?? [])
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [symbol, category, limit, enabled])

  useEffect(() => {
    fetchNews()
    if (!enabled) return
    const id = setInterval(fetchNews, pollIntervalMs)
    return () => clearInterval(id)
  }, [fetchNews, pollIntervalMs, enabled])

  return { items, loading, error, refresh: fetchNews }
}
