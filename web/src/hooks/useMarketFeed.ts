import { useEffect, useRef, useState } from "react";
import { WsClient, type WsStatus } from "../api/ws";
import { WS_BASE } from "../api/config";
import type { WsMessage } from "../types";

export interface MarketFeedState {
  status: WsStatus;
  /** Latest quote per symbol, keyed by symbol. */
  quotes: Record<string, WsMessage & { type: "quote" }>;
}

/**
 * Subscribe to live quotes for `symbols` over the market WebSocket.
 * Falls back to a no-op if no symbols are provided.
 */
export function useMarketFeed(symbols: string[]): MarketFeedState {
  const [status, setStatus] = useState<WsStatus>("closed");
  const [quotes, setQuotes] = useState<Record<string, WsMessage & { type: "quote" }>>({});
  const clientRef = useRef<WsClient | null>(null);

  useEffect(() => {
    if (symbols.length === 0) return;
    const url = `${WS_BASE || ""}/ws/market`;
    const client = new WsClient(url);
    clientRef.current = client;
    client.onStatus(setStatus);
    client.onMessage((m) => {
      if (m.type === "quote") {
        setQuotes((prev) => ({ ...prev, [m.symbol]: m }));
      }
    });
    client.connect();
    client.subscribe(symbols);

    return () => {
      client.unsubscribe(symbols);
      client.close();
      clientRef.current = null;
    };
  }, [symbols.join(",")]);

  return { status, quotes };
}
