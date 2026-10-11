import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// The frontend lives in `frontend/`; the production build is emitted to
// `dist/` at the repo root, where the FastAPI backend serves it from.
export default defineConfig({
  root: 'frontend',
  plugins: [
    react(),
    VitePWA({
      // Registration is injected automatically at build time; a new service
      // worker takes over as soon as a deployment updates (no stale cache).
      registerType: 'autoUpdate',
      // The OutStep manifest is hand-written (frontend/public/manifest.webmanifest)
      // with the approved branding; the plugin must not emit a second one.
      manifest: false,
      workbox: {
        // Precache the app shell (html/js/css) plus the icons the installed
        // app and the header need offline. The full logo (README-only) is
        // deliberately excluded to keep the precache small.
        globPatterns: ['**/*.{js,css,html,ico,svg,webmanifest,png}'],
        globIgnores: ['outstep-logo-full.png'],
        // SPA navigation works offline; API routes always hit the network.
        navigateFallback: 'index.html',
        navigateFallbackDenylist: [/^\/api\//],
        // Never cache API requests or personalized responses: mission
        // generation must reflect live model availability, and the API may
        // carry user-specific data. Anything not precached goes to network.
        runtimeCaching: [],
        // outstep-mark.png (~575 kB) is part of the shell; leave headroom
        // above the 2 MiB default only if more brand art is ever added.
        maximumFileSizeToCacheInBytes: 3 * 1024 * 1024,
      },
      devOptions: {
        // No service worker in development: the dev server proxies /api to
        // the local backend and must never serve stale assets.
        enabled: false,
      },
    }),
  ],
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
