/**
 * Tiny formatting utilities.
 */

import { type ClassValue, clsx } from 'clsx'

export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs)
}

export function formatIN(value: number, decimals = 2): string {
  if (!Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('en-IN', {
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
  }).format(value)
}

export function formatCompact(value: number): string {
  if (!Number.isFinite(value)) return '—'
  const abs = Math.abs(value)
  if (abs >= 1e7) return (value / 1e7).toFixed(2) + 'Cr'
  if (abs >= 1e5) return (value / 1e5).toFixed(2) + 'L'
  if (abs >= 1e3) return (value / 1e3).toFixed(2) + 'K'
  return value.toFixed(0)
}

export function formatNumber(value: number, decimals = 0): string {
  if (!Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('en-IN', {
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
  }).format(value)
}

export function formatPercent(v: number, decimals = 2): string {
  if (!Number.isFinite(v)) return '—'
  const s = v >= 0 ? '+' : ''
  return s + v.toFixed(decimals) + '%'
}

export function formatTime(ts: number, withSeconds = true): string {
  const d = new Date(ts)
  return d.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: withSeconds ? '2-digit' : undefined,
    hour12: false,
  })
}

export function formatDateShort(ts: number): string {
  const d = new Date(ts)
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
}

export function pnlColor(v: number): string {
  if (v > 0) return 'text-bull'
  if (v < 0) return 'text-bear'
  return 'text-bfgm'
}

export function timeAgo(ts: number | Date): string {
  const d = typeof ts === 'object' ? ts.getTime() : ts
  const seconds = Math.floor((Date.now() - d) / 1000)
  if (seconds < 5)    return 'just now'
  if (seconds < 60)   return `${seconds}s ago`
  const m = Math.floor(seconds / 60)
  if (m < 60)         return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24)         return `${h}h ago`
  const days = Math.floor(h / 24)
  if (days < 30)      return `${days}d ago`
  const months = Math.floor(days / 30)
  if (months < 12)    return `${months}mo ago`
  return `${Math.floor(months / 12)}y ago`
}
