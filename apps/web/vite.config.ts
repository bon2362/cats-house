import { defineConfig } from 'vitest/config'

export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: process.env.CATS_HOUSE_API_PROXY_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
  },
})
