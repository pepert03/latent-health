import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// En desarrollo, /api se reenvía al servidor local de Python (web/server).
// IP literal: en Windows «localhost» resuelve antes a ::1 y uvicorn escucha en 127.0.0.1.
const apiTarget = process.env.API_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: { '/api': { target: apiTarget, changeOrigin: true } },
  },
})
