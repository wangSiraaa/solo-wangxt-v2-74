import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Build straight into the FastAPI static directory.
export default defineConfig({
  plugins: [react()],
  build: { outDir: '../backend/static', emptyOutDir: true },
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
