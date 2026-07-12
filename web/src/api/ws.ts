/**
 * Minimal WebSocket client for the TradeXV2 market feed.
 *
 * Server protocol (src/interface/api/ws/market.py):
 *   Client -> Server: { action: "subscribe", symbols: [...] }
 *                    { action: "unsubscribe", symbols: [...] }
 *                    { action: "ping" }
 *   Server -> Client: { type: "quote", symbol, ltp, ... }
 *                     { type: "candle", symbol, timeframe, ... }
 *                     { type: "subscribed" | "unsubscribed", symbols }
 *                     { type: "pong" }
 *                     { type: "error", reason, message }
 *
 * ASSUMPTION / BACKEND GAP: the server authenticates the WS via the
 * `x-api-key` *header*, which browsers cannot set on a WebSocket
 * handshake. So `apiKey` here is currently a no-op for browser clients;
 * run the backend with `AUTH_MODE=none` (see web/README) for local WS,
 * or patch the server to accept the key as a query param. The client
 * still sends the key as a query param as a forward-compatible hint.
 */
import type { WsMessage } from "../types";
import { API_KEY, WS_BASE } from "./config";

export type WsStatus = "connecting" | "open" | "closed" | "error";

export class WsClient {
  private ws: WebSocket | null = null;
  private status: WsStatus = "closed";
  private statusCb?: (s: WsStatus) => void;
  private messageCb?: (m: WsMessage) => void;

  constructor(
    private readonly url: string,
    private readonly apiKey?: string,
  ) {}

  onStatus(cb: (s: WsStatus) => void): void {
    this.statusCb = cb;
  }
  onMessage(cb: (m: WsMessage) => void): void {
    this.messageCb = cb;
  }

  connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    this.setStatus("connecting");

    let wsUrl = this.url;
    if (this.apiKey && !wsUrl.includes("api_key")) {
      const sep = wsUrl.includes("?") ? "&" : "?";
      wsUrl += `${sep}api_key=${encodeURIComponent(this.apiKey)}`;
    }
    if (this.apiKey && typeof WebSocket !== "undefined") {
      // Browsers ignore custom headers on WS; log the limitation once.
      console.warn(
        "[WsClient] Backend expects x-api-key as a header, which browsers " +
          "cannot set on a WebSocket. Passing it as a query param as a hint; " +
          "run the backend with AUTH_MODE=none for local WS.",
      );
    }

    try {
      this.ws = new WebSocket(wsUrl);
    } catch (e) {
      this.setStatus("error");
      console.error("[WsClient] failed to construct socket", e);
      return;
    }

    this.ws.onopen = () => this.setStatus("open");
    this.ws.onclose = () => this.setStatus("closed");
    this.ws.onerror = () => this.setStatus("error");
    this.ws.onmessage = (ev: MessageEvent) => {
      try {
        const msg = JSON.parse(ev.data as string) as WsMessage;
        this.messageCb?.(msg);
      } catch {
        /* ignore malformed frames */
      }
    };
  }

  subscribe(symbols: string[]): void {
    this.send({ action: "subscribe", symbols });
  }
  unsubscribe(symbols: string[]): void {
    this.send({ action: "unsubscribe", symbols });
  }
  ping(): void {
    this.send({ action: "ping" });
  }

  close(): void {
    this.ws?.close();
    this.ws = null;
    this.setStatus("closed");
  }

  private send(obj: unknown): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(obj));
    }
  }
  private setStatus(s: WsStatus): void {
    this.status = s;
    this.statusCb?.(s);
  }
}
