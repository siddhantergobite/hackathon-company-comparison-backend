import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const BACKEND = process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8765';

// The FastAPI backend serves the production build at /casefile/, so the app
// is built with that base path. In dev, /api calls are proxied to the backend.
export default defineConfig({
  base: '/casefile/',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true, timeout: 0, proxyTimeout: 0 },
      '/health': { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
