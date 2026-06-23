import { renderHook, act } from '@testing-library/react'
import { useAppStore } from '../store/app'

describe('useAppStore', () => {
  it('has default active symbol', () => {
    const { result } = renderHook(() => useAppStore())
    expect(result.current.activeSymbol).toBe('RELIANCE')
  })

  it('can set active symbol', () => {
    const { result } = renderHook(() => useAppStore())
    act(() => {
      result.current.setActiveSymbol('TCS')
    })
    expect(result.current.activeSymbol).toBe('TCS')
  })

  it('normalizes symbol to uppercase', () => {
    const { result } = renderHook(() => useAppStore())
    act(() => {
      result.current.setActiveSymbol('infy')
    })
    expect(result.current.activeSymbol).toBe('INFY')
  })

  it('can add to watchlist', () => {
    const { result } = renderHook(() => useAppStore())
    act(() => {
      result.current.addToWatchlist('HDFCBANK')
    })
    expect(result.current.watchlist).toContain('HDFCBANK')
  })

  it('can remove from watchlist', () => {
    const { result } = renderHook(() => useAppStore())
    act(() => {
      result.current.removeFromWatchlist('RELIANCE')
    })
    expect(result.current.watchlist).not.toContain('RELIANCE')
  })
})