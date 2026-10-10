import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The frontend lives in `frontend/`; the production build is emitted to
// `dist/` at the repo root, where the FastAPI backend serves it from.
export default defineConfig({
  root: 'frontend',
  plugins: [react()],
  build: {
    outDir: '../dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      // In development, API calls reach the backend on :8000.
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
