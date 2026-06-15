/**
 * useWidgetData — the standard data-fetching hook for widgets.
 *
 * Wraps a fetcher with:
 *   - Auto-refresh on an interval
 *   - Manual refresh trigger
 *   - Loading / error / lastUpdated state
 *   - Mount-aware cleanup
 *
 * Usage:
 *   const { data, loading, refresh, lastUpdated } = useWidgetData({
 *     fetcher: () => fetchQuotes(['RELIANCE', 'TCS']),
 *     intervalMs: 1500,
 *   })
 */

import { useCallback, useEffect, useRef, useState } from 'react'

interface UseWidgetDataOptions<T> {
  fetcher: () => T | Promise<T>
  /** Auto-refresh interval in ms. Set to 0 to disable. */
  intervalMs?: number
  /** Skip the first auto-fetch (useful when the widget starts paused). */
  skipInitial?: boolean
  /** Stop fetching when document hidden. */
  pauseOnHidden?: boolean
}

interface UseWidgetDataResult<T> {
  data: T | undefined
  loading: boolean
  error: Error | null
  refresh: () => Promise<void>
  lastUpdated: number | undefined
}

export function useWidgetData<T>({
  fetcher,
  intervalMs = 0,
  skipInitial = false,
  pauseOnHidden = true,
}: UseWidgetDataOptions<T>): UseWidgetDataResult<T> {
  const [data, setData] = useState<T | undefined>(undefined)
  const [loading, setLoading] = useState(!skipInitial)
  const [error, setError] = useState<Error | null>(null)
  const [lastUpdated, setLastUpdated] = useState<number | undefined>(undefined)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetcherRef.current()
      setData(result)
      setLastUpdated(Date.now())
    } catch (err) {
      setError(err as Error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!skipInitial) {
      refresh()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (intervalMs <= 0) return
    const tick = () => {
      if (pauseOnHidden && document.hidden) return
      refresh()
    }
    const id = window.setInterval(tick, intervalMs)
    return () => window.clearInterval(id)
  }, [intervalMs, pauseOnHidden, refresh])

  return { data, loading, error, refresh, lastUpdated }
}
