import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
  server: {
    port: 5173,
    // Local dev: proxy API calls to the FastAPI backend
    proxy: {
      '/v1': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
