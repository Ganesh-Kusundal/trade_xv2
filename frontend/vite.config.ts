import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// ESM-safe __dirname equivalent. The project is `"type": "module"`, so
// the CommonJS `__dirname` global is not available; we derive it from
// `import.meta.url` instead.
const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
    host: true,
    proxy: {
      // Forward /api and /ws to the Python FastAPI backend when it's
      // running on :8000. When the backend is down, the frontend
      // transparently falls back to its in-memory mock generators
      // (see src/api/client.ts).
      //
      // We pass `bypass: () => undefined` to keep the proxy active
      // even for paths the Vite dev server can't resolve — the
      // ECONNREFUSED is the expected state during local dev and the
      // frontend handles it.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws':  { target: 'ws://localhost:8000', ws: true, changeOrigin: true },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
