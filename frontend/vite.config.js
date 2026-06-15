import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
// ESM-safe __dirname equivalent. The project is `"type": "module"`, so
// the CommonJS `__dirname` global is not available; we derive it from
// `import.meta.url` instead.
var __dirname = path.dirname(fileURLToPath(import.meta.url));
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: { '@': path.resolve(__dirname, './src') },
    },
    server: {
        port: 5173,
        host: true,
        proxy: {
            '/api': { target: 'http://localhost:8000', changeOrigin: true },
            '/ws': { target: 'ws://localhost:8000', ws: true, changeOrigin: true },
        },
    },
    build: { outDir: 'dist', sourcemap: false },
});
