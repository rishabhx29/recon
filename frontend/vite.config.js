import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // keeps the browser on one origin in development, so the api needs no cors
    // configuration at all
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
