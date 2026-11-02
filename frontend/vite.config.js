import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies every backend path to the FastAPI service, so the
// browser only ever talks to one origin (works locally and behind a preview URL).
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    allowedHosts: ['.e2b.app', '.arena.ai', 'all'],
    hmr: { clientPort: 443, protocol: 'wss' },
    proxy: {
      '/monitor': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/users': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/products': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/secure-data': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/metrics': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/docs': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/openapi.json': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
