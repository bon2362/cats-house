import { defineConfig } from '@playwright/test'

// End-to-end checks run against the already started local stack:
// API on http://localhost:8000 and Vite UI on CATS_HOUSE_E2E_URL (default http://localhost:5176).
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  use: {
    baseURL: process.env.CATS_HOUSE_E2E_URL ?? 'http://localhost:5176',
    channel: 'chrome',
    viewport: { width: 1600, height: 1000 },
  },
})
