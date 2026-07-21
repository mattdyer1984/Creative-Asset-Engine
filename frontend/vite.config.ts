import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // During `npm run dev`, proxy API calls to the FastAPI backend so the
    // frontend can be developed with hot reload without needing its own
    // build served by uvicorn. Production still serves the built static
    // files directly from FastAPI (see backend/app/main.py).
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
