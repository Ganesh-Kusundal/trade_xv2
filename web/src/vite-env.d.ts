/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the TradeXV2 FastAPI backend. Empty = same-origin (use Vite proxy). */
  readonly VITE_API_BASE?: string;
  /** WebSocket base URL. Empty = same-origin (use Vite proxy). */
  readonly VITE_WS_BASE?: string;
  /** API key sent as X-API-Key. Only needed when backend AUTH_MODE=api_key. */
  readonly VITE_API_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
