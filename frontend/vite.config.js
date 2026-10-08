import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// During dev, proxy /api to the FastAPI backend so the browser sees one origin
// (no CORS). The backend runs on port 8000.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: process.env.PORT ? Number(process.env.PORT) : 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
