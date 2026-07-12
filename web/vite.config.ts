/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Vite dev server proxies API + WebSocket traffic to the running TradeXV2
// FastAPI backend (default http://127.0.0.1:8080). Using a proxy means the
// SPA talks to a same-origin URL ("/api", "/ws"), which:
//   1. avoids browser CORS preflight issues in dev, and
//   2. lets the dev server forward the X-API-Key header to the backend.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8080", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:8080", ws: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**", "dist/**"],
  },
});
