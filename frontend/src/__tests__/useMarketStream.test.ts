import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useMarketStream, __resetMarketStreamForTests } from '../hooks/useMarketStream'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 3
  url: string
  readyState = MockWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onmessage: ((ev: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  sent: string[] = []

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.()
  }

  simulateOpen() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.()
  }

  simulateMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) })
  }
}

describe('useMarketStream', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    Object.defineProperty(globalThis, 'location', {
      value: { protocol: 'http:', host: 'localhost:5173' },
      configurable: true,
    })
    __resetMarketStreamForTests()
  })

  afterEach(() => {
    __resetMarketStreamForTests()
    vi.unstubAllGlobals()
  })

  it('connects to /ws/market and sends subscribe message', async () => {
    const { result } = renderHook(() =>
      useMarketStream({ symbols: ['RELIANCE', 'TCS'], enabled: true }),
    )

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBeGreaterThan(0)
    }, { timeout: 3000 })

    const ws = MockWebSocket.instances[0]
    expect(ws.url).toContain('/ws/market')

    act(() => {
      ws.simulateOpen()
    })

    await waitFor(() => {
      expect(ws.sent.some((s) => {
        const body = JSON.parse(s)
        return body.action === 'subscribe' && body.symbols.includes('RELIANCE')
      })).toBe(true)
    })

    act(() => {
      ws.simulateMessage({ type: 'quote', symbol: 'RELIANCE', ltp: 2500.5, ts: Date.now() })
    })

    await waitFor(() => {
      expect(result.current.quotes.RELIANCE?.ltp).toBe(2500.5)
    })
  })
})
